import io
import json
from pathlib import Path
import shutil
import unittest
import uuid
from unittest.mock import patch
import app as server
import platform_api
import tracing
from external_calculator import calculate

class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(__file__).resolve().parent/'.test-data'
        self.root.mkdir(exist_ok=True)
        self.temp=self.root/uuid.uuid4().hex;self.temp.mkdir()
        server.DATA=self.temp;server.UPLOADS=self.temp/'uploads';server.UPLOADS.mkdir()
        server.initialize()
        self.client=server.app.test_client()
        with server.app.app_context(): platform_api.ensure_schema(server.db())
        self.a=self.login('teacher_a');self.b=self.login('student_b1')
    def tearDown(self):
        assert self.temp.resolve().is_relative_to(self.root.resolve())
        shutil.rmtree(self.temp)
    def login(self,name):
        r=self.client.post('/api/login',json={'username':name,'password':'teacherpass123' if name.startswith('teacher') else 'studentpass123'})
        return {'Authorization':'Bearer '+r.json['access_token']}
    def provider(self,con,kind,payload):
        result={'id':'test-only','choices':[{'message':{'role':'assistant','content':'测试答复'}}]}
        tracing.record({'type':'provider','kind':kind,'request':payload,'response':result})
        return result,'test-only'
    def test_templates_render_and_history_owner(self):
        self.assertEqual(self.client.put('/api/templates/study',headers=self.a,json={'body':'面向{audience}，风格{style}，模板核验'}).status_code,200)
        with patch('knowledge.provider_call',side_effect=self.provider) as mock:
            first=self.client.post('/api/chat',headers=self.a,json={'app_id':'study','question':'问题一','audience':'小学生','style':'简单'})
            self.assertEqual(first.status_code,200)
            request=mock.call_args[0][2]
            self.assertTrue(request['messages'][0]['content'].startswith('面向小学生，风格简单，模板核验'))
            cid=first.json['conversation_id']
            self.assertEqual(self.client.post('/api/chat',headers=self.b,json={'app_id':'study','question':'越权','conversation_id':cid}).status_code,404)
            second=self.client.post('/api/chat',headers=self.a,json={'app_id':'study','question':'问题二','conversation_id':cid})
            self.assertEqual(second.status_code,200)
            self.assertEqual([x['role'] for x in mock.call_args[0][2]['messages']],['system','user','assistant','user'])
    def test_trace_owner_and_no_header_capture(self):
        with patch('knowledge.provider_call',side_effect=self.provider):
            r=self.client.post('/api/chat',headers=self.a,json={'app_id':'writing','question':'测试'})
        tid=r.json['trace_id']
        self.assertEqual(self.client.get('/api/traces/'+tid).status_code,401)
        self.assertEqual(self.client.get('/api/traces/'+tid,headers=self.b).status_code,404)
        trace=self.client.get('/api/traces/'+tid,headers=self.a)
        self.assertNotIn(self.a['Authorization'],trace.text)
        self.assertNotIn('password',trace.text)
    def test_uploaded_skill_validation_and_scope(self):
        raw=(Path(__file__).parent/'fixtures/uploaded-summary.md').read_bytes()
        r=self.client.post('/api/skills',headers=self.a,data={'file':(io.BytesIO(raw),'SKILL.md')})
        self.assertEqual(r.status_code,201)
        self.assertEqual(self.client.post('/api/chat',headers=self.b,json={'app_id':'study','question':'test','skill_id':r.json['id']}).status_code,404)
        for name,data in [('bad.py',b'print(1)'),('bad.md',b'not metadata')]:
            self.assertEqual(self.client.post('/api/skills',headers=self.a,data={'file':(io.BytesIO(data),name)}).status_code,400)
    def test_skill_body_deferred_and_action_tools_deferred(self):
        captured=[]
        def provider(con,kind,payload):
            captured.append(json.loads(json.dumps(payload)))
            if len(captured)==1:
                msg={'role':'assistant','content':None,'tool_calls':[{'id':'load-1','type':'function','function':{'name':'load_skill','arguments':'{"skill_id":"calculation-review"}'}}]}
            else: msg={'role':'assistant','content':'已加载'}
            return {'choices':[{'message':msg}]},'test'
        with patch('knowledge.provider_call',side_effect=provider):
            r=self.client.post('/api/chat',headers=self.a,json={'app_id':'study','question':'计算','skill_id':'calculation-review'})
        self.assertEqual(r.status_code,200)
        self.assertNotIn('CALC_SKILL_BODY_1028',json.dumps(captured[0]))
        self.assertIn('CALC_SKILL_BODY_1028',json.dumps(captured[1]))
        self.assertEqual([t['function']['name'] for t in captured[0]['tools']],['load_skill'])
        self.assertIn('calculate',[t['function']['name'] for t in captured[1]['tools']])
        self.assertNotIn('tool_choice',captured[1])
    def test_calculator_rejects_code_and_unbounded_operations(self):
        self.assertEqual(calculate('(18+24)*3/2'),63)
        for expr in ['__import__("os").getcwd()','2**100000','1/0','float("nan")']:
            with self.assertRaises((ValueError,ArithmeticError)): calculate(expr)
    def test_mcp_only_two_finite_numbers(self):
        import mcp_client
        for args in [{'a':1,'b':2,'command':'x'},{'a':True,'b':2},{'a':float('inf'),'b':2}]:
            with self.assertRaises(ValueError):mcp_client.call_add(args)
    def test_empty_knowledge_skips_chat(self):
        with patch('knowledge.search',return_value=[]),patch('knowledge.provider_call') as model:
            r=self.client.post('/api/chat',headers=self.a,json={'app_id':'knowledge','question':'不存在的资料'})
        self.assertEqual(r.status_code,200)
        self.assertFalse(r.json['model_called']);model.assert_not_called()
    def test_chat_validates_payload(self):
        for payload in [[],{}, {'app_id':'study','question':'q','audience':{}},{'app_id':'unknown','question':'q'}]:
            self.assertEqual(self.client.post('/api/chat',headers=self.a,json=payload).status_code,400)

if __name__=='__main__':unittest.main()
