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

    def sample_answer(self):
        return {k:{'priority':'专业能力信息','weight_ability':60,'weight_morality':40,
                   'importance_ability':5,'importance_morality':3,'reason':'test'}
                for k in ['task1','task2']}

    def sample_response(self):
        content=json.dumps(self.sample_answer(),ensure_ascii=False)
        raw={'id':'test-response','model':'test-model','usage':{'total_tokens':42}}
        return SimpleNamespace(
            id='test-response',model='test-model',system_fingerprint=None,
            choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=content))],
            model_dump=lambda **kw:raw)

    def test_batch_jsonl_resume_retry_and_export(self):
        a=Args()
        a.repeat=2
        tasks=hr.make_tasks('principles',a,self.occ,self.config)[:2]
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(hr,'ROOT',Path(tmp)),patch.object(hr,'RESULTS',Path(tmp)/'results'):
                with patch.object(hr,'api_request',side_effect=[RuntimeError('network failure'),(self.sample_response(),{})]) as api:
                    self.assertEqual(hr.record_task(tasks[0],self.config,a),'error')
                    self.assertEqual(hr.record_task(tasks[0],self.config,a),'skip')
                    a.retry_failed=True
                    self.assertEqual(hr.record_task(tasks[0],self.config,a),'ok')
                    self.assertEqual(hr.record_task(tasks[0],self.config,a),'skip')
                    self.assertEqual(api.call_count,2)
                with patch.object(hr,'api_request',return_value=(self.sample_response(),{})):
                    self.assertEqual(hr.record_task(tasks[1],self.config,a),'ok')
                batch=hr.path_for(tasks[0],a.run_id)
                self.assertEqual(batch,hr.path_for(tasks[1],a.run_id))
                self.assertEqual(batch,Path(tmp)/'results'/'principles'/'test01')
                self.assertFalse(any(p.is_dir() for p in batch.iterdir()))
                requests=hr.read_jsonl(batch/'requests.jsonl')
                records=hr.read_jsonl(batch/'records.jsonl')
                self.assertEqual(len(requests),3)
                self.assertEqual([r['attempt'] for r in records],[1,2,1])
                self.assertEqual([r['status'] for r in records],['error','ok','ok'])
                self.assertEqual(records[1]['parsed'],self.sample_answer())
                self.assertEqual(len(hr.read_jsonl(batch/'responses.jsonl')),2)
                # Same run/task ID cannot silently reuse changed scientific input.
                changed={**tasks[0],'messages':[{'role':'user','content':'changed'}]}
                with self.assertRaisesRegex(ValueError,'已变化'):
                    hr.record_task(changed,self.config,a)
                # A request saved before a crash is not automatically charged again.
                interrupted={**requests[0],'task_id':'interrupted'}
                interrupted['request']={**interrupted['request'],'task':{**tasks[0],'task_id':'interrupted'}}
                hr.append_jsonl(batch/'requests.jsonl',interrupted)
                a.retry_failed=False
                with patch.object(hr,'api_request') as api:
                    self.assertEqual(hr.record_task(interrupted['request']['task'],self.config,a),'skip')
                    api.assert_not_called()
                hr.export_results()
                with (batch/(a.run_id+'.csv')).open(encoding='utf-8-sig',newline='') as fp:
                    rows=list(csv.DictReader(fp))
                self.assertEqual(len(rows),3)
                self.assertEqual({r['run_id'] for r in rows},{a.run_id})
                self.assertEqual(sum(r['status']=='ok' for r in rows),2)
                # Another batch must have its own CSV and join only in the global table.
                a.run_id='test02'
                with patch.object(hr,'api_request',return_value=(self.sample_response(),{})):
                    hr.record_task(tasks[0],self.config,a)
                hr.export_results()
                with (Path(tmp)/'results'/'all_results.csv').open(encoding='utf-8-sig',newline='') as fp:
                    all_rows=list(csv.DictReader(fp))
                self.assertEqual(len(all_rows),4)
                self.assertEqual({r['run_id'] for r in all_rows},{'test01','test02'})

    def test_legacy_migration_preserves_answers_requests_and_retry_history(self):
        a=Args()
        task=hr.make_tasks('principles',a,self.occ,self.config)[0]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            results=root/'results'
            legacy=results/'_principles'/'principles'/'runs'/a.run_id
            task_dir=legacy/task['task_id']
            failed=task_dir/'failed_attempts'/'2026-11-16T00-00-00'
            failed.mkdir(parents=True)
            request={'task':task,'config':self.config['profiles']['evaluation'],
                     'api_base_url':self.config['api_base_url']}
            record={'task_id':task['task_id'],'status':'ok','context':task['metadata'],
                    'timestamp_utc':'2026-11-16T00:00:01+00:00','runner_sha256':'original-program'}
            for folder,status in [(failed,'error'),(task_dir,'ok')]:
                (folder/'request.json').write_text(json.dumps(request),encoding='utf-8')
                (folder/'record.json').write_text(json.dumps({**record,'status':status}),encoding='utf-8')
            response=self.sample_response()
            (task_dir/'raw_response.json').write_text(json.dumps(response.model_dump()),encoding='utf-8')
            (task_dir/'answer.txt').write_text(response.choices[0].message.content,encoding='utf-8')
            (task_dir/'parsed.json').write_text(json.dumps(self.sample_answer()),encoding='utf-8')
            manifest={'task':'principles','run_id':a.run_id,'occupation':None,'runner_sha256':'original-program'}
            (legacy/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
            original_manifest=(legacy/'manifest.json').read_bytes()
            with patch.object(hr,'ROOT',root),patch.object(hr,'RESULTS',results),patch.object(hr,'api_request') as api:
                target=hr.migrate_legacy_batch(legacy,root/'archives')
                api.assert_not_called()
                self.assertFalse(legacy.exists())
                self.assertFalse(any(p.is_dir() for p in target.iterdir()))
                self.assertEqual((target/'manifest.json').read_bytes(),original_manifest)
                saved_request=json.loads(json.dumps(request))
                self.assertEqual([r['request'] for r in hr.read_jsonl(target/'requests.jsonl')],[saved_request,saved_request])
                records=hr.read_jsonl(target/'records.jsonl')
                self.assertEqual([r['status'] for r in records],['error','ok'])
                self.assertEqual([r['attempt'] for r in records],[1,2])
                self.assertEqual(records[1]['parsed'],self.sample_answer())
                self.assertEqual(records[1]['runner_sha256'],'original-program')
                self.assertEqual(hr.read_jsonl(target/'responses.jsonl')[0]['answer'],response.choices[0].message.content)
                self.assertEqual(len(list((root/'archives').glob('*/*.tar.gz'))),1)
                hr.export_results()
                # Conflicting destination never replaces either copy.
                legacy.mkdir(parents=True)
                (legacy/'manifest.json').write_bytes(original_manifest)
                with self.assertRaisesRegex(ValueError,'已存在'):
                    hr.migrate_legacy_batch(legacy,root/'archives')
                self.assertTrue(legacy.exists())

    def test_cli_new_batches_and_manifest_guard_without_network(self):
        a=Args()
        task=hr.make_tasks('principles',a,self.occ,self.config)[0]
        with tempfile.TemporaryDirectory() as tmp:
            results=Path(tmp)/'results'
            config=Path(tmp)/'config'
            config.mkdir()
            (config/'settings.json').write_text(json.dumps(self.config),encoding='utf-8')
            (config/'occupations.json').write_text(json.dumps(self.occ),encoding='utf-8')
            with patch.object(hr,'ROOT',Path(tmp)),patch.object(hr,'RESULTS',results),patch.object(hr,'make_tasks',return_value=[task]),patch.dict(os.environ,{'DEEPSEEK_API_KEY':'test-key'}),patch.object(hr.time,'sleep'):
                command=['run','--task','principles','--run-id','test01','--execute']
                with patch.object(hr,'api_request',return_value=(self.sample_response(),{})) as api:
                    self.assertEqual(hr.main(command),0)
                    self.assertEqual(hr.main(command),0)
                    self.assertEqual(api.call_count,1)
                batch=hr.path_for(task,'test01')
                manifest=hr.load_json(batch/'manifest.json')
                manifest['runner_sha256']='changed-program'
                (batch/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
                with patch.object(hr,'api_request') as api:
                    with self.assertRaisesRegex(ValueError,'批次清单'):
                        hr.main(command)
                    api.assert_not_called()
                old=results/'_principles'/'principles'/'runs'/'test02'
                old.mkdir(parents=True)
                (old/'manifest.json').write_text('{}',encoding='utf-8')
                with patch.object(hr,'api_request') as api:
                    with self.assertRaisesRegex(ValueError,'旧目录'):
                        hr.main(['run','--task','principles','--run-id','test02','--execute'])
                    api.assert_not_called()

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
