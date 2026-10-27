"""09/30 classroom implementation: JWT bearer authentication and class knowledge."""
from functools import wraps
from pathlib import Path
import hashlib
import hmac
import secrets
import sqlite3
import time
import uuid
import sys
import os
import knowledge

import jwt

from flask import Flask, g, jsonify, request, send_file
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.exceptions import RequestEntityTooLarge

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('CAMPUSCLAW_DATA', str(ROOT / 'data')))
UPLOADS = DATA / "uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)
secret_file = DATA / "session.key"
if not secret_file.exists():
    secret_file.write_bytes(secrets.token_bytes(32))
SECRET = secret_file.read_bytes()
LIMIT = 2 * 1024 * 1024
app = Flask(__name__, static_folder=None)
app.json.ensure_ascii = False
app.config["MAX_CONTENT_LENGTH"] = LIMIT + 64 * 1024
TOKEN_TTL = 3600
TOKEN_ISSUER = 'campusclaw-local'
TOKEN_AUDIENCE = 'campusclaw-api'


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DATA / "campusclaw.db", timeout=30)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(_error):
    if "db" in g:
        g.db.close()


def token_hash(token):
    return hmac.new(SECRET, token.encode(), hashlib.sha256).hexdigest()


def bearer_token():
    scheme, _, token = request.headers.get('Authorization', '').partition(' ')
    return token if scheme.lower() == 'bearer' and token and len(token) < 4096 else None


def current_user():
    token = bearer_token()
    if not token:
        return None
    try:
        claims = jwt.decode(token, SECRET, algorithms=['HS256'],
            issuer=TOKEN_ISSUER, audience=TOKEN_AUDIENCE,
            options={'require': ['sub', 'exp', 'iat', 'nbf', 'iss', 'aud', 'jti']})
    except jwt.InvalidTokenError:
        return None
    user = db().execute(
        "SELECT u.id,u.username,u.role,u.class_id,c.code AS class_code "
        "FROM sessions s JOIN users u ON u.id=s.user_id "
        "JOIN classes c ON c.id=u.class_id WHERE s.token_hmac=? AND s.expires_at>?",
        (token_hash(token), time.time()),
    ).fetchone()
    if user is None or str(user['id']) != claims['sub']:
        return None
    return user


def protected(fn):
    @wraps(fn)
    def checked(*args, **kwargs):
        g.user = current_user()
        if g.user is None:
            response = jsonify(error="未登录或 Token 已失效")
            response.headers['WWW-Authenticate'] = 'Bearer'
            return response, 401
        return fn(*args, **kwargs)
    return checked


@app.after_request
def no_cache(response):
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/")
def index():
    return send_file(ROOT / "index.html")


@app.get('/knowledge-ui.js')
def knowledge_ui():
    return send_file(ROOT / 'knowledge-ui.js', mimetype='application/javascript')


@app.get('/favicon.ico')
def favicon():
    return '', 204


@app.get('/health')
def health():
    return jsonify(status='ok')


@app.post("/api/login")
def login():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify(error="用户名或密码错误"), 401
    username, password = payload.get("username"), payload.get("password")
    if not isinstance(username, str) or not isinstance(password, str):
        return jsonify(error="用户名或密码错误"), 401
    user = db().execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if user is None or not check_password_hash(user["password_hash"], password):
        return jsonify(error="用户名或密码错误"), 401
    old = bearer_token()
    now = int(time.time())
    token = jwt.encode({'sub': str(user['id']), 'iat': now, 'nbf': now,
        'exp': now + TOKEN_TTL, 'iss': TOKEN_ISSUER, 'aud': TOKEN_AUDIENCE,
        'jti': secrets.token_hex(16)}, SECRET, algorithm='HS256')
    with db():
        if old:
            db().execute("DELETE FROM sessions WHERE token_hmac=?", (token_hash(old),))
        db().execute("INSERT INTO sessions VALUES(?,?,?)",
                     (token_hash(token), user["id"], now + TOKEN_TTL))
    code = db().execute("SELECT code FROM classes WHERE id=?", (user["class_id"],)).fetchone()[0]
    response = jsonify(access_token=token, token_type='Bearer', expires_in=TOKEN_TTL,
                       user={"id": user["id"], "username": username, "role": user["role"],
                             "class_id": user["class_id"], "class_code": code})
    return response


@app.post("/api/logout")
@protected
def logout():
    with db():
        db().execute("DELETE FROM sessions WHERE token_hmac=?",
                     (token_hash(bearer_token()),))
    response = jsonify(status="ok")
    return response


@app.get("/api/me")
@protected
def me():
    return jsonify(user=dict(g.user))


@app.get("/api/materials")
@protected
def materials():
    rows = db().execute(
        "SELECT m.id,m.title,c.code AS class_code,m.created_at FROM materials m "
        "JOIN classes c ON c.id=m.class_id WHERE m.class_id=? ORDER BY m.id DESC",
        (g.user["class_id"],),
    ).fetchall()
    return jsonify(materials=[dict(row) for row in rows])


def resolve_material(material_id):
    row = db().execute("SELECT * FROM materials WHERE id=?", (material_id,)).fetchone()
    if row is None or row["class_id"] != g.user["class_id"]:
        return None
    return row


@app.get("/api/materials/<int:material_id>")
@protected
def detail(material_id):
    row = resolve_material(material_id)
    if row is None:
        return jsonify(error="材料不存在"), 404
    body = db().execute("SELECT body_text FROM knowledge_entries WHERE material_id=?",
                        (material_id,)).fetchone()[0]
    return jsonify(material={"id": row["id"], "title": row["title"],
        "class_code": g.user["class_code"], "created_at": row["created_at"], "body_text": body})


@app.get("/api/materials/<int:material_id>/file")
@protected
def download(material_id):
    row = resolve_material(material_id)
    if row is None:
        return jsonify(error="材料不存在"), 404
    target = (UPLOADS / row["file_path"]).resolve()
    if not target.is_relative_to(UPLOADS.resolve()) or not target.is_file():
        return jsonify(error="材料不存在"), 404
    return send_file(target, mimetype="text/plain; charset=utf-8", as_attachment=True,
                     download_name=row["title"], conditional=False)


@app.post("/api/materials")
@protected
def upload():
    if g.user["role"] != "teacher":
        return jsonify(error="仅教师可以上传材料"), 403
    file = request.files.get("file")
    if file is None or not file.filename:
        return jsonify(error="请选择文件"), 400
    title = file.filename.replace("\\", "/").rsplit("/", 1)[-1]
    ext = Path(title).suffix.lower()
    if ext not in {".txt", ".md"}:
        return jsonify(error="仅支持 .txt 和 .md 文件"), 400
    raw = file.stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        return jsonify(error="文件超过 2 MiB 限制"), 413
    try:
        text = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return jsonify(error="文件必须是 UTF-8 文本"), 400
    if not text:
        return jsonify(error="文件内容不能为空"), 400
    relative = f"{g.user['class_id']}/{uuid.uuid4().hex}{ext}"
    path = UPLOADS / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_bytes(raw)
        with db():
            cursor = db().execute(
                "INSERT INTO materials(class_id,title,file_path,uploaded_by) VALUES(?,?,?,?)",
                (g.user["class_id"], title, relative, g.user["id"]),
            )
            material_id = cursor.lastrowid
            db().execute("INSERT INTO knowledge_entries(material_id,class_id,body_text) VALUES(?,?,?)",
                         (material_id, g.user["class_id"], text))
    except (OSError, sqlite3.Error):
        path.unlink(missing_ok=True)
        app.logger.exception("upload failed")
        return jsonify(error="上传失败"), 500
    try:
        count = knowledge.index_material(db(), material_id, g.user['class_id'])
        return jsonify(id=material_id, title=title, index_status='ready', chunks=count), 201
    except knowledge.ModelUnavailable:
        return jsonify(id=material_id, title=title, index_status='failed',
            message='材料已保存，索引失败，可重试'), 201


@app.post('/api/materials/<int:material_id>/reindex')
@protected
def reindex(material_id):
    if g.user['role'] != 'teacher':
        return jsonify(error='仅教师可以重建索引'), 403
    if resolve_material(material_id) is None:
        return jsonify(error='材料不存在'), 404
    try:
        return jsonify(status='ready', chunks=knowledge.index_material(db(), material_id, g.user['class_id']))
    except knowledge.ModelUnavailable as exc:
        return jsonify(error=str(exc)), 503


def query_parameters():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get('q'), str):
        raise ValueError('请输入问题')
    query = payload['q'].strip()
    mode, limit = payload.get('mode', 'hybrid'), payload.get('limit', 4)
    if not 1 <= len(query) <= 200:
        raise ValueError('问题长度须为 1 至 200 个字符')
    if mode not in ('keyword', 'vector', 'hybrid') or type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError('检索参数无效')
    return query, mode, limit


@app.post('/api/search')
@protected
def search():
    try:
        query, mode, limit = query_parameters()
        hits = knowledge.search(db(), g.user['class_id'], query, mode, limit)
        if current_user() is None:
            return jsonify(error='Token 已失效'), 401
        return jsonify(status='ok' if hits else 'no_evidence', hits=hits, mode=mode)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except knowledge.ModelUnavailable as exc:
        return jsonify(error=str(exc)), 503


@app.post('/api/ask')
@protected
def ask():
    try:
        query, _, _ = query_parameters()
        result = knowledge.answer(db(), g.user['class_id'], query)
        if current_user() is None:
            return jsonify(error='Token 已失效'), 401
        return jsonify(result)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except knowledge.ModelUnavailable as exc:
        return jsonify(error=str(exc)), 503


@app.errorhandler(RequestEntityTooLarge)
def too_large(_error):
    return jsonify(error="上传请求超过大小限制"), 413


def initialize():
    with app.app_context():
        db().executescript("""
        CREATE TABLE IF NOT EXISTS classes(id INTEGER PRIMARY KEY,code TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,
          password_hash TEXT NOT NULL,role TEXT NOT NULL,class_id INTEGER NOT NULL REFERENCES classes(id));
        CREATE TABLE IF NOT EXISTS sessions(token_hmac TEXT PRIMARY KEY,user_id INTEGER REFERENCES users(id),expires_at REAL);
        CREATE TABLE IF NOT EXISTS materials(id INTEGER PRIMARY KEY,class_id INTEGER NOT NULL REFERENCES classes(id),
          title TEXT NOT NULL,file_path TEXT NOT NULL,uploaded_by INTEGER REFERENCES users(id),
          created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')));
        CREATE TABLE IF NOT EXISTS knowledge_entries(id INTEGER PRIMARY KEY,material_id INTEGER UNIQUE REFERENCES materials(id),
          class_id INTEGER NOT NULL REFERENCES classes(id),body_text TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS materials_class ON materials(class_id);
        """)
        knowledge.ensure_schema(db())
        with db():
            db().executemany("INSERT OR IGNORE INTO classes VALUES(?,?)", [(1,"A"),(2,"B")])
            for uid, name, role, cid, password in [
                (1,"teacher_a","teacher",1,"teacherpass123"),
                (2,"student_a1","student",1,"studentpass123"),
                (3,"student_b1","student",2,"studentpass123"),
                (4,"teacher_b","teacher",2,"teacherpass123")]:
                if not db().execute("SELECT id FROM users WHERE id=?", (uid,)).fetchone():
                    db().execute("INSERT INTO users VALUES(?,?,?,?,?)",
                        (uid,name,generate_password_hash(password,method="scrypt"),role,cid))
            if not db().execute("SELECT id FROM materials LIMIT 1").fetchone():
                for cid, code in [(1,"A"),(2,"B")]:
                    body = f"{code}班演示材料\n\n这是预置的演示材料。"
                    relative = f"{cid}/{uuid.uuid4().hex}.txt"
                    path = UPLOADS / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(body,encoding="utf-8")
                    cursor = db().execute("INSERT INTO materials(class_id,title,file_path,uploaded_by) VALUES(?,?,?,?)",
                        (cid,f"{code}班演示材料",relative,1 if cid==1 else 3))
                    db().execute("INSERT INTO knowledge_entries(material_id,class_id,body_text) VALUES(?,?,?)",
                        (cursor.lastrowid,cid,body))


import platform_api
platform_api.register(app, db, protected, current_user)

if __name__ == "__main__":
    initialize()
    with app.app_context():
        platform_api.ensure_schema(db())
    app.run(host="127.0.0.1", port=int(os.environ.get('CAMPUSCLAW_PORT', '8092')), debug=False)
