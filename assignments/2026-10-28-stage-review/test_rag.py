import io
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import uuid

import app as server
import knowledge


def vectors(con, texts):
    result = []
    for text in texts:
        axis = 0 if '磁铁' in text else 1 if '蓝鲸' in text else 2
        value = [0.0] * knowledge.DIM
        value[axis] = 1.0
        result.append(value)
    return result


class RagTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent / '.test-data'
        self.temp = self.root / ('rag-test-' + uuid.uuid4().hex)
        self.temp.mkdir()
        server.DATA = self.temp
        server.UPLOADS = self.temp / 'uploads'
        server.UPLOADS.mkdir()
        server.initialize()
        self.client = server.app.test_client()
        self.embedding = patch('knowledge.embed_texts', side_effect=vectors)
        self.embedding.start()
        self.teacher = self.login('teacher_a')
        self.student = self.login('student_a1')
        self.other = self.login('student_b1')
        self.teacher_b = self.login('teacher_b')
        self.a = self.upload(self.teacher, '磁铁不能吸引木块。中文与emoji🧲。', '科学.md').json['id']
        self.b = self.upload(self.teacher_b, '蓝鲸七号是B班活动代号。', '活动.md').json['id']

    def tearDown(self):
        self.embedding.stop()
        assert self.temp.resolve().is_relative_to(self.root.resolve())
        shutil.rmtree(self.temp)

    def login(self, name):
        data = self.client.post('/api/login', json={'username':name,
            'password':'teacherpass123' if name.startswith('teacher') else 'studentpass123'}).json
        return {'Authorization':'Bearer ' + data['access_token']}

    def upload(self, headers, text, name='test.md'):
        return self.client.post('/api/materials', headers=headers,
            data={'file':(io.BytesIO(text.encode()), name)})

    def query(self, q, mode='hybrid', headers=None, endpoint='/api/search', **kwargs):
        return self.client.post(endpoint, headers=headers or self.student,
            json={'q':q,'mode':mode, **kwargs})

    def test_unicode_chunks_cover_original(self):
        text = ('正文🧲。' * 470) + '结尾'
        chunks = list(knowledge.split_text(text))
        self.assertGreater(len(chunks), 1)
        covered = set()
        for start, end, body in chunks:
            self.assertLessEqual(len(body), 800)
            self.assertEqual(text[start:end], body)
            covered.update(range(start, end))
        self.assertEqual(covered, set(range(len(text))))

    def test_invalid_requests_and_anonymous(self):
        for endpoint in ['/api/search','/api/ask']:
            self.assertEqual(self.client.post(endpoint,json={'q':'磁铁'}).status_code,401)
            for payload in [None,[],{}, {'q':''},{'q':42},{'q':'x'*201},{'q':'磁铁','limit':True},
                            {'q':'磁铁','limit':21},{'q':'磁铁','mode':'unknown'}]:
                self.assertEqual(self.client.post(endpoint,headers=self.student,json=payload).status_code,400)

    def test_scoped_search_ignores_client_class(self):
        response = self.query('蓝鲸七号', class_id=2)
        self.assertEqual(response.json['status'],'no_evidence')
        a = self.query('磁铁',headers=self.teacher).json['hits']
        b = self.query('磁铁').json['hits']
        self.assertEqual(a,b)
        self.assertTrue(all(hit['class_code']=='A' for hit in a))
        self.assertEqual(self.query('磁铁',headers=self.other).json['hits'],[])

    def test_keyword_independent_and_hybrid_rrf(self):
        with patch('knowledge.embed_texts',side_effect=AssertionError('must not call embedding')):
            data = self.query('磁铁','keyword').json
        self.assertEqual(len(data['hits']),1)
        combined = self.query('磁铁').json['hits']
        self.assertEqual(len(combined),1)
        self.assertAlmostEqual(combined[0]['score_final'],2/61)
        self.assertAlmostEqual(combined[0]['score_vector'],1)

    def test_empty_results_skip_chat(self):
        with patch('knowledge.provider_call', side_effect=AssertionError('must not call chat')):
            result = self.query('火星天气',endpoint='/api/ask')
        self.assertEqual(result.status_code,200)
        self.assertFalse(result.json['model_called'])
        self.assertEqual(result.json['sources'],[])

    def test_dependency_failure_is_not_no_evidence(self):
        with patch('knowledge.embed_texts',side_effect=knowledge.ModelUnavailable('模型暂不可用')):
            for mode in ['hybrid','vector']:
                self.assertEqual(self.query('磁铁',mode).status_code,503)
            self.assertEqual(self.query('磁铁','keyword').status_code,200)

    def test_upload_failure_retry_and_reindex_permissions(self):
        with patch('knowledge.embed_texts',side_effect=knowledge.ModelUnavailable('模型暂不可用')):
            response = self.upload(self.teacher,'磁铁测试','失败后重试.md')
        self.assertEqual(response.status_code,201)
        self.assertEqual(response.json['index_status'],'failed')
        mid = response.json['id']
        self.assertEqual(self.client.get(f'/api/materials/{mid}',headers=self.teacher).status_code,200)
        route = f'/api/materials/{mid}/reindex'
        self.assertEqual(self.client.post(route,headers=self.student).status_code,403)
        self.assertEqual(self.client.post(route,headers=self.teacher_b).status_code,404)
        for _ in range(2):self.assertEqual(self.client.post(route,headers=self.teacher).status_code,200)
        with server.app.app_context():
            self.assertEqual(server.db().execute('SELECT COUNT(*) FROM knowledge_chunks WHERE material_id=?',(mid,)).fetchone()[0],1)

    def test_generation_checks_citations(self):
        for value, expected in [({'has_evidence':True,'answer':'不能吸引木块。[1]','citations':[1]},200),
                                ({'has_evidence':True,'answer':'伪造答案[2]','citations':[2]},503),
                                ({'has_evidence':True,'answer':'没有引用','citations':[1]},503)]:
            response = {'choices':[{'message':{'content':json.dumps(value)}}]}
            with patch('knowledge.provider_call',return_value=(response,'test-request')):
                result = self.query('磁铁',endpoint='/api/ask')
            self.assertEqual(result.status_code,expected)
            if expected == 200:
                hit = result.json['sources'][0]
                original = self.client.get(hit['detail_url'],headers=self.student).json['material']['body_text']
                self.assertEqual(original[hit['start_offset']:hit['end_offset']],hit['snippet'])

    def test_changed_source_excluded(self):
        with server.app.app_context(), server.db():
            server.db().execute('UPDATE knowledge_entries SET body_text=? WHERE material_id=?',('内容已更改',self.a))
        self.assertEqual(self.query('磁铁').json['hits'],[])


if __name__ == '__main__':
    unittest.main(verbosity=2)
