"""Run only on the assignment's isolated synthetic database; export real evidence."""
import json
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'evidence'
OUT.mkdir(exist_ok=True)
BASE='http://127.0.0.1:8092'
session=requests.Session();session.trust_env=False
def login(name):
    r=session.post(BASE+'/api/login',json={'username':name,'password':'teacherpass123' if name.startswith('teacher') else 'studentpass123'})
    r.raise_for_status();return {'Authorization':'Bearer '+r.json()['access_token']}
headers=login('teacher_a')
bheaders=login('teacher_b')
# This script creates no personal inputs: all model-bound data is task-authored fixtures.
for i,path in enumerate(sorted((ROOT/'fixtures').glob('0*.md'))):
    h=bheaders if 'class-b' in path.name else headers
    existing=session.get(BASE+'/api/materials',headers=h).json()['materials']
    if path.name in [m['title'] for m in existing]: continue
    with path.open('rb') as file:
        r=session.post(BASE+'/api/materials',headers=h,files={'file':(path.name,file,'text/markdown')},timeout=80)
    r.raise_for_status();assert r.json()['index_status']=='ready',r.text
    print('indexed',path.name,flush=True)
session.get(BASE+'/api/platform',headers=headers).raise_for_status()
with (ROOT/'fixtures/uploaded-summary.md').open('rb') as file:
    r=session.post(BASE+'/api/skills',headers=headers,files={'file':('uploaded-summary.md',file)})
r.raise_for_status();sid=r.json()['id']
summary=[]
def turn(name,payload):
    r=session.post(BASE+'/api/chat',headers=headers,json=payload,timeout=180)
    r.raise_for_status();data=r.json()
    tr=session.get(BASE+'/api/traces/'+data['trace_id'],headers=headers).json()
    (OUT/(name+'.json')).write_text(json.dumps(tr,ensure_ascii=False,indent=2),encoding='utf-8')
    chats=[e for e in tr['events'] if e['type']=='provider' and e['kind']=='chat']
    assert tr['status']=='ok'
    assert all(tr['rendered_template'] in e['request']['messages'][0]['content'] for e in chats)
    summary.append({'case':name,'trace_id':tr['id'],'answer':data['answer'],'llm_rounds':len(chats)})
    print('passed',name,'LLM rounds',len(chats),flush=True)
    return data,tr,chats

first,tr,chats=turn('01-template',{'app_id':'study','question':'用一句话解释什么是二分查找。','audience':'初学者','style':'简洁'})
turn('02-history',{'app_id':'study','question':'再给我一个生活中的类比。','conversation_id':first['conversation_id'],'audience':'初学者','style':'简洁'})
turn('03-writing',{'app_id':'writing','question':'写一则明天下午三点进行班级读书交流的通知，50字以内。'})
data,tr,chats=turn('04-knowledge',{'app_id':'knowledge','question':'磁铁能吸引木块吗？哪些位置吸力最强？'})
assert 0<tr['retrieval']['selected_count']<=2<tr['retrieval']['total_class_chunks']
wire=json.dumps([e['request'] for e in chats],ensure_ascii=False)
assert 'B_CLASS_PRIVATE_1028' not in wire
excluded=[f for f in sorted((ROOT/'fixtures').glob('0*.md')) if f.name not in [s['material_title'] for s in tr['retrieval']['sources']]]
assert any(f.read_text('utf-8').strip() not in wire for f in excluded)
data,tr,chats=turn('05-skill-builtin',{'app_id':'study','skill_id':'calculation-review','question':'请核验 (18 + 24) * 3 / 2 的结果。'})
assert 'CALC_SKILL_BODY_1028' not in json.dumps(chats[0]['request'],ensure_ascii=False)
assert any('CALC_SKILL_BODY_1028' in json.dumps(e['request'],ensure_ascii=False) for e in chats[1:])
assert any(e['type']=='external_http' and e['response'].get('result')==63 for e in tr['events'])
data,tr,chats=turn('06-skill-upload',{'app_id':'study','skill_id':sid,'question':'把“磁铁能吸引铁钉但不能吸引木块”整理成复习卡。'})
assert 'UPLOADED_SKILL_BODY_1028' not in json.dumps(chats[0]['request'],ensure_ascii=False)
assert 'UPLOADED_SKILL_BODY_1028' in json.dumps(chats[-1]['request'],ensure_ascii=False)
data,tr,chats=turn('07-mcp',{'app_id':'tools','tool_mode':'mcp','question':'请使用 MCP 加法工具计算 137 + 286。'})
assert any(e['type']=='mcp_rpc' and e['request']['method']=='tools/call' and '423' in json.dumps(e['response']) for e in tr['events'])
assert any(m['role']=='tool' for m in chats[-1]['request']['messages'])
student=login('student_a1')
assert session.get(BASE+'/api/traces/'+tr['id'],headers=student).status_code==404
assert session.post(BASE+'/api/chat',headers=student,json={'app_id':'study','question':'使用技能','skill_id':sid}).status_code==404
summary.append({'case':'isolation','result':'他人 Trace / Skill 均返回 404'})
(OUT/'verification-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print('All live verification cases passed.',flush=True)
