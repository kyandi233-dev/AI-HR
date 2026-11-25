"""New structured inputs, immutable originals, reviewer gates and exact extraction."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from openpyxl import Workbook
import unittest
import test_pipeline as pipeline
from shared import common as c, storage
from material_preparation.generation_inputs import read_occupation_data,read_jd_occupation_data,project_jd_modules,extract_jd,MARKERS
from material_preparation.generate_jd import make_tasks
from material_preparation.run_material_generation import run as generate
from material_preparation.approve_materials import approval_plan,run as approve


BODY='\r\n职位名称：软件开发人员\r\n岗位简介\n原文。\n工作职责\n1. Write software.\n任职要求\n3 年以上。\r\n'
ANSWER=MARKERS[0]+'\n原始依据。\n'+MARKERS[1]+'\n'+MARKERS[2]+BODY+MARKERS[3]+'\n'


class GenerationTests(unittest.TestCase):
    setUp=pipeline.PipelineTests.setUp
    tearDown=pipeline.PipelineTests.tearDown
    materials=pipeline.PipelineTests.materials
    def test_lossless_json_no_profile_or_setup_needed(self):
        self.materials()
        paths=c.job_files('software_developer')
        paths['profile'].unlink(); paths['setup'].unlink()
        data=c.load_json(paths['structured'])
        data['unknown_new_section']={'literal':'=原文\r\n{braces}','all_items':[1,2,3]}
        storage.write_json(paths['structured'],data)
        text,meta=read_occupation_data('software_developer')
        self.assertEqual(json.loads(text),data)
        jd_text,jd_meta=read_jd_occupation_data('software_developer')
        task=make_tasks('jd',self.args,self.occupations,self.settings)[0]
        self.assertIn(jd_text,task['messages'][0]['content'])
        self.assertNotIn('unknown_new_section',jd_text)
        self.assertNotIn('{occupation_data_json}',task['messages'][0]['content'])
        self.assertIn('Software_Developers_15-1252.00',str(paths['jd_draft']))
        self.assertEqual(task['metadata']['structured_sha256'],c.sha256(paths['structured'].read_bytes()))

    def test_module_selection_preserves_descriptions_all_records_and_prose(self):
        self.materials(); paths=c.job_files('software_developer'); data=c.load_json(paths['structured'])
        before=json.dumps(data,ensure_ascii=False)
        tasks=next(s for s in data['sections'] if s['id']=='Tasks')
        tasks['records']=[{'order':i,'kind':'table_row','group':'1','fields':[
            {'name':'Importance','value':'77','text_original':'77'},
            {'name':'Task','value':text,'text_original':text}],
            'text':'77 '+text,'links':[{'url':'https://example.test'}]} for i,text in enumerate(['Analyze data.','Identify data trends.'],1)]
        knowledge=next(s for s in data['sections'] if s['id']=='Knowledge')
        knowledge['records']=[{'order':1,'fields':[{'name':'Knowledge','value':'Computers',
                              'text_original':'Computers — Original full description. Related occupations'}]}]
        overview=next(s for s in data['sections'] if s['id']=='Overview')
        overview['source_text']='Original occupation overview, absent from navigation records.\r\n'
        data['sections'].append({'id':'WorkStyles','source_text':'Excluded module','records':[]})
        modules=c.load_json(self.root/'material_preparation/config/jd_input_modules.json')['modules']
        original=json.dumps(data,ensure_ascii=False)
        view,trace=project_jd_modules(data,modules)
        self.assertEqual(json.dumps(data,ensure_ascii=False),original)
        self.assertEqual([s['id'] for s in view['sections']],modules)
        selected={s['id']:s for s in view['sections']}
        self.assertEqual(len(selected['Tasks']['records']),2)
        self.assertNotIn('text_original',selected['Tasks']['records'][0]['fields'][0])
        self.assertNotIn('text',selected['Tasks']['records'][0])
        self.assertNotIn('links',selected['Tasks']['records'][0])
        self.assertEqual(selected['Knowledge']['records'][0]['fields'][0]['text_original'],
                         knowledge['records'][0]['fields'][0]['text_original'])
        self.assertEqual(selected['Overview']['source_text'],overview['source_text'])
        for mapping in trace:
            self.assertEqual(mapping['input_records'],mapping['source_records'])
        with self.assertRaisesRegex(ValueError,'缺少 JD 模块'):
            project_jd_modules(data,modules+['Missing'])

    def test_source_mismatch_fails_before_generation(self):
        self.materials()
        paths=c.job_files('software_developer')
        (paths['source']/'source_details.html').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'digest mismatch'):
            read_occupation_data('software_developer')

    def test_resume_uses_verbatim_approved_jd_without_profile(self):
        self.materials()
        paths=c.job_files('software_developer'); paths['profile'].unlink()
        paths['jd'].write_bytes(BODY.encode('utf-8'))
        from material_preparation.generate_resumes import make_tasks as resumes
        task=resumes('resume',self.args,self.occupations,self.settings)[0]
        self.assertIn(BODY,task['messages'][0]['content'])
        self.assertEqual(task['metadata']['approved_jd_sha256'],c.sha256(BODY))

    def test_resume_wrapper_requires_excel_approval(self):
        self.materials(); review=self.workbook()
        with patch.object(storage,'api_request') as call:
            with self.assertRaisesRegex(ValueError,'尚未审核通过'):
                generate(['--task','resume','--run-id','resume','--review',str(review),'--execute'])
            call.assert_not_called()

    def test_stream_assembly_preserves_text_and_original_chunks(self):
        from shared.api import assemble_stream
        chunks=[{'id':'response','model':'model','choices':[{'index':0,'delta':{'content':'原文\r'}}]},
                {'id':'response','model':'model','choices':[{'index':0,'delta':{'content':'\n继续。'},'finish_reason':'stop'}]},
                {'id':'response','model':'model','choices':[],'usage':{'completion_tokens':4}}]
        response=assemble_stream(chunks)
        self.assertEqual(response.choices[0].message.content,'原文\r\n继续。')
        self.assertEqual(response.choices[0].finish_reason,'stop')
        self.assertEqual(response.model_dump()['stream_chunks'],chunks)
        self.assertEqual(response.model_dump()['usage'],{'completion_tokens':4})

    def test_extraction_keeps_every_character_and_rejects_ambiguous_outputs(self):
        self.assertEqual(extract_jd(ANSWER),BODY)
        for bad in [ANSWER+MARKERS[2],ANSWER.replace(MARKERS[3],''),'extra'+ANSWER,
                    ANSWER.replace(MARKERS[0],MARKERS[1],1)]:
            with self.assertRaises(ValueError): extract_jd(bad)

    def workbook(self,status=None):
        path=self.root/'review.xlsx'
        b=Workbook(); s=b.active; s.title='职业汇总'
        s.append(['O*NET Code','是否选用','JD','简历1','审核备注'])
        s.append(['15-1252.00',1,status,None,'保留人工备注'])
        b.save(path); b.close(); return path

    def test_preview_all_inputs_without_api_or_workbook_changes(self):
        self.materials(); review=self.workbook(); before=review.read_bytes()
        old_draft=c.job_files('software_developer')['jd_draft']
        old_draft.parent.mkdir(parents=True,exist_ok=True)
        old_draft.write_bytes(b'Existing original must survive new previews.')
        with patch.object(storage,'api_request') as call:
            self.assertEqual(generate(['--task','jd','--run-id','preview','--review',str(review)]),0)
            call.assert_not_called()
        self.assertEqual(review.read_bytes(),before)
        manifest=c.load_json(self.root/'material_preparation/results/material_generation/preview/preview_manifest.json')
        self.assertEqual(len(manifest['requests']),1)
        request=c.load_json(self.root/manifest['requests'][0]['request'])
        prompt=(self.root/manifest['requests'][0]['prompt']).read_bytes().decode('utf-8')
        self.assertEqual(request['task']['messages'][0]['content'],prompt)
        self.assertFalse(list(self.root.rglob('*.output.json')))
        self.assertEqual(old_draft.read_bytes(),b'Existing original must survive new previews.')
        self.assertIn('input_projection',request['task']['metadata'])

    def test_new_inclusion_field_controls_approval_instead_of_link_text(self):
        self.materials();review=self.workbook()
        c.job_files('software_developer')['jd'].unlink()
        response=SimpleNamespace(id='fake',model='fake',choices=[SimpleNamespace(
            finish_reason='stop',message=SimpleNamespace(content=ANSWER))],
            model_dump=lambda **kw:{'choices':[{'message':{'content':ANSWER}}],'usage':{}})
        with patch.object(storage,'api_request',return_value=(response,{})),patch.dict('os.environ',{'DEEPSEEK_API_KEY':'fake'}):
            generate(['--task','jd','--run-id','new_layout','--review',str(review),'--execute'])
        manifest=self.root/'material_preparation/results/material_generation/new_layout/generated_manifest.json'
        b=Workbook();s=b.active;s.title='职业汇总'
        s.append(['O*NET Code','是否选用','JD','JD是否纳入','审核备注'])
        s.append(['15-1252.00',1,'打开JD原稿',None,'保留人工备注'])
        b.save(review)
        self.assertEqual(approval_plan(review,manifest),[])
        s.cell(2,4,1);b.save(review);b.close()
        self.assertEqual(approval_plan(review,manifest)[0][1],BODY.encode('utf-8'))

    def test_new_review_table_approves_resume_verbatim_without_formatting(self):
        self.materials();paths=c.job_files('software_developer');rid='R03';run_id='raw_resume'
        raw='求职简历｜R03\r\n工作经历\r\n1. 原文第一项。第二句不分行。\r\n专业技能\r\n2. 原始技能。\r\n'
        draft=paths['drafts']/(rid+'.txt');draft.parent.mkdir(parents=True,exist_ok=True);draft.write_bytes(raw.encode('utf-8'))
        root=self.root/'material_preparation/results/material_generation'/run_id
        inp=root/'input.json';out=root/'output.json'
        context={'occupation':'software_developer','approved_jd_sha256':c.sha256(paths['jd'].read_bytes())}
        request={'messages':[{'role':'user','content':'原始输入'}]};sha=c.sha256(c.canonical(request))
        storage.write_json(inp,{'context':context,'task_id':rid,'run_id':run_id,'request':request,'request_sha256':sha})
        storage.write_json(out,{'context':context,'task_id':rid,'run_id':run_id,'status':'ok','answer':raw,
            'request_sha256':sha,'raw_response':{'choices':[{'message':{'content':raw}}]}})
        manifest=root/'generated_manifest.json'
        storage.write_json(manifest,{'task':'resume','run_id':run_id,'materials':[{'occupation':'software_developer','task_id':rid,
            'draft':str(draft.relative_to(self.root)),'draft_sha256':c.sha256(draft.read_bytes()),
            'input':str(inp.relative_to(self.root)),'output':str(out.relative_to(self.root))}]})
        review=self.root/'new_review.xlsx';b=Workbook();s=b.active;s.title='职业汇总'
        s.append(['O*NET Code','是否选用','JD','JD是否纳入','简历3是否纳入'])
        s.append(['15-1252.00',1,'打开JD原稿',1,1]);b.save(review);b.close()
        plan=approval_plan(review,manifest)
        self.assertEqual(plan[0][1],raw.encode('utf-8'))
        self.assertNotIn('content_transform',plan[0][3])
        self.assertFalse((review.parent/'resumes').exists())

    def test_generation_raw_preservation_and_excel_approval_gate(self):
        self.materials(); review=self.workbook()
        c.job_files('software_developer')['jd'].unlink()
        response=SimpleNamespace(id='fake',model='fake',choices=[SimpleNamespace(
            finish_reason='stop',message=SimpleNamespace(content=ANSWER))],
            model_dump=lambda **kw:{'choices':[{'message':{'content':ANSWER}}],'usage':{}})
        with patch.object(storage,'api_request',return_value=(response,{})),patch.dict('os.environ',{'DEEPSEEK_API_KEY':'fake'}):
            self.assertEqual(generate(['--task','jd','--run-id','generated','--review',str(review),'--execute']),0)
        manifest=self.root/'material_preparation/results/material_generation/generated/generated_manifest.json'
        self.assertEqual(approval_plan(review,manifest),[])
        self.workbook('通过')
        plan=approval_plan(review,manifest)
        self.assertEqual(len(plan),1); self.assertEqual(plan[0][1],BODY.encode('utf-8'))
        self.assertEqual(approve(['--run-id','generated','--review',str(review),'--execute']),0)
        paths=c.job_files('software_developer')
        self.assertEqual(paths['jd_draft'].read_bytes(),ANSWER.encode('utf-8'))
        self.assertEqual(paths['jd'].read_bytes(),BODY.encode('utf-8'))
        self.assertEqual(approve(['--run-id','generated','--review',str(review),'--execute']),0)
        paths['jd_draft'].write_bytes(b'tampered')
        with self.assertRaises(ValueError): approval_plan(review,manifest)

    def test_rejected_jd_removal_checks_original_and_preserves_archives(self):
        self.materials(); review=self.workbook()
        response=SimpleNamespace(id='fake',model='fake',choices=[SimpleNamespace(
            finish_reason='stop',message=SimpleNamespace(content=ANSWER))],
            model_dump=lambda **kw:{'choices':[{'message':{'content':ANSWER}}],'usage':{}})
        with patch.object(storage,'api_request',return_value=(response,{})),patch.dict('os.environ',{'DEEPSEEK_API_KEY':'fake'}):
            generate(['--task','jd','--run-id','old','--review',str(review),'--execute'])
        from material_preparation.remove_jd_drafts import removal_plan,run as remove
        root=self.root/'material_preparation/results/material_generation/old'
        manifest=root/'generated_manifest.json'
        draft=c.job_files('software_developer')['jd_draft']
        saved=draft.read_bytes(); draft.write_bytes(b'User changed this draft')
        with self.assertRaisesRegex(ValueError,'已被修改'): removal_plan(manifest)
        self.assertTrue(draft.exists())
        draft.write_bytes(saved)
        all_records={p:p.read_bytes() for p in self.root.rglob('*.output.json')}
        self.assertEqual(remove(['--run-id','old','--execute']),0)
        self.assertFalse(draft.exists())
        self.assertTrue((root/'draft_removal.json').exists())
        self.assertEqual(removal_plan(manifest),[])
        for p,raw in all_records.items(): self.assertEqual(p.read_bytes(),raw)

    def test_two_levels_two_each_bind_jd_without_fabricating_approval(self):
        self.materials(); review=self.workbook(); review_raw=review.read_bytes()
        c.job_files('software_developer')['jd'].unlink()
        response=SimpleNamespace(id='fake',model='fake',choices=[SimpleNamespace(
            finish_reason='stop',message=SimpleNamespace(content=ANSWER))],
            model_dump=lambda **kw:{'choices':[{'message':{'content':ANSWER}}],'usage':{}})
        with patch.object(storage,'api_request',return_value=(response,{})),patch.dict('os.environ',{'DEEPSEEK_API_KEY':'fake'}):
            generate(['--task','jd','--run-id','jd_source','--review',str(review),'--execute'])
        args=SimpleNamespace(occupation='software_developer',count=2,start_index=1,
                             levels=['medium','low'],jd_run_id='jd_source')
        from material_preparation.generate_resumes import make_tasks as resumes
        tasks=resumes('resume',args,self.occupations,self.settings)
        self.assertEqual([t['task_id'] for t in tasks],['R01','R02','R03','R04'])
        self.assertEqual([t['metadata']['ability_level'] for t in tasks],['medium','medium','low','low'])
        self.assertEqual(len({t['metadata']['jd_input_sha256'] for t in tasks}),1)
        self.assertEqual(tasks[0]['metadata']['jd_input_sha256'],c.sha256(BODY))
        self.assertIn('累计3—4年',tasks[0]['messages'][0]['content'])
        self.assertIn('累计1—2年',tasks[2]['messages'][0]['content'])
        for task in tasks:
            self.assertIn(BODY,task['messages'][0]['content'])
            self.assertNotIn('{ability_profile}',task['messages'][0]['content'])
            self.assertEqual(task['metadata']['jd_input_mode'],'generated_batch')
        with patch.object(storage,'api_request') as call:
            self.assertEqual(generate(['--task','resume','--levels','medium','low','--count','2',
                                      '--jd-run-id','jd_source','--run-id','level_preview','--review',str(review)]),0)
            call.assert_not_called()
        self.assertFalse(c.job_files('software_developer')['jd'].exists())
        self.assertEqual(review.read_bytes(),review_raw)
        from material_preparation.resume_inputs import validate_resume_text
        for task in tasks:
            meta=task['metadata']; plan=meta['employment_plan']
            body=('求职简历｜'+meta['resume_id']+'\n教育背景\n'+plan['education_period']+' '+plan['major']+
                  '\n工作经历\n'+'\n'.join(plan['work_periods'])+
                  '\n项目经历／代表性工作成果\n'+plan['project_period']+'\n专业技能\n测试技能')
            validate_resume_text(body,meta)
            scannable=('求职简历｜'+meta['resume_id']+'\n工作经历\n'+plan['work_periods'][1]+'\n'+plan['work_periods'][0]+
                       '\n项目经历／代表性工作成果\n'+plan['project_period']+
                       '\n教育背景\n本科，'+plan['major']+'｜'+plan['school']+'｜'+plan['education_period']+
                       '\n专业技能\n- 语言：Python')
            validate_resume_text(scannable,meta)
            with self.assertRaisesRegex(ValueError,'模糊占位词'):
                validate_resume_text(scannable.replace(plan['school'],'某某大学'),meta)
            with self.assertRaisesRegex(ValueError,'工作经历日期'):
                validate_resume_text(body.replace(plan['work_periods'][0],'2020.01—2025.12'),meta)
        self.assertEqual([t['metadata']['employment_plan']['total_work_months'] for t in tasks],[40,46,18,12])
        c.job_files('software_developer')['jd_draft'].write_bytes(b'user changed JD')
        with self.assertRaisesRegex(ValueError,'已变化'):
            resumes('resume',args,self.occupations,self.settings)


