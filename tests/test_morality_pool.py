"""Scientific input freezing, candidate coverage, generated/rejected records and human review safety."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from openpyxl import Workbook
from shared import common as c, storage
from material_preparation.morality_inputs import build_tasks, validate_generated
from material_preparation.run_morality_generation import preview
from material_preparation.run_morality_generation import run as run_generation
from material_preparation.export_morality_review import material_rows, preserve, validate_review, REVIEW_MANUAL

PROJECT = Path(__file__).resolve().parents[1]


class MoralityPoolTests(unittest.TestCase):
    def small_project(self, root):
        for relative in ['config/morality_generation.json','config/morality_protocol.json','config/settings.json',
                         'prompts/morality_pool.txt','sources/morality/mfv_catalog.json']:
            target = root / 'material_preparation' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PROJECT / 'material_preparation' / relative, target)
        path = root / 'material_preparation/config/morality_generation.json'
        config = c.load_json(path)
        config.update(variants_per_mfv=1, novel_per_foundation=0)
        path.write_text(c.canonical(config), encoding='utf-8')
        catalog_path = root / config['catalog']
        catalog = c.load_json(catalog_path)
        catalog['items'] = catalog['items'][:1]
        catalog_path.write_text(c.canonical(catalog), encoding='utf-8')

    def generated(self, task):
        return {'pair_id': task['task_id'], 'foundation': task['metadata']['foundation'], 'status': 'generated',
                'negative': '候选人在一次私人聚会中，当着其他人的面反复拿一位参加者的体形取笑。',
                'neutral': '候选人在同一次私人聚会中，与附近的参加者谈论各自带来的桌面游戏。',
                'scene_summary': '成人私人聚会', 'dominant_violation': '具体的情感伤害',
                'adaptation_note': '改成成人私人事件', 'neutral_rationale': '同一聚会中的普通互动',
                'other_foundations': [], 'review_flags': [], 'rejection_reason': ''}

    def test_pool_covers_all_moral_sources_without_pretending_controls_are_matched_neutrals(self):
        _, _, catalog, tasks = build_tasks(PROJECT / 'material_preparation/config/morality_generation.json')
        self.assertEqual(len(catalog['items']), 132)
        self.assertEqual(sum(x['recommended'] for x in catalog['items']), 90)
        self.assertEqual(len(tasks), 268)
        source_ids = [t['metadata']['spec']['source_id'] for t in tasks if t['metadata']['spec']['source_id']]
        self.assertEqual(len(set(source_ids)), 116)
        self.assertTrue(all(source_ids.count(x) == 2 for x in set(source_ids)))
        self.assertEqual(len({t['task_id'] for t in tasks}), len(tasks))
        self.assertEqual(sum(t['metadata']['spec']['source_kind'] == 'principle_extension' for t in tasks), 36)
        for task in tasks:
            self.assertNotEqual(task['metadata']['spec'].get('source', {}).get('foundation') if task['metadata']['spec']['source'] else None, 'social_norm')
            text = task['messages'][0]['content']
            self.assertIn('原作者MFV编写规则', text)
            self.assertIn('中性版', text)

    def test_preview_never_calls_api_and_freezes_actual_prompt_inputs(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(c, 'ROOT', Path(temp)), patch.object(storage, 'api_request', side_effect=AssertionError('network')):
            root = Path(temp)
            self.small_project(root)
            *_, folder, _ = preview()
            before = (folder / 'plan.json').read_bytes()
            preview()
            self.assertEqual((folder / 'plan.json').read_bytes(), before)
            prompt = root / 'material_preparation/prompts/morality_pool.txt'
            prompt.write_text(prompt.read_text(encoding='utf-8') + '\n不同写作要求', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '不覆盖'):
                preview()
            self.assertEqual((folder / 'plan.json').read_bytes(), before)
            self.assertFalse((folder / 'records').exists())

    def test_wrong_identity_and_identical_pair_cannot_be_saved(self):
        _, _, _, tasks = build_tasks(PROJECT / 'material_preparation/config/morality_generation.json')
        good = self.generated(tasks[0])
        validate_generated(good, tasks[0])
        bad = {**good, 'pair_id': 'CARE_99999'}
        with self.assertRaisesRegex(ValueError, '编号或主题'):
            validate_generated(bad, tasks[0])
        with self.assertRaisesRegex(ValueError, '完全相同'):
            validate_generated({**good, 'neutral': good['negative']}, tasks[0])

    def test_rejected_response_is_not_a_material_draft(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(c, 'ROOT', Path(temp)):
            self.small_project(Path(temp))
            *_, tasks = build_tasks()
            task = tasks[0]
            rejected = {**self.generated(task), 'status': 'not_adaptable', 'negative': '', 'neutral': '',
                        'rejection_reason': '无法保留关系结构且建立自然中性版本'}
            storage.save_draft(task, json.dumps(rejected), rejected)
            self.assertFalse((Path(temp) / 'material_preparation/drafts/morality').exists())
            rejected['rejection_reason'] = ''
            with self.assertRaisesRegex(ValueError, '说明原因'):
                storage.save_draft(task, json.dumps(rejected), rejected)

    def test_mocked_generation_exports_real_text_but_not_planned_tasks_as_materials(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(c, 'ROOT', Path(temp)):
            self.small_project(Path(temp))
            _, _, _, tasks, settings, folder, run_id = preview()
            task = tasks[0]
            self.assertEqual(material_rows(tasks, settings, folder, run_id)[0]['生成状态'], '待生成')
            parsed = self.generated(task)
            content = json.dumps(parsed, ensure_ascii=False)
            raw = {'choices': [{'message': {'content': content}}]}
            record_dir = folder / 'records'
            record_dir.mkdir()
            (record_dir / (task['task_id'] + '_a01.input.json')).write_text(c.canonical({'task_id': task['task_id'], 'attempt': 1, 'request': storage.request_for(task, settings)}), encoding='utf-8')
            out = {'status': 'ok', 'parsed': parsed, 'answer': content, 'raw_response': raw}
            (record_dir / (task['task_id'] + '_a01.output.json')).write_text(c.canonical(out), encoding='utf-8')
            storage.save_draft(task, content, parsed)
            rows = material_rows(tasks, settings, folder, run_id)
            self.assertEqual(rows[0]['生成状态'], '已生成')
            body = Path(rows[0]['_body']).read_text(encoding='utf-8')
            self.assertIn(parsed['negative'], body)
            draft = Path(temp) / 'material_preparation/drafts/morality' / (task['task_id'] + '.json')
            changed = {**parsed, 'negative': '被改写的正文'}
            draft.write_text(c.canonical(changed), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '草稿与成功响应'):
                material_rows(tasks, settings, folder, run_id)

    def test_manual_reviews_follow_version_and_cannot_approve_ungenerated_text(self):
        one = {'材料编号': 'CARE_00101', '材料版本': 'v1', '生成状态': '已生成'}
        two = {'材料编号': 'CARE_00201', '材料版本': 'v2', '生成状态': '已生成'}
        saved = {('CARE_00101', 'v1'): {'审核结论': '需修改', '问题说明': '中性情境不自然'}}
        rows = preserve([two, one], saved)
        self.assertEqual(rows[1]['审核结论'], '需修改')
        self.assertNotIn('审核结论', rows[0])
        with self.assertRaisesRegex(ValueError, '换版'):
            preserve([{**one, '材料版本': 'changed'}], saved)
        with self.assertRaisesRegex(ValueError, '尚无正文'):
            validate_review({'材料编号': 'X', '生成状态': '待生成', '审核结论': '可用'})

    def test_mocked_execute_resumes_without_calling_again_and_exports_rejection_reason(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(c, 'ROOT', Path(temp)), patch.object(c, 'load_api_key', return_value='mock-key'):
            self.small_project(Path(temp))
            _, _, _, tasks = build_tasks()
            task = tasks[0]
            parsed = {**self.generated(task), 'status': 'not_adaptable', 'negative': '', 'neutral': '',
                      'rejection_reason': '自然配对不成立'}
            text = json.dumps(parsed, ensure_ascii=False)
            raw = {'choices': [{'finish_reason': 'stop', 'message': {'content': text}}]}
            response = SimpleNamespace(id='mock', model='mock-model', system_fingerprint=None,
                choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=text))],
                model_dump=lambda **kwargs: copy.deepcopy(raw))
            with patch.object(storage, 'api_request', return_value=(response, {})) as api:
                self.assertEqual(run_generation(['--execute', '--limit', '1']), 0)
                self.assertEqual(api.call_count, 1)
                self.assertEqual(run_generation(['--execute', '--limit', '1']), 0)
                self.assertEqual(api.call_count, 1)
            _, _, _, tasks, settings, folder, run_id = preview()
            row = material_rows(tasks, settings, folder, run_id)[0]
            self.assertEqual(row['生成状态'], '不适配')
            self.assertIn('自然配对不成立', row['生成备注'])
            self.assertIsNone(row['_body'])


if __name__ == '__main__':
    unittest.main()
