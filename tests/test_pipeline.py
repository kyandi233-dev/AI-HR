"""Offline tests only: do not call DeepSeek or O*NET."""
from pathlib import Path
import csv
import importlib.util
import json
import os
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('hrpilot', ROOT/'src/hrpilot.py')
hr=importlib.util.module_from_spec(spec)
spec.loader.exec_module(hr)

class Args:
    occupation='software_developer'
    foundation='fairness'
    count=2
    start_index=1
    repeat=1
    run_id='test01'
    source='approved'
    limit=None
    execute=False
    retry_failed=False

class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=hr.load_json(ROOT/'config/settings.json')
        cls.occ=hr.load_json(ROOT/'config/occupations.json')

    def test_authentication_errors_redact_key_before_logging(self):
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'test-secret-key'}):
            self.assertNotIn('test-secret-key',hr.safe_error_message('Your api key: test-secret-key is invalid'))
            self.assertNotIn('test-***-key',hr.safe_error_message('Your api key: test-***-key is invalid'))

    def test_abstract_principles_no_job_and_four_orders(self):
        a=Args()
        tasks=hr.make_tasks('principles',a,self.occ,self.config)
        self.assertEqual(len(tasks),4)
        self.assertEqual({t['metadata']['condition'] for t in tasks},{'M12','M21','A12','A21'})
        for t in tasks:
            self.assertEqual(len(t['messages']),1)
            self.assertEqual(t['messages'][0]['role'],'user')
            u=t['messages'][0]['content']
            self.assertNotIn('JD_TEXT',u)
            self.assertNotIn('软件开发',u)
            self.assertNotIn('招聘岗位说明',u)
            self.assertNotIn('心理学实验',u)
            d=t['metadata']['definition_order']
            torder=t['metadata']['task_order']
            left=u.index('私人道德信息：'); right=u.index('专业能力信息：')
            self.assertEqual(left<right,d[0]=='morality')
            task1=u.index('任务一：专业能力判断。')
            task2=u.index('任务二：面试推荐判断。')
            self.assertEqual(task1<task2,torder[0]=='task1')

    def test_moral_generation_prompt_and_json(self):
        t=hr.make_tasks('moral-generate',Args(),self.occ,self.config)
        self.assertEqual(len(t),2)
        self.assertTrue(t[0]['json_mode'])
        self.assertIn('FAIRNESS_001',t[0]['messages'][0]['content'])
        self.assertIn('中性',t[0]['messages'][0]['content'])

    def test_principles_repeat_whole_prompt_in_independent_messages(self):
        a=Args()
        a.repeat=2
        tasks=hr.make_tasks('principles',a,self.occ,self.config)
        self.assertEqual(len(tasks),8)
        for condition in ['M12','M21','A12','A21']:
            repeats=[t for t in tasks if t['metadata']['condition']==condition]
            self.assertEqual([t['metadata']['repeat'] for t in repeats],[1,2])
            self.assertEqual(repeats[0]['messages'],repeats[1]['messages'])
            self.assertIsNot(repeats[0]['messages'],repeats[1]['messages'])
            for task in repeats:
                self.assertEqual(len(task['messages']),1)
                self.assertIn('任务一：',task['messages'][0]['content'])
                self.assertIn('任务二：',task['messages'][0]['content'])

    def test_record_and_export_identify_batch_without_duplicate_calls(self):
        a=Args()
        a.repeat=2
        tasks=hr.make_tasks('principles',a,self.occ,self.config)[:2]
        answer={k:{'priority':'专业能力信息','weight_ability':60,'weight_morality':40,
                   'importance_ability':5,'importance_morality':3,'reason':'test'}
                for k in ['task1','task2']}
        response=SimpleNamespace(
            id='test-response',model='test-model',system_fingerprint=None,
            choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(
                content=json.dumps(answer)))],model_dump=lambda **kw: {})
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(hr,'ROOT',Path(tmp)),patch.object(hr,'RESULTS',Path(tmp)),patch.object(hr,'api_request',return_value=(response,{})) as api:
                for task in tasks:
                    self.assertEqual(hr.record_task(task,self.config,a),'ok')
                    record=hr.load_json(hr.path_for(task,a.run_id)/'record.json')
                    self.assertEqual(record['run_id'],a.run_id)
                    self.assertEqual(record['record_unit'],'api_request')
                self.assertEqual(hr.record_task(tasks[0],self.config,a),'skip')
                self.assertEqual(api.call_count,2)
                # A legacy record still exports its batch from the directory.
                legacy_path=hr.path_for(tasks[0],a.run_id)/'record.json'
                legacy=hr.load_json(legacy_path)
                del legacy['run_id']
                del legacy['record_unit']
                legacy_path.write_text(json.dumps(legacy),encoding='utf-8')
                hr.export_results()
                with (Path(tmp)/'all_results.csv').open(encoding='utf-8-sig',newline='') as fp:
                    rows=list(csv.DictReader(fp))
                self.assertEqual(len(rows),2)
                self.assertEqual({r['run_id'] for r in rows},{a.run_id})
                self.assertEqual({r['record_unit'] for r in rows},{'api_request'})
                self.assertEqual({r['meta_repeat'] for r in rows},{'1','2'})
                batch_dir=hr.path_for(tasks[0],a.run_id).parent
                with (batch_dir/(a.run_id+'.csv')).open(encoding='utf-8-sig',newline='') as fp:
                    self.assertEqual(list(csv.DictReader(fp)),rows)
                # Historical failures belong to the same batch, even without new fields.
                archived=legacy_path.parent/'failed_attempts'/'2026-11-16T00-00-00'
                archived.mkdir(parents=True)
                legacy['status']='error'
                (archived/'record.json').write_text(json.dumps(legacy),encoding='utf-8')
                hr.export_results()
                with (batch_dir/(a.run_id+'.csv')).open(encoding='utf-8-sig',newline='') as fp:
                    rows=list(csv.DictReader(fp))
                self.assertEqual(len(rows),3)
                self.assertEqual({r['run_id'] for r in rows},{a.run_id})
                self.assertEqual(sum(r['status']=='ok' for r in rows),2)
                self.assertEqual(sum(bool(r['attempt_archive']) for r in rows),1)

    def test_principle_validation(self):
        valid={'task1':{'priority':'专业能力信息','weight_ability':60,'weight_morality':40,'importance_ability':5,'importance_morality':3,'reason':'a'},
               'task2':{'priority':'私人道德信息','weight_ability':50,'weight_morality':50,'importance_ability':4,'importance_morality':4,'reason':'b'}}
        self.assertEqual(hr.check_response('principles',json.dumps(valid)),valid)
        valid['task2']['weight_morality']=60
        with self.assertRaisesRegex(ValueError,'权重'):
            hr.check_response('principles',json.dumps(valid))

    def test_score_validation(self):
        obj={'education_fit':3,'work_experience':3,'professional_skills':3,'accomplishments':3,
             'overall_suitability':3,'interview_probability':65,'reason':'专业证据'}
        self.assertEqual(hr.check_response('abc',json.dumps(obj)),obj)
        obj['education_fit']=8
        with self.assertRaisesRegex(ValueError,'整数'):
            hr.check_response('abc',json.dumps(obj))

    def test_job_materials_and_abc_blinding(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'occupations'
            morale=Path(tmp)/'morality'
            d=source/'software_developer'
            (d/'onet').mkdir(parents=True)
            (d/'jd').mkdir()
            (d/'resumes/approved').mkdir(parents=True)
            (morale/'approved').mkdir(parents=True)
            (d/'onet/profile.txt').write_text('O*NET Tasks: write software code. Knowledge: programming.'*4,encoding='utf-8')
            (d/'job_setup.json').write_text(json.dumps({'job_title':'后端工程师','company_profile':'虚构软件公司','job_level':'初级'}),encoding='utf-8')
            (d/'jd/approved.txt').write_text('招聘后端工程师，要求按专业任务开发程序、进行软件测试。'*4,encoding='utf-8')
            (d/'resumes/approved/R01.txt').write_text('简历 R01，软件开发工程师，负责专业程序开发和测试。'*4,encoding='utf-8')
            (morale/'approved/F_001.json').write_text(json.dumps({
                'pair_id':'F_001','foundation':'fairness',
                'neutral':'在休息日去书店阅读并购买一本小说。',
                'negative':'在休息日故意插队并嘲笑他人的正常排队。'
            },ensure_ascii=False),encoding='utf-8')
            with patch.object(hr,'SOURCES',source),patch.object(hr,'MORALS',morale):
                for kind in hr.TASK_TO_PROFILE:
                    for task in hr.make_tasks(kind,Args(),self.occ,self.config):
                        self.assertEqual(len(task['messages']),1,kind)
                        self.assertEqual(task['messages'][0]['role'],'user',kind)
                        self.assertTrue(task['messages'][0]['content'].strip(),kind)
                tasks=hr.make_tasks('abc',Args(),self.occ,self.config)
                self.assertEqual(len(tasks),3)
                by={t['metadata']['condition']:t for t in tasks}
                self.assertEqual(set(by),{'A','B','C'})
                rubric=hr.read_prompt('experiments/score_rubric.txt')
                for task in tasks:
                    self.assertEqual(task['messages'][0]['content'].count(rubric),1)
                au=by['A']['messages'][0]['content']
                bu=by['B']['messages'][0]['content']
                cu=by['C']['messages'][0]['content']
                self.assertNotIn('背景调查补充信息',au)
                self.assertIn('背景调查补充信息',bu)
                self.assertEqual(bu.replace('在休息日去书店阅读并购买一本小说。','STORY'),
                                 cu.replace('在休息日故意插队并嘲笑他人的正常排队。','STORY'))
                self.assertNotIn('实验研究',bu)
                self.assertNotIn('实验研究',cu)
                checks=hr.make_tasks('moral-check',Args(),self.occ,self.config)
                self.assertEqual(len(checks),2)
                for t in checks:
                    user=t['messages'][0]['content']
                    self.assertNotIn('F_001',user)
                    self.assertNotIn('fairness',user)
                rel=hr.make_tasks('moral-relevance',Args(),self.occ,self.config)
                self.assertEqual(len(rel),2)
                self.assertIn('招聘后端工程师',rel[0]['messages'][0]['content'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
