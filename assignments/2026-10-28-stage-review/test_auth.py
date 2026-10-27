import base64
import io
import json
import shutil
import uuid
import time
import unittest
from unittest.mock import patch
from pathlib import Path

import app as server


class AuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_root = Path(__file__).resolve().parent / '.test-data'
        cls.temp = cls.test_root / ('auth-test-' + uuid.uuid4().hex)
        cls.temp.mkdir()
        server.DATA = cls.temp
        server.UPLOADS = server.DATA / 'uploads'
        server.UPLOADS.mkdir()
        server.initialize()
        cls.client = server.app.test_client()
        cls.embedding_mock = patch('knowledge.embed_texts', side_effect=lambda con, texts: [[1.0] + [0.0] * 1023 for _ in texts])
        cls.embedding_mock.start()

    @classmethod
    def tearDownClass(cls):
        cls.embedding_mock.stop()
        assert cls.temp.resolve().is_relative_to(cls.test_root.resolve())
        shutil.rmtree(cls.temp)

    def login(self, name='student_a1'):
        response = self.client.post('/api/login', json={
            'username': name, 'password': 'teacherpass123' if name == 'teacher_a' else 'studentpass123'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Set-Cookie', response.headers)
        data = response.json
        self.assertEqual(data['token_type'], 'Bearer')
        return data['access_token']

    def headers(self, token):
        return {'Authorization': 'Bearer ' + token}

    def test_login_and_signed_token(self):
        token = self.login()
        claims = server.jwt.decode(token, server.SECRET, algorithms=['HS256'],
            issuer=server.TOKEN_ISSUER, audience=server.TOKEN_AUDIENCE)
        self.assertEqual(claims['sub'], '2')
        self.assertEqual(claims['exp'] - claims['iat'], 3600)
        response = self.client.get('/api/materials', headers=self.headers(token))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(m['class_code'] == 'A' for m in response.json['materials']))

    def test_wrong_password(self):
        self.assertEqual(self.client.post('/api/login', json={'username': 'teacher_a', 'password': 'wrong'}).status_code, 401)

    def test_anonymous_rejected(self):
        for path in ['/api/me', '/api/materials', '/api/materials/1', '/api/materials/1/file']:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.headers['WWW-Authenticate'], 'Bearer')

    def test_cookie_is_not_bearer(self):
        token = self.login()
        client = server.app.test_client()
        client.set_cookie('session', token)
        self.assertEqual(client.get('/api/materials').status_code, 401)

    def test_tampered_subject(self):
        token = self.login()
        h, payload, signature = token.split('.')
        claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        claims['sub'] = '1'
        payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')
        self.assertEqual(self.client.get('/api/me', headers=self.headers('.'.join([h, payload, signature]))).status_code, 401)

    def test_expired_wrong_audience_and_none_algorithm(self):
        now = int(time.time())
        claims = {'sub': '2', 'iat': now - 100, 'nbf': now - 100, 'exp': now + 100,
            'iss': server.TOKEN_ISSUER, 'aud': server.TOKEN_AUDIENCE, 'jti': 'test'}
        for change, key, algorithm in [({'exp': now - 10}, server.SECRET, 'HS256'),
                ({'aud': 'another-api'}, server.SECRET, 'HS256'), ({}, None, 'none')]:
            token = server.jwt.encode({**claims, **change}, key, algorithm=algorithm)
            with server.app.app_context(), server.db():
                server.db().execute('INSERT INTO sessions VALUES(?,?,?)', (server.token_hash(token), 2, now + 100))
            self.assertEqual(self.client.get('/api/me', headers=self.headers(token)).status_code, 401)

    def test_student_cannot_upload_or_forge_role(self):
        headers = {**self.headers(self.login()), 'X-Role': 'teacher', 'X-Class-Id': '2'}
        response = self.client.post('/api/materials', headers=headers,
            data={'file': (io.BytesIO(b'test'), 'student.txt'), 'role': 'teacher'})
        self.assertEqual(response.status_code, 403)

    def test_teacher_upload_and_protected_download(self):
        teacher = self.headers(self.login('teacher_a'))
        content = '教师上传的本班正文'.encode()
        result = self.client.post('/api/materials', headers=teacher,
            data={'file': (io.BytesIO(content), 'teacher.txt'), 'class_id': '2'})
        self.assertEqual(result.status_code, 201)
        path = '/api/materials/' + str(result.json['id']) + '/file'
        result = self.client.get(path, headers=self.headers(self.login()))
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data, content)
        result.close()
        self.assertEqual(self.client.get(path, headers=self.headers(self.login('student_b1'))).status_code, 404)

    def test_class_and_sources_are_server_scoped(self):
        headers = {**self.headers(self.login('student_b1')), 'X-Class-Id': '1'}
        result = self.client.get('/api/materials?class_id=1', headers=headers)
        self.assertTrue(all(m['class_code'] == 'B' for m in result.json['materials']))
        self.assertEqual(self.client.get('/api/materials/1', headers=headers).status_code, 404)
        self.assertEqual(self.client.get('/api/materials/1/file', headers=headers).status_code, 404)

    def test_logout_revokes_replayed_token(self):
        headers = self.headers(self.login())
        self.assertEqual(self.client.post('/api/logout', headers=headers).status_code, 200)
        self.assertEqual(self.client.get('/api/materials', headers=headers).status_code, 401)


if __name__ == '__main__':
    unittest.main(verbosity=2)
