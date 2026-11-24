"""Renamed reviewer paths remain independent and preserve four members' existing decisions."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from openpyxl import Workbook
from shared import common as c
from material_preparation.reviewer_config import load_team, reviewer_file
from material_preparation.export_morality_review import make_payload, REVIEW_HEADERS
from material_preparation.export_individual_reviews import OCCUPATION_HEADERS, preserve_reviews


class ReviewerConfigTests(unittest.TestCase):
    def team(self):
        people = ['gsc', 'lkx', 'lxy', 'wjy']
        return {'reviewers': people, 'review_files': {
            'occupation': {p: ('lJD+resume_kx.xlsx' if p == 'lkx' else 'JD+resume_' + p + '.xlsx') for p in people},
            'mority': {p: 'moral_' + p + '.xlsx' for p in people}}}

    def test_explicit_renamed_paths_and_member_count_are_not_hardcoded(self):
        team = load_team(self.team())
        self.assertEqual(reviewer_file(team, 'occupation', 'lkx', Path('occupation')), Path('occupation/lJD+resume_kx.xlsx'))
        self.assertEqual(reviewer_file(team, 'mority', 'gsc', Path('mority')), Path('mority/moral_gsc.xlsx'))
        extended = copy.deepcopy(team)
        extended['reviewers'].append('fifth')
        for group in extended['review_files']:
            extended['review_files'][group]['fifth'] = 'fifth.xlsx'
        self.assertEqual(len(load_team(extended)['reviewers']), 5)

    def test_duplicate_names_filenames_and_outside_paths_are_rejected(self):
        team = self.team()
        team['review_files']['mority']['lkx'] = team['review_files']['mority']['gsc']
        with self.assertRaisesRegex(ValueError, '共用'):
            load_team(team)
        team = self.team()
        team['reviewers'][-1] = 'GSC'
        with self.assertRaisesRegex(ValueError, '重复'):
            load_team(team)
        team = self.team()
        team['review_files']['occupation']['lkx'] = '../outside.xlsx'
        with self.assertRaises(ValueError):
            load_team(team)

    def test_four_renamed_files_keep_separate_opinions_and_master_columns(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(c, 'ROOT', Path(temp)):
            root = Path(temp)
            team = self.team()
            folder = root / 'material_preparation/review/mority'
            folder.mkdir(parents=True)
            files = {}
            for person in team['reviewers']:
                path = reviewer_file(team, 'mority', person, folder)
                book = Workbook()
                sheet = book.active
                sheet.title = '材料审核'
                for _ in range(4):
                    sheet.append([])
                sheet.append(REVIEW_HEADERS)
                row = {'材料编号': 'CARE_00101', '材料版本': 'same-version', '生成状态': '已生成',
                       '审核结论': '需修改', '问题说明': person + '的独立意见'}
                sheet.append([row.get(h) for h in REVIEW_HEADERS])
                book.save(path)
                book.close()
                files[path] = path.read_bytes()
            team_path = root / 'team.json'
            team_path.write_text(c.canonical(team), encoding='utf-8')
            current = [{'材料编号': 'CARE_00101', '材料版本': 'same-version', '生成状态': '已生成',
                        '道德主题': '关怀/伤害'}]
            with patch('material_preparation.export_morality_review.material_rows', return_value=current):
                payload, _ = make_payload({'review_config': 'team.json'}, {}, {}, [], {}, root, 'test')
            self.assertEqual(len(payload['specs']), 5)
            master = payload['specs'][0]
            for person in team['reviewers']:
                self.assertIn(person, master['headers'])
                spec = next(s for s in payload['specs'][1:] if Path(s['review']).name == 'moral_' + person + '.xlsx')
                self.assertEqual(spec['rows'][0][REVIEW_HEADERS.index('问题说明')], person + '的独立意见')
            for path, data in files.items():
                self.assertEqual(path.read_bytes(), data)

    def test_four_occupation_files_preserve_each_members_own_decision(self):
        team = load_team(self.team())
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            material = {'材料编号': '15-1252.00_R01', '材料批次': 'same-run',
                        '原稿SHA256': 'same-original', '材料类型': '简历', '_links': {}}
            decisions = ['可用', '需重新生成', '不采用', None]
            for person, decision in zip(team['reviewers'], decisions):
                path = reviewer_file(team, 'occupation', person, folder)
                book = Workbook()
                sheet = book.active
                sheet.title = '材料审核'
                for _ in range(4):
                    sheet.append([])
                sheet.append(OCCUPATION_HEADERS)
                saved = {**material, '审核结论': decision, '问题说明': person + '的独立意见'}
                sheet.append([saved.get(h) for h in OCCUPATION_HEADERS])
                book.save(path)
                book.close()
                before = path.read_bytes()
                rows, _ = preserve_reviews(path, OCCUPATION_HEADERS, [material])
                self.assertEqual(rows[0][OCCUPATION_HEADERS.index('审核结论')], decision)
                self.assertEqual(rows[0][OCCUPATION_HEADERS.index('问题说明')], person + '的独立意见')
                self.assertEqual(path.read_bytes(), before)
            self.assertEqual(len(list(folder.glob('*.xlsx'))), 4)


if __name__ == '__main__':
    unittest.main()
