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
sys.path.insert(0,str(ROOT))
from shared import common as c, api, storage, batch, exports, migration, cli, tasks
from material_preparation import fetch_occupations as onet


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        for folder in ['material_preparation','experiments/exp_1_principles',
                       'experiments/exp_2_material_evaluation','experiments/exp_3_hiring']:
            for name in ['prompts','config']:
                source=ROOT/folder/name
                if source.exists(): shutil.copytree(source,self.root/folder/name)
        self.patch=patch.object(c,'ROOT',self.root); self.patch.start()
        self.settings=c.load_settings('principles')
        self.settings['profiles'].update(c.load_settings('jd')['profiles'])
        self.occupations=c.load_json(self.root/'material_preparation/config/occupations.json')
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
        storage.write_json(self.root/'material_preparation/approved/morality/F_001.json',{
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
            def __enter__(fake): return fake
            def __exit__(fake,*exc): return False
        with patch.dict(sys.modules,{'openai':SimpleNamespace(OpenAI=FakeClient)}),patch.dict(os.environ,{'DEEPSEEK_API_KEY':'fake'}):
            for t in self.make(): api.api_request(self.settings,t)
        self.assertEqual(len(seen),4)
        for req in seen:
            self.assertEqual(len(req['messages']),1)
            self.assertEqual(req['extra_body'],{'thinking':{'type':'disabled'}})
            self.assertEqual(req['temperature'],self.settings['profiles']['evaluation']['temperature'])

    def test_one_command_100_requests_200_jsons_readable_csv_and_resume(self):
        cmd=['run','--task','principles','--run-id','test01','--repeat','25','--stage','main','--execute']
        with patch.object(storage,'api_request',return_value=(self.response(),{})) as call,patch.dict(os.environ,{'DEEPSEEK_API_KEY':'fake'}):
            self.assertEqual(cli.main(cmd),0)
            self.assertEqual(call.call_count,100)
            self.assertEqual(cli.main(cmd),0)
            self.assertEqual(call.call_count,100)
        base=self.root/'experiments/exp_1_principles/results/test01'
        records=base/'records'
        self.assertTrue(records.is_dir())
        self.assertEqual(len(list(records.glob('*.input.json'))),100)
        self.assertEqual(len(list(records.glob('*.output.json'))),100)
        self.assertFalse(list(base.glob('*.input.json')))
        self.assertTrue((base/'batch.json').is_file())
        rows=self.csv(base/'results.csv')
        self.assertEqual(len(rows),100)
        self.assertEqual(rows[0]['task1_weight_ability'],'60')
        self.assertEqual(float(rows[0]['temperature']),self.settings['profiles']['evaluation']['temperature'])
        self.assertEqual(rows[0]['requested_model'],'deepseek-flash')
        self.assertEqual(rows[0]['returned_model'],'returned-model')
        self.assertNotIn('result_task1',rows[0])
        self.assertFalse((self.root/'results/all_results.csv').exists())

    def csv(self,path):
        with path.open(encoding='utf-8-sig',newline='') as stream: return list(csv.DictReader(stream))

    def test_optional_limit_counts_only_new_requests(self):
        cmd=['run','--task','principles','--repeat','25','--run-id','test01','--limit','12','--execute']
        with patch.object(storage,'api_request',return_value=(self.response(),{})) as call,patch.dict(os.environ,{'DEEPSEEK_API_KEY':'fake'}):
            cli.main(cmd); cli.main(cmd)
            self.assertEqual(call.call_count,24)
        self.assertEqual(len(self.csv(self.root/'experiments/exp_1_principles/results/test01/results.csv')),24)

    def test_failures_interruption_and_manual_retry_preserve_every_attempt(self):
        t=self.make()[0]
        with patch.object(storage,'api_request',side_effect=RuntimeError('network failure')):
            self.assertEqual(storage.record_task(t,self.settings,self.args),'error')
        base=storage.path_for(t,'test01')
        records=storage.records_dir(base)
        first=c.load_json(next(records.glob('*.input.json')))
        with patch.object(storage,'api_request') as call:
            self.assertEqual(storage.record_task(t,self.settings,self.args),'skip'); call.assert_not_called()
        self.args.retry_failed=True
        with patch.object(storage,'api_request',return_value=(self.response(),{})) as call:
            self.assertEqual(storage.record_task(t,self.settings,self.args),'ok')
            self.assertEqual(storage.record_task(t,self.settings,self.args),'skip')
            self.assertEqual(call.call_count,1)
        self.assertEqual(len(list(records.glob('*.input.json'))),2)
        self.assertEqual(c.load_json(next(records.glob('*_a01.input.json'))),first)
        t2=self.make()[1]; self.args.retry_failed=False
        storage.write_json(records/(t2['task_id']+'_a01.input.json'),{'task_id':t2['task_id'],'attempt':1,'request':storage.request_for(t2,self.settings)})
        self.assertFalse(storage.pending(t2,self.settings,self.args))
        changed={**t,'messages':[{'role':'user','content':'changed'}]}
        with self.assertRaisesRegex(ValueError,'输入已变化'): storage.pending(changed,self.settings,self.args)

    def test_malformed_and_truncated_outputs_keep_raw_but_no_analysis_values(self):
        self.args.repeat=2
        for t,resp in zip(self.make()[:2],[self.response({'task1':{}}),self.response(finish='length')]):
            with patch.object(storage,'api_request',return_value=(resp,{})):
                self.assertEqual(storage.record_task(t,self.settings,self.args),'error')
            out=c.load_json(storage.records_dir(storage.path_for(t,'test01'))/(t['task_id']+'_a01.output.json'))
            self.assertIsNotNone(out['raw_response']); self.assertIsNone(out['parsed'])

    def test_freeze_rejects_parameter_changes_but_not_export_provenance(self):
        built=self.make(); batch.freeze(built,self.settings,self.args)
        with patch.object(c,'program_sha256',return_value='export-only-change'):
            batch.freeze(built,self.settings,self.args)
        changed=copy.deepcopy(self.settings)
        changed['profiles']['evaluation']['temperature']=0 if self.settings['profiles']['evaluation']['temperature']!=0 else 1
        with self.assertRaisesRegex(ValueError,'批次计划'): batch.freeze(built,changed,self.args)

    def test_dry_run_plan_has_no_outputs_and_no_occupation_registry_dependency(self):
        (self.root/'material_preparation/config/occupations.json').unlink()
        plan=self.root/'experiments/exp_1_principles/config/principles_100.json'
        with patch.object(storage,'api_request') as call:
            self.assertEqual(cli.main(['run','--batch',str(plan)]),0); call.assert_not_called()
        self.assertIn('计划=100',self.stdout.getvalue())
        self.assertFalse(any(path.exists() for path in storage.result_roots()))

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
        principle=self.csv(self.root/'experiments/exp_1_principles/results/principles_all_results.csv')
        moral=self.csv(self.root/'experiments/exp_2_material_evaluation/results/moral_check_all_results.csv')
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
        source=self.root/'material_preparation/approved/occupations/software_developer'
        shutil.copytree(source,self.root/'material_preparation/approved/occupations/logistics_analyst')
        registry=(self.root/'material_preparation/config/occupations.json').read_bytes()
        plan=self.root/'experiments/exp_3_hiring/config/jobs.json'
        from shared.materials import create_snapshot
        create_snapshot('exp_3_hiring','test_materials',['software_developer','logistics_analyst'],execute=True)
        storage.write_json(plan,{'task':'baseline','run_id':'jobs01','stage':'main','repeat':2,
                                 'occupations':['software_developer','logistics_analyst'],'materials_version':'test_materials'})
        self.assertEqual(cli.main(['run','--batch',str(plan)]),0)
        self.assertIn('计划=4',self.stdout.getvalue())
        self.assertEqual((self.root/'material_preparation/config/occupations.json').read_bytes(),registry)

    def test_jsonl_migration_preserves_raw_input_answers_failures_and_originals(self):
        base=self.root/'experiments/exp_1_principles/results/test01'; base.mkdir(parents=True)
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
        self.assertEqual(__import__('shared.validation',fromlist=['check_response']).check_response('principles',json.dumps(self.answer())),self.answer())
        broken=self.answer(); broken['task1']['weight_ability']=101
        with self.assertRaises(ValueError):
            __import__('shared.validation',fromlist=['check_response']).check_response('principles',json.dumps(broken))
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'test-secret-key'}):
            self.assertNotIn('test-secret-key',c.safe_error_message('Your api key: test-secret-key is invalid'))
        self.settings['profiles']['evaluation']['thinking']='enabled'
        with self.assertRaises(ValueError): api.request_kwargs(self.settings,self.make()[0])

    def test_onet_fresh_clone_creates_source_directory_without_approving_it(self):
        import bs4
        html='<html><main><h1>Software Developers 15-1252.00</h1>'+('Occupational tasks and knowledge. '*100)+'</main></html>'
        response=SimpleNamespace(text=html,
                                 content=html.encode(),status_code=200,raise_for_status=lambda:None)
        with patch('requests.get',return_value=response):
            onet.fetch_onet(SimpleNamespace(occupation='software_developer',execute=True),self.occupations)
        folder=c.job_files('software_developer')['source']
        self.assertTrue((folder/'source_details.txt').exists()); self.assertFalse(c.job_files('software_developer')['profile'].exists())
        self.assertFalse(c.load_json(folder/'source_metadata.json')['researcher_reviewed'])

    def test_all_original_requests_match_before_reorganization(self):
        self.materials()
        golden=c.load_json(ROOT/'tests/fixtures/tasks_before_reorganization.json')
        for kind,expected in golden.items():
            original_settings=copy.deepcopy(self.settings)
            profile=original_settings['profiles'][c.TASK_TO_PROFILE[kind]]
            # Replay historical requests with their historical parameters.
            profile['temperature']=expected[0]['kwargs']['temperature']
            actual=[{'task':t,'kwargs':api.request_kwargs(original_settings,t)} for t in self.make(kind)]
            self.assertEqual(json.loads(json.dumps(actual)),expected,kind)

    def test_every_current_task_uses_temperature_one_and_original_token_limit(self):
        self.materials()
        limits={'generation':3000,'evaluation':2200,'material_review':1600}
        for kind in c.TASK_TO_PROFILE:
            settings=c.load_settings(kind)
            for task in self.make(kind):
                kwargs=api.request_kwargs(settings,task)
                self.assertEqual(kwargs['temperature'],1,kind)
                self.assertEqual(kwargs['max_tokens'],limits[c.TASK_TO_PROFILE[kind]],kind)
                self.assertEqual(kwargs['extra_body']['thinking']['type'],'disabled',kind)

    def test_snapshot_preview_copy_isolation_and_tampering(self):
        from shared.materials import create_snapshot, verified_snapshot
        self.materials()
        target=create_snapshot('exp_2_material_evaluation','v1',['software_developer'],True)
        self.assertFalse(target.exists())
        target=create_snapshot('exp_2_material_evaluation','v1',['software_developer'],True,execute=True)
        manifest=c.load_json(target/'manifest.json')
        (target/'README.md').write_text('材料版本说明',encoding='utf-8')
        verified_snapshot('moral-check','v1')
        self.assertTrue(all('drafts' not in name for name in manifest['files']))
        original=(target/'occupations/software_developer/resumes/R01.txt').read_bytes()
        c.job_files('software_developer')['resumes'].joinpath('R01.txt').write_text('later changes',encoding='utf-8')
        self.assertEqual((target/'occupations/software_developer/resumes/R01.txt').read_bytes(),original)
        other=create_snapshot('exp_3_hiring','v1',['software_developer'],True,
                              'exp_2_material_evaluation','v1',execute=True)
        self.assertEqual(c.load_json(other/'manifest.json')['files'],manifest['files'])
        with self.assertRaisesRegex(ValueError,'已存在'):
            create_snapshot('exp_2_material_evaluation','v1',['software_developer'],True,execute=True)
        (target/'morality/F_001.json').write_text('{}',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'内容发生变化'):
            verified_snapshot('moral-check','v1')
        verified_snapshot('abc','v1')

    def test_experiment_materials_are_required_and_recorded_before_api(self):
        from shared.materials import create_snapshot
        self.materials()
        cmd=['run','--task','abc','--occupation','software_developer','--run-id','hiring01']
        with patch.object(storage,'api_request') as call:
            with self.assertRaisesRegex(ValueError,'materials-version'): cli.main(cmd)
            call.assert_not_called()
        target=create_snapshot('exp_3_hiring','v1',['software_developer'],True,execute=True)
        cmd.extend(['--materials-version','v1','--execute'])
        answer={k:3 for k in ['education_fit','work_experience','professional_skills','accomplishments','overall_suitability']}
        answer.update(interview_probability=60,reason='测试理由')
        with patch.object(storage,'api_request',return_value=(self.response(answer),{})) as call,patch.dict(os.environ,{'DEEPSEEK_API_KEY':'fake'}):
            self.assertEqual(cli.main(cmd),0)
            self.assertEqual(call.call_count,3)
            self.assertEqual(cli.main(cmd),0)
            self.assertEqual(call.call_count,3)
        path=self.root/'experiments/exp_3_hiring/results/abc/software_developer/hiring01'
        self.assertEqual(c.load_json(path/'batch.json')['materials_snapshot']['version'],'v1')
        self.assertTrue(all(row['materials_version']=='v1' for row in self.csv(path/'results.csv')))
        (target/'morality/extra.json').write_text('{}',encoding='utf-8')
        with patch.object(storage,'api_request') as call:
            with self.assertRaisesRegex(ValueError,'文件清单'): cli.main(cmd)
            call.assert_not_called()

    def test_preparation_and_experiment_two_stay_separate(self):
        self.materials()
        shutil.copytree(self.root/'material_preparation/approved/morality',
                        self.root/'material_preparation/drafts/morality')
        self.args.source='drafts'
        review=self.make('moral-review')[0]
        measured=self.make('moral-check')[0]
        self.assertIn('material_preparation',str(storage.path_for(review,'test01')))
        self.assertIn('exp_2_material_evaluation',str(storage.path_for(measured,'test01')))
        self.assertEqual(review['messages'],measured['messages'])
        # Resume quality review has no unused profile dependency.
        c.job_files('software_developer')['profile'].unlink()
        self.args.source='approved'
        self.assertEqual(len(self.make('resume-review')),1)

    def test_direct_entries_work_from_another_directory_and_are_scoped(self):
        import subprocess
        entries=['experiments/exp_1_principles/run.py','experiments/exp_2_material_evaluation/evaluate_morality.py',
                 'experiments/exp_2_material_evaluation/evaluate_relevance.py',
                 'experiments/exp_2_material_evaluation/snapshot_materials.py',
                 'experiments/exp_3_hiring/run.py','experiments/exp_3_hiring/snapshot_materials.py',
                 'material_preparation/fetch_occupations.py','material_preparation/generate_jd.py',
                 'material_preparation/generate_resumes.py','material_preparation/generate_morality.py',
                 'material_preparation/review_resumes.py','material_preparation/review_morality.py']
        for entry in entries:
            result=subprocess.run([sys.executable,'-B',str(ROOT/entry),'--help'],cwd=self.root,capture_output=True)
            self.assertEqual(result.returncode,0,(entry,result.stderr))
        with patch.object(sys,'argv',['run.py','--batch',str(self.root/'experiments/exp_3_hiring/config/hiring_example.json')]),patch.object(storage,'api_request') as call:
            self.assertEqual(cli.task_main('principles'),2)
            call.assert_not_called()

    def test_missing_sdk_stops_before_freezing_or_recording_a_batch(self):
        cmd=['run','--task','principles','--run-id','missing_sdk','--execute']
        with patch.dict(sys.modules,{'openai':None}),patch.dict(os.environ,{'DEEPSEEK_API_KEY':'fake'}),patch.object(storage,'api_request') as call:
            with self.assertRaises(ImportError): cli.main(cmd)
            call.assert_not_called()
        self.assertFalse(any(path.exists() for path in storage.result_roots()))

    def test_default_principles_plan_is_pilot_with_100_requests(self):
        plan=c.load_json(self.root/'experiments/exp_1_principles/config/principles_100.json')
        self.assertEqual(plan['stage'],'pilot')
        self.assertEqual(plan['repeat'],25)
        self.assertIn('pilot',plan['run_id'])
        with patch.object(sys,'argv',['run.py']),patch.object(storage,'api_request') as call:
            self.assertEqual(cli.task_main('principles',default_batch='principles_100.json'),0)
            call.assert_not_called()
        self.assertIn('阶段=pilot',self.stdout.getvalue())
        self.assertIn('计划=100',self.stdout.getvalue())
        self.assertIn('温度=1.0',self.stdout.getvalue())
        self.assertIn('max_tokens=2200',self.stdout.getvalue())
        self.assertFalse(any(path.exists() for path in storage.result_roots()))

    def test_completed_batch_needs_no_api_key_when_no_new_requests_remain(self):
        cmd=['run','--task','principles','--run-id','finished01','--execute']
        with patch.object(storage,'api_request',return_value=(self.response(),{})) as call,patch.dict(os.environ,{'DEEPSEEK_API_KEY':'fake'}):
            self.assertEqual(cli.main(cmd),0)
            self.assertEqual(call.call_count,4)
        with patch.object(storage,'api_request') as call,patch.dict(os.environ,{'DEEPSEEK_API_KEY':''}):
            self.assertEqual(cli.main(cmd),0)
            call.assert_not_called()

    def test_material_generation_has_no_arbitrary_count_or_text_length_limit(self):
        self.materials()
        paths=c.job_files('software_developer')
        paths['profile'].write_text('职业任务',encoding='utf-8')
        paths['jd'].write_text('岗位职责',encoding='utf-8')
        (paths['resumes']/'R01.txt').write_text('专业简历',encoding='utf-8')
        self.assertEqual(c.read_job('software_developer',require_jd=True)['jd'],'岗位职责')
        self.assertEqual(c.list_resumes('software_developer')[0][1],'专业简历')
        self.args.count=100
        self.assertEqual(len(self.make('resume')),100)
        self.assertEqual(len(self.make('moral-generate')),100)
        batch.validate_run_id('pilot_'+('x'*80))

    def test_source_changes_do_not_block_resume_or_rewrite_batch_manifest(self):
        built=self.make()
        batch.freeze(built,self.settings,self.args)
        path=storage.path_for(built[0],self.args.run_id)/'batch.json'
        original=path.read_bytes()
        manifest=batch.manifest_for(built,self.settings,self.args)
        manifest['protocol']={name:'changed-source' for name in manifest['protocol']}
        manifest['concurrency']=4
        with patch.object(batch,'manifest_for',return_value=manifest):
            batch.freeze(built,self.settings,self.args)
        self.assertEqual(path.read_bytes(),original)

    def test_api_key_file_is_reused_and_terminal_value_has_priority(self):
        path=self.root/'.env'
        path.write_text('# local settings\nDEEPSEEK_API_KEY="file-key" # comment\n',encoding='utf-8')
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':''}):
            self.assertEqual(c.load_api_key(),'file-key')
            self.assertNotIn('file-key',c.safe_error_message('invalid file-key'))
            self.assertEqual(c.load_api_key(),'file-key')
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'terminal-key'}):
            self.assertEqual(c.load_api_key(),'terminal-key')

    def test_parallel_100_requests_preserve_trial_identity_and_resume(self):
        import threading
        barrier=threading.Barrier(4,timeout=10)
        lock=threading.Lock()
        state={'active':0,'maximum':0,'calls':0}
        seen=set()
        def respond(settings,task):
            with lock:
                state['calls']+=1
                number=state['calls']
                state['active']+=1
                state['maximum']=max(state['maximum'],state['active'])
                self.assertNotIn(task['task_id'],seen)
                seen.add(task['task_id'])
            if number<=4: barrier.wait()
            with lock: state['active']-=1
            return self.response(),{}
        cmd=['run','--task','principles','--repeat','25','--run-id','parallel01','--concurrency','4','--execute']
        with patch.object(storage,'api_request',side_effect=respond),patch.dict(os.environ,{'DEEPSEEK_API_KEY':'fake'}):
            self.assertEqual(cli.main(cmd),0)
        self.assertEqual(state['calls'],100)
        self.assertEqual(state['maximum'],4)
        base=self.root/'experiments/exp_1_principles/results/parallel01'
        records=base/'records'
        inputs=list(records.glob('*.input.json'))
        self.assertEqual(len(inputs),100)
        self.assertEqual(len(list(records.glob('*.output.json'))),100)
        for path in inputs:
            inp=c.load_json(path)
            out=c.load_json(path.with_name(path.name.replace('.input.json','.output.json')))
            self.assertEqual(inp['task_id'],out['task_id'])
            self.assertEqual(inp['sequence'],out['sequence'])
            self.assertEqual(inp['concurrency'],4)
            self.assertEqual(out['status'],'ok')
        rows=self.csv(base/'results.csv')
        self.assertEqual([int(row['sequence']) for row in rows],list(range(1,101)))
        cmd[-2]='1'
        with patch.object(storage,'api_request') as call,patch.dict(os.environ,{'DEEPSEEK_API_KEY':''}):
            self.assertEqual(cli.main(cmd),0)
            call.assert_not_called()

    def test_pending_ignores_other_workers_partial_input_files(self):
        task=self.make()[0]
        base=storage.path_for(task,self.args.run_id)
        records=storage.records_dir(base)
        records.mkdir(parents=True)
        (records/'OTHER_a01.input.json').write_text('{',encoding='utf-8')
        self.assertTrue(storage.pending(task,self.settings,self.args))

    def test_blank_reason_is_error_and_question_order_is_recorded_as_warning(self):
        from shared.validation import check_response
        answer=self.answer()
        answer['task1']['reason']='   '
        with self.assertRaisesRegex(ValueError,'非空文字'):
            check_response('principles',json.dumps(answer))
        task=next(t for t in self.make() if list(t['metadata']['task_order'])==['task2','task1'])
        with patch.object(storage,'api_request',return_value=(self.response(),{})):
            self.assertEqual(storage.record_task(task,self.settings,self.args),'ok')
        output=c.load_json(next(storage.records_dir(storage.path_for(task,self.args.run_id)).glob('*.output.json')))
        self.assertEqual(list(output['parsed']),['task1','task2'])
        self.assertEqual(output['validation_warnings'],['任务键顺序与提示要求不同'])


if __name__=='__main__': unittest.main(verbosity=2)
