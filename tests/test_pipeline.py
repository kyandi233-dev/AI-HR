"""Offline checks: mock network responses; use isolated temporary results."""
import contextlib
import copy
import csv
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from hrpilot_core import common as c, api, storage, batch, exports, migration, cli, tasks, onet


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        shutil.copytree(ROOT/'prompts',self.root/'prompts')
        shutil.copytree(ROOT/'config',self.root/'config')
        self.patch=patch.object(c,'ROOT',self.root); self.patch.start()
        self.settings=c.load_json(self.root/'config/settings.json')
        self.occupations=c.load_json(self.root/'config/occupations.json')
        self.args=SimpleNamespace(task='principles',occupation=None,occupations=[],foundation='fairness',
                                  count=1,start_index=1,repeat=1,run_id='test01',stage='pilot',source='approved',retry_failed=False)
        self.stdout=io.StringIO()
        self.redirect=contextlib.redirect_stdout(self.stdout); self.redirect.__enter__()

    def tearDown(self):
        self.redirect.__exit__(None,None,None); self.patch.stop(); self.tmp.cleanup()

    def answer(self):
        return {q:{'priority':'专业能力信息','weight_ability':60,'weight_morality':40,
                   'importance_ability':5,'importance_morality':3,'reason':'测试理由'} for q in ['task1','task2']}

    def response(self,answer=None,finish='stop'):
        content=json.dumps(self.answer() if answer is None else answer,ensure_ascii=False)
        raw={'id':'test-response','model':'returned-model','usage':{'prompt_tokens':10,'completion_tokens':20,'total_tokens':30},
             'choices':[{'finish_reason':finish,'message':{'content':content}}]}
        return SimpleNamespace(id=raw['id'],model=raw['model'],system_fingerprint='test-fingerprint',
                               choices=[SimpleNamespace(finish_reason=finish,message=SimpleNamespace(content=content))],
                               model_dump=lambda **kw:copy.deepcopy(raw))

    def make(self,kind='principles'):
        return tasks.make_tasks(kind,self.args,self.occupations,self.settings)

    def materials(self):
        self.args.occupation='software_developer'; self.args.occupations=['software_developer']
        d=c.job_files(self.args.occupation)
        for path,content in [(d['profile'],'O*NET Tasks: write software code. Knowledge: programming.'*4),
                             (d['jd'],'招聘后端工程师，要求按专业任务开发程序、进行软件测试。'*4),
                             (d['resumes']/'R01.txt','简历 R01，软件开发工程师，负责专业程序开发和测试。'*4)]:
            path.parent.mkdir(parents=True,exist_ok=True); path.write_text(content,encoding='utf-8')
        storage.write_json(d['setup'],{'job_title':'后端工程师','company_profile':'虚构软件公司','job_level':'初级'})
        storage.write_json(self.root/'materials/morality/approved/F_001.json',{
            'pair_id':'F_001','foundation':'fairness','neutral':'在休息日去书店阅读并购买一本小说。',
            'negative':'在休息日故意插队并嘲笑他人的正常排队。'})

    def test_100_trials_balanced_reproducible_and_stateless(self):
        self.args.repeat=25
        built=self.make()
        self.assertEqual(len(built),100)
        self.assertEqual(built,self.make())
        for i in range(0,100,4):
            self.assertEqual({t['metadata']['condition'] for t in built[i:i+4]},{'M12','M21','A12','A21'})
        for t in built:
            self.assertEqual(len(t['messages']),1); self.assertEqual(t['messages'][0]['role'],'user')
            self.assertEqual(t['metadata']['repeat'],int(t['task_id'].split('_T')[1]))
            self.assertNotIn('软件开发',t['messages'][0]['content'])
        self.assertEqual(len({id(t['messages']) for t in built}),100)

    def test_actual_sdk_call_has_no_history_or_automatic_retry(self):
        seen=[]
        class FakeClient:
            def __init__(fake,**kw):
                self.assertEqual(kw['max_retries'],0)
                fake.chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw:seen.append(copy.deepcopy(kw))))
        with patch.dict(sys.modules,{'openai':SimpleNamespace(OpenAI=FakeClient)}),patch.dict(os.environ,{'DEEPSEEK_API_KEY':'fake'}):
            for t in self.make(): api.api_request(self.settings,t)
        self.assertEqual(len(seen),4)
        for req in seen:
            self.assertEqual(len(req['messages']),1)
            self.assertEqual(req['extra_body'],{'thinking':{'type':'disabled'}})
            self.assertEqual(req['temperature'],0)

    def test_one_command_100_requests_200_jsons_readable_csv_and_resume(self):
        cmd=['run','--task','principles','--run-id','test01','--repeat','25','--stage','main','--execute']
        with patch.object(storage,'api_request',return_value=(self.response(),{})) as call,patch.object(cli.time,'sleep'),patch.dict(os.environ,{'DEEPSEEK_API_KEY':'fake'}):
            self.assertEqual(cli.main(cmd),0)
            self.assertEqual(call.call_count,100)
            self.assertEqual(cli.main(cmd),0)
            self.assertEqual(call.call_count,100)
        base=self.root/'results/principles/test01'
        self.assertEqual(len(list(base.glob('*.input.json'))),100)
        self.assertEqual(len(list(base.glob('*.output.json'))),100)
        rows=self.csv(base/'results.csv')
        self.assertEqual(len(rows),100)
        self.assertEqual(rows[0]['task1_weight_ability'],'60')
        self.assertEqual(rows[0]['temperature'],'0.0')
        self.assertEqual(rows[0]['requested_model'],'deepseek-flash')
        self.assertEqual(rows[0]['returned_model'],'returned-model')
        self.assertNotIn('result_task1',rows[0])
        self.assertFalse((self.root/'results/all_results.csv').exists())

    def csv(self,path):
        with path.open(encoding='utf-8-sig',newline='') as stream: return list(csv.DictReader(stream))

    def test_optional_limit_counts_only_new_requests(self):
        cmd=['run','--task','principles','--repeat','25','--run-id','test01','--limit','12','--execute']
        with patch.object(storage,'api_request',return_value=(self.response(),{})) as call,patch.object(cli.time,'sleep'),patch.dict(os.environ,{'DEEPSEEK_API_KEY':'fake'}):
            cli.main(cmd); cli.main(cmd)
            self.assertEqual(call.call_count,24)
        self.assertEqual(len(self.csv(self.root/'results/principles/test01/results.csv')),24)

    def test_failures_interruption_and_manual_retry_preserve_every_attempt(self):
        t=self.make()[0]
        with patch.object(storage,'api_request',side_effect=RuntimeError('network failure')):
            self.assertEqual(storage.record_task(t,self.settings,self.args),'error')
        base=storage.path_for(t,'test01')
        first=c.load_json(next(base.glob('*.input.json')))
        with patch.object(storage,'api_request') as call:
            self.assertEqual(storage.record_task(t,self.settings,self.args),'skip'); call.assert_not_called()
        self.args.retry_failed=True
        with patch.object(storage,'api_request',return_value=(self.response(),{})) as call:
            self.assertEqual(storage.record_task(t,self.settings,self.args),'ok')
            self.assertEqual(storage.record_task(t,self.settings,self.args),'skip')
            self.assertEqual(call.call_count,1)
        self.assertEqual(len(list(base.glob('*.input.json'))),2)
        self.assertEqual(c.load_json(next(base.glob('*_a01.input.json'))),first)
        t2=self.make()[1]; self.args.retry_failed=False
        storage.write_json(base/(t2['task_id']+'_a01.input.json'),{'task_id':t2['task_id'],'attempt':1,'request':storage.request_for(t2,self.settings)})
        self.assertFalse(storage.pending(t2,self.settings,self.args))
        changed={**t,'messages':[{'role':'user','content':'changed'}]}
        with self.assertRaisesRegex(ValueError,'输入已变化'): storage.pending(changed,self.settings,self.args)

    def test_malformed_and_truncated_outputs_keep_raw_but_no_analysis_values(self):
        self.args.repeat=2
        for t,resp in zip(self.make()[:2],[self.response({'task1':{}}),self.response(finish='length')]):
            with patch.object(storage,'api_request',return_value=(resp,{})):
                self.assertEqual(storage.record_task(t,self.settings,self.args),'error')
            out=c.load_json(storage.path_for(t,'test01')/(t['task_id']+'_a01.output.json'))
            self.assertIsNotNone(out['raw_response']); self.assertIsNone(out['parsed'])

    def test_freeze_rejects_parameter_changes_but_not_export_provenance(self):
        built=self.make(); batch.freeze(built,self.settings,self.args)
        with patch.object(c,'program_sha256',return_value='export-only-change'):
            batch.freeze(built,self.settings,self.args)
        changed=copy.deepcopy(self.settings); changed['profiles']['evaluation']['temperature']=1
        with self.assertRaisesRegex(ValueError,'批次计划'): batch.freeze(built,changed,self.args)

    def test_dry_run_plan_has_no_outputs_and_no_occupation_registry_dependency(self):
        (self.root/'config/occupations.json').unlink()
        plan=self.root/'config/batches/principles_100.json'
        with patch.object(storage,'api_request') as call:
            self.assertEqual(cli.main(['run','--batch',str(plan)]),0); call.assert_not_called()
        self.assertIn('计划=100',self.stdout.getvalue())
        self.assertFalse((self.root/'results').exists())

    def test_aggregates_never_mix_task_types_or_duplicate_on_export(self):
        t=self.make()[0]
        with patch.object(storage,'api_request',return_value=(self.response(),{})):
            storage.record_task(t,self.settings,self.args)
        batch.freeze(self.make(),self.settings,self.args)
        other=copy.deepcopy(t); other['task']='moral-check'; other['task_id']='CHECK01'
        other['metadata']={'pair_id':'PAIR01','background_type':'neutral'}
        self.args.task='moral-check'
        resp=self.response({'moral_valence':4,'comprehensibility':7,'naturalness':7,'moral_foundations':[]})
        with patch.object(storage,'api_request',return_value=(resp,{})):
            storage.record_task(other,self.settings,self.args)
        batch.freeze([other],self.settings,self.args)
        exports.export_results(); exports.export_results()
        principle=self.csv(self.root/'results/principles/principles_all_results.csv')
        moral=self.csv(self.root/'results/moral_check/moral_check_all_results.csv')
        self.assertEqual([r['task'] for r in principle],['principles'])
        self.assertEqual([r['task'] for r in moral],['moral-check'])

    def test_job_builders_and_blinding_and_missing_draft_directories(self):
        self.materials()
        for kind in c.TASK_TO_PROFILE:
            for t in self.make(kind): self.assertEqual(len(t['messages']),1)
        by={t['metadata']['condition']:t['messages'][0]['content'] for t in self.make('abc')}
        self.assertNotIn('背景调查补充信息',by['A'])
        self.assertEqual(by['B'].replace('在休息日去书店阅读并购买一本小说。','STORY'),
                         by['C'].replace('在休息日故意插队并嘲笑他人的正常排队。','STORY'))
        for t in self.make('moral-check'):
            self.assertNotIn('F_001',t['messages'][0]['content']); self.assertNotIn('fairness',t['messages'][0]['content'])
        t=self.make('resume')[0]
        with patch.object(storage,'api_request',return_value=(self.response(),{})):
            self.assertEqual(storage.record_task(t,self.settings,self.args),'ok')
        self.assertTrue((c.job_files('software_developer')['drafts']/'R01.txt').exists())

    def test_multi_occupation_batch_selection_preserves_registry(self):
        self.materials()
        source=self.root/'materials/occupations/software_developer'
        shutil.copytree(source,self.root/'materials/occupations/logistics_analyst')
        registry=(self.root/'config/occupations.json').read_bytes()
        plan=self.root/'config/batches/jobs.json'
        storage.write_json(plan,{'task':'baseline','run_id':'jobs01','stage':'main','repeat':2,
                                 'occupations':['software_developer','logistics_analyst']})
        self.assertEqual(cli.main(['run','--batch',str(plan)]),0)
        self.assertIn('计划=4',self.stdout.getvalue())
        self.assertEqual((self.root/'config/occupations.json').read_bytes(),registry)

    def test_jsonl_migration_preserves_raw_input_answers_failures_and_originals(self):
        base=self.root/'results/principles/test01'; base.mkdir(parents=True)
        t=self.make()[0]; request=storage.request_for(t,self.settings)
        old={'task':'principles','run_id':'test01','occupation':None}
        storage.write_json(base/'manifest.json',old)
        storage.write_json(base/'run_summary.json',{'stage':'pilot'})
        identity={'task_id':t['task_id'],'attempt':1}
        data={'requests.jsonl':[{**identity,'request':request}],
              'responses.jsonl':[{**identity,'raw_response':{'model':'original'},'answer':'原始回答'}],
              'records.jsonl':[{**identity,'task':'principles','context':t['metadata'],'status':'ok',
                                'timestamp_utc':'2026-11-16T00:00:00Z','parsed':self.answer()}]}
        original={}
        for name,rows in data.items():
            (base/name).write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows),encoding='utf-8')
            original[name]=(base/name).read_bytes()
        with patch.object(storage,'api_request') as call:
            migration.migrate_results(); migration.migrate_results(); call.assert_not_called()
        inp=c.load_json(next(base.glob('*.input.json')))
        out=c.load_json(next(base.glob('*.output.json')))
        self.assertEqual(inp['request'],json.loads(json.dumps(request)))
        self.assertEqual(out['answer'],'原始回答'); self.assertEqual(out['parsed'],self.answer())
        self.assertEqual(out['timestamp_utc'],'2026-11-16T00:00:00Z')
        for name,value in original.items(): self.assertEqual((base/'legacy'/name).read_bytes(),value)
        self.assertEqual(len(self.csv(base/'results.csv')),1)

    def test_validation_and_redaction(self):
        self.assertEqual(__import__('hrpilot_core.validation',fromlist=['check_response']).check_response('principles',json.dumps(self.answer())),self.answer())
        broken=self.answer(); broken['task1']['weight_ability']=101
        with self.assertRaises(ValueError):
            __import__('hrpilot_core.validation',fromlist=['check_response']).check_response('principles',json.dumps(broken))
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'test-secret-key'}):
            self.assertNotIn('test-secret-key',c.safe_error_message('Your api key: test-secret-key is invalid'))
        self.settings['profiles']['evaluation']['thinking']='enabled'
        with self.assertRaises(ValueError): api.request_kwargs(self.settings,self.make()[0])

    def test_onet_fresh_clone_creates_source_directory_without_approving_it(self):
        import bs4
        response=SimpleNamespace(text='<html><main>'+('Occupational tasks and knowledge. '*100)+'</main></html>',
                                 content=b'original-html',status_code=200,raise_for_status=lambda:None)
        with patch('requests.get',return_value=response):
            onet.fetch_onet(SimpleNamespace(occupation='software_developer',execute=True),self.occupations)
        folder=c.job_files('software_developer')['profile'].parent
        self.assertTrue((folder/'source_details.txt').exists()); self.assertFalse((folder/'profile.txt').exists())
        self.assertFalse(c.load_json(folder/'source_metadata.json')['researcher_reviewed'])


if __name__=='__main__': unittest.main(verbosity=2)
