"""Meaningful storage regressions: previews, paired stages, failures and immutability."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from shared import common as c,storage,material_results as mr


class MaterialResultLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.mock=patch.object(c,'ROOT',self.root);self.mock.start()
        self.settings={'profiles':{'generation':{'model':'fake','temperature':1,'thinking':'disabled','max_tokens':3000}},
                       'api_base_url':'https://example.test','api_timeout_seconds':120}
        self.args=SimpleNamespace(run_id='20261125_001',stage='pilot',concurrency=2,retry_failed=False)
        mr.write(c.occupations_file(),{'software_developer':{'onet_code':'15-1252.00','onet_name':'Software Developers'}})

    def tearDown(self):self.mock.stop();self.temp.cleanup()
    def task(self,kind='moral-generate',tid='CARE_00101',foundation='care'):
        meta={'foundation':foundation}
        if kind in {'jd','resume'}:meta.update(occupation='software_developer',material_directory='Software_Developers_15-1252.00')
        return {'task':kind,'task_id':tid,'metadata':meta,
                'messages':[{'role':'user','content':'verbatim input\r\n'}],'json_mode':False}
    def response(self,text):
        return SimpleNamespace(id='fake',model='fake',choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=text))],
            model_dump=lambda **kw:{'choices':[{'message':{'content':text}}]})

    def test_preview_is_pending_has_no_duplicate_prompt_and_is_immutable(self):
        task=self.task();base=mr.prepare([task],self.settings,self.args)
        inp=mr.inputs(base)[0];raw=inp.read_bytes();manifest=(base/mr.INFO).read_bytes()
        self.assertTrue(storage.pending(task,self.settings,self.args))
        self.assertFalse(mr.output_path(inp).exists())
        self.assertEqual([x.name for x in inp.parent.iterdir()],['input.json'])
        mr.prepare([task],self.settings,self.args)
        self.assertEqual(inp.read_bytes(),raw);self.assertEqual((base/mr.INFO).read_bytes(),manifest)
        task['messages'][0]['content']='changed'
        with self.assertRaisesRegex(ValueError,'输入已变化'):mr.prepare([task],self.settings,self.args)
        self.assertEqual(inp.read_bytes(),raw)

    def test_failed_call_requires_explicit_retry_and_never_overwrites_input(self):
        task=self.task();base=mr.prepare([task],self.settings,self.args)
        before=mr.inputs(base)[0].read_bytes()
        with patch.object(storage,'api_request',side_effect=RuntimeError('network failure')):
            self.assertEqual(storage.record_task(task,self.settings,self.args),'error')
        first=mr.inputs(base)[0]
        self.assertTrue(first.parent.name.endswith('_fail'));self.assertEqual(first.read_bytes(),before)
        with patch.object(storage,'api_request') as call:
            self.assertEqual(storage.record_task(task,self.settings,self.args),'skip');call.assert_not_called()
        self.args.retry_failed=True
        answer='exact response\r\n'
        with patch.object(storage,'api_request',return_value=(self.response(answer),{})),patch.object(storage,'save_draft'):
            self.assertEqual(storage.record_task(task,self.settings,self.args),'ok')
        records=mr.inputs(base)
        self.assertEqual(len(records),2)
        self.assertTrue(records[1].parent.name.endswith('_retry001'))
        self.assertEqual(records[0].read_bytes(),before)
        self.assertEqual(c.load_json(mr.output_path(records[1]))['answer'],answer)
        self.assertFalse(storage.pending(task,self.settings,self.args))

    def test_two_stages_share_one_batch_but_have_independent_records(self):
        jd=self.task('jd','JD01');resume=self.task('resume','R01')
        first=mr.prepare([jd],self.settings,self.args,{'task':'jd','count':2})
        original=mr.inputs(first)[0].read_bytes()
        second=mr.prepare([resume],self.settings,self.args,{'task':'resume','count':2,'jd_run_id':self.args.run_id})
        self.assertEqual(first,second);self.assertEqual(len(mr.inputs(first)),2)
        self.assertEqual(set(mr.info(first)['plans']),{'jd','resume'})
        self.assertEqual(mr.inputs(first,'JD01','jd')[0].read_bytes(),original)

    def test_same_task_ids_in_different_dimensions_cannot_collide(self):
        tasks=[self.task(foundation='care'),self.task(foundation='fairness')]
        base=mr.prepare(tasks,self.settings,self.args)
        self.assertEqual(len(mr.inputs(base)),2)
        self.assertEqual({p.parent.parent.name for p in mr.inputs(base)},{'care','fairness'})

    def test_prepared_stage_cannot_silently_add_or_remove_tasks(self):
        task=self.task();mr.prepare([task],self.settings,self.args)
        with self.assertRaisesRegex(ValueError,'任务范围已变化'):
            mr.prepare([task,self.task(tid='CARE_00102')],self.settings,self.args)

    def test_download_summary_keeps_each_occupations_result(self):
        base=mr.root()/'onet_download/20261125_001'
        mr.write(base/mr.INFO,{'task':'onet-download','occupations':[
            {'occupation':'software_developer','onet_code':'15-1252.00','status':'reused','url':'https://example.test'}]})
        mr.refresh(base)
        import csv
        with (base/'调用清单.csv').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.reader(f))
        self.assertEqual(len(rows),2);self.assertEqual(rows[1][2],'reused')

    def test_display_sequence_matches_new_directory_without_rewriting_legacy_input(self):
        task=self.task();base=mr.prepare([task],self.settings,self.args)
        inp=mr.inputs(base)[0];record=c.load_json(inp);record['sequence']=99;mr.write(inp,record)
        original=inp.read_bytes();mr.refresh(base)
        import csv
        with (base/'调用清单.csv').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.reader(f))
        self.assertEqual(rows[1][0],'1');self.assertEqual(inp.read_bytes(),original)

    def test_source_verifier_distinguishes_versioned_templates_from_immutable_sources(self):
        from material_preparation.verify_occupation_exports import verify_archived_inputs
        source=self.root/'material_preparation/sources/page.html'
        prompt=self.root/'material_preparation/prompts/jd.txt'
        source.parent.mkdir(parents=True);source.write_bytes(b'original source')
        prompt.parent.mkdir(parents=True);prompt.write_bytes(b'new template')
        manifest={'unchanged_inputs':{mr.relative(source):c.sha256(source.read_bytes()),
                                     mr.relative(prompt):c.sha256(b'old template')}}
        self.assertEqual(verify_archived_inputs(manifest),[mr.relative(prompt)])
        with self.assertRaisesRegex(ValueError,'Archived input'):verify_archived_inputs(manifest,True)
        source.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError,'Archived input'):verify_archived_inputs(manifest)

    def test_concurrent_duplicate_claim_is_rejected(self):
        task=self.task();mr.prepare([task],self.settings,self.args)
        inp,out,data,lock=mr.begin(task,self.settings,self.args)
        try:
            with self.assertRaisesRegex(ValueError,'正在执行'):mr.begin(task,self.settings,self.args)
        finally:lock.unlink()

    def test_archived_paths_resolve_without_rewriting_original_bytes(self):
        from zipfile import ZipFile
        path=self.root/'old.json';raw=b'{"run_id":"legacy","literal":"unchanged"}\n'
        archive=self.root/'history.zip'
        with ZipFile(archive,'w') as z:z.writestr('old.json',raw)
        mr.write(mr.mapping_path(),{'aliases':{},'files':{'old.json':{'archive':'history.zip','member':'old.json','sha256':c.sha256(raw)}}})
        self.assertEqual(mr.legacy_bytes(path),raw)
        self.assertEqual(c.load_json(path)['run_id'],'legacy')

    def test_migrated_preview_execution_preserves_input_bytes_and_records_live_execution_metadata(self):
        task=self.task();base=mr.prepare([task],self.settings,self.args)
        inp=mr.inputs(base)[0];record=c.load_json(inp)
        record.update(run_id='legacy_morality_preview',timestamp_utc=None,concurrency=1)
        mr.write(inp,record);original=inp.read_bytes()
        run_args=SimpleNamespace(run_id=self.args.run_id,stage='pilot',concurrency=4,retry_failed=False)
        with patch.object(storage,'api_request',return_value=(self.response('ok\n'),{})),patch.object(storage,'save_draft'):
            self.assertEqual(storage.record_task(task,self.settings,run_args),'ok')
        self.assertEqual(inp.read_bytes(),original)
        out=c.load_json(mr.output_path(inp))
        self.assertEqual(out['run_id'],base.name)
        self.assertEqual(out['concurrency'],4)
        self.assertIsNotNone(out['timestamp_utc'])

    def test_blinded_moral_review_groups_by_foundation_and_freezes_alongside_generation_stage(self):
        from shared import batch
        self.settings['profiles']['material_review']={'model':'fake','temperature':1,'thinking':'disabled','max_tokens':1600}
        gen=self.task('moral-generate','CARE_00101','care')
        base=mr.prepare([gen],self.settings,self.args,{'task':'moral-generate','protocol_version':'v3'})
        mr.write(self.root/'material_preparation/drafts/morality/F_001.json',
                 {'pair_id':'F_001','foundation':'fairness','neutral':'a','negative':'b'})
        reviews=[
            {'task':'moral-review','task_id':'CARE_00101_neutral',
             'metadata':{'pair_id':'CARE_00101','background_type':'neutral','source':'drafts'},
             'messages':[{'role':'user','content':'check 1'}],'json_mode':False},
            {'task':'moral-review','task_id':'F_001_negative',
             'metadata':{'pair_id':'F_001','background_type':'negative','source':'drafts'},
             'messages':[{'role':'user','content':'check 2'}],'json_mode':False},
        ]
        review_args=SimpleNamespace(task='moral-review',run_id=self.args.run_id,stage='pilot',occupations=[],concurrency=2)
        batch.freeze(reviews,self.settings,review_args)
        review_inputs=mr.inputs(base,kind='moral-review')
        self.assertEqual(len(review_inputs),2)
        self.assertEqual({p.parent.parent.name for p in review_inputs},{'care','fairness'})


if __name__=='__main__':unittest.main()
