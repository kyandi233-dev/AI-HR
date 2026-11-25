"""Offline source completeness and review-preservation checks."""
import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from openpyxl import load_workbook
from shared import common as c
from material_preparation.onet_data import source_folder, source_identity, write_json, digest
from material_preparation.onet_download import fetch_onet
from material_preparation.parse_occupations import parse_html, parse_occupation
from material_preparation.export_occupation_review import (
    SHEETS, SUMMARY, MANUAL, make_workbook, save_workbook, existing_manual, build_rows,
)


HTML = '''<html><main><h1>Example 15-1252.00</h1><p>Original overview.</p>
<div class="reportsection" id="Tasks"><h2>Tasks <span>Save Table</span></h2>
<button data-bs-toggle="collapse">10 of All 2 displayed</button>
<table><thead><tr><th>Importance</th><th>Category</th><th>Task</th></tr></thead><tbody>
<tr><td data-text="77">77</td><td>Core</td><td data-text="Original one.">Original one.<a href="/link/moreinfo/task/1">Related occupations</a></td></tr>
<tr class="collapse"><td data-text="69">69</td><td>Supplemental</td><td data-text="Original two.">Original two.</td></tr>
</tbody></table></div>
<div class="reportsection" id="SoftwareSkills"><h2>Software Skills</h2>
<ul><li>Original tool; <a href="/link/tt/example">62 more</a></li></ul></div>
<div class="reportsection" id="UnexpectedSection"><h2>New official section</h2><p>Keep this exact sentence.</p></div>
</main></html>'''


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patch = patch.object(c, 'ROOT', self.root)
        self.patch.start()
        self.info = {'onet_code': '15-1252.00', 'onet_name': 'Example',
                     'job_family_code': '15', 'job_family_name': 'Computer and Mathematical'}
        self.registry = {'example': self.info}

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def fetch(self):
        response = SimpleNamespace(content=HTML.encode(), status_code=200, raise_for_status=lambda: None)
        with patch('requests.get', return_value=response) as request:
            result = fetch_onet(argparse.Namespace(occupation='example', execute=True), self.registry)
        self.assertEqual(request.call_count, 1)
        self.assertFalse(request.call_args.kwargs['allow_redirects'])
        self.assertEqual(result['status'], 'downloaded')

    def test_initial_response_only_exact_bytes_and_skip(self):
        self.fetch()
        folder = source_folder(self.info)
        self.assertEqual((folder/'source_details.html').read_bytes(), HTML.encode())
        self.assertIn('62 more', (folder/'source_details.txt').read_text(encoding='utf-8'))
        with patch('requests.get') as request:
            self.assertEqual(fetch_onet(argparse.Namespace(occupation='example', execute=True), self.registry)['status'], 'reused')
            request.assert_not_called()
        (folder/'source_details.html').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            source_identity(folder)

    def test_hidden_rows_unknown_sections_and_original_fields_retained(self):
        parsed = parse_html(HTML, 'https://www.onetonline.org/link/details/15-1252.00')
        sections = {s['id']:s for s in parsed['sections']}
        self.assertEqual(sections['Tasks']['record_count'], 2)
        self.assertEqual(sections['Tasks']['records'][1]['fields'][2]['value'], 'Original two.')
        self.assertIn('Keep this exact sentence.', sections['UnexpectedSection']['source_text'])
        self.assertIn('62 more', sections['SoftwareSkills']['source_text'])
        self.assertFalse(parsed['warnings'])

    def test_mismatched_declared_counts_reported_not_silently_filled(self):
        parsed = parse_html(HTML.replace('2 displayed', '3 displayed'), 'https://example.test')
        self.assertTrue(parsed['warnings'])
        self.assertIn('parsed 2', parsed['warnings'][0])

    def test_review_notes_survive_reexport_and_source_change(self):
        self.fetch()
        parse_occupation('example', self.info)
        rows, _ = build_rows(self.registry)
        self.assertEqual(rows['职业汇总'][0][-len(MANUAL):], [None]*len(MANUAL))
        self.assertEqual(len(rows['Tasks']), 2)
        path = self.root/'review.xlsx'
        save_workbook(path, make_workbook(rows, SHEETS))
        book = load_workbook(path)
        sheet = book['职业汇总']
        sheet.cell(2, (SUMMARY+MANUAL).index('JD')+1, '通过')
        sheet.cell(2, (SUMMARY+MANUAL).index('审核备注')+1, 'Keep my note')
        sheet.cell(1, len(SUMMARY+MANUAL)+1, '自定义审核列')
        sheet.cell(2, len(SUMMARY+MANUAL)+1, 'Custom value')
        book.save(path)
        previous, extra = existing_manual(path)
        self.assertEqual(extra, ['自定义审核列'])
        previous['15-1252.00']['来源摘要'] = 'old-source'
        new_rows, _ = build_rows(self.registry, previous, extra)
        row = dict(zip(SUMMARY+MANUAL+extra, new_rows['职业汇总'][0]))
        self.assertEqual(row['JD'], '通过')
        self.assertEqual(row['审核备注'], 'Keep my note')
        self.assertEqual(row['自定义审核列'], 'Custom value')
        self.assertIn('来源已变化', row['提示'])
        save_workbook(path, make_workbook(new_rows, {**SHEETS, '职业汇总': SUMMARY+MANUAL+extra}))
        self.assertEqual(len(list((path.parent/'backups').glob('*.xlsx'))), 1)

    def test_full_source_text_can_be_reassembled_without_truncation(self):
        self.fetch()
        data = parse_occupation('example', self.info)
        data['sections'][0]['source_text'] = 'Source line\n'*6000
        write_json(source_folder(self.info)/'structured_en.json', data)
        rows, _ = build_rows(self.registry)
        parts = [r[-1] for r in rows['原文段落'] if r[2]=='Overview']
        self.assertEqual(''.join(parts), data['sections'][0]['source_text'])
        self.assertTrue(all(len(p)<=30000 for p in parts))

    def test_excel_preserves_literal_cr_lf_and_formula_like_source_text(self):
        rows = {key: [] for key in SHEETS}
        original = '=literal source\r\nsecond line\rthird line'
        rows['原文段落'] = [['15-1252.00', 'Example', 'Overview', 1, original]]
        path = self.root/'exact_text.xlsx'
        save_workbook(path, make_workbook(rows, SHEETS))
        book = load_workbook(path, read_only=True)
        try:
            self.assertEqual(book['原文段落']['E2'].value, original)
            self.assertEqual(book['原文段落']['E2'].data_type, 's')
        finally:
            book.close()

    def test_readable_layout_separates_native_modules_and_keeps_descriptions(self):
        from material_preparation.occupation_review_layout import occupation_workbook
        raw = HTML.replace('</main>', '''<div class="reportsection" id="WorkStyles"><h2>Work Styles</h2>
        <table><thead><tr><th>Impact</th><th>Work Style</th></tr></thead><tbody>
        <tr><td data-text="89">89</td><td data-text="Attention to Detail"><div class="order-2 flex-grow-1"><b>Attention to Detail</b> — Original full description.</div></td></tr>
        </tbody></table></div></main>''')
        data = parse_html(raw, 'https://example.test')
        data['source'] = {'url':'https://example.test'}
        book, specs = occupation_workbook(self.info,data,raw)
        self.assertIn('Tasks',book.sheetnames)
        self.assertIn('Work Styles',book.sheetnames)
        self.assertNotIn('条目明细',book.sheetnames)
        self.assertNotIn('原文段落',book.sheetnames)
        self.assertEqual(specs['Tasks']['rows'][0], [1,'77','Core','Original one.'])
        self.assertEqual(specs['Work Styles']['rows'][0][-1], '— Original full description.')
        self.assertEqual(specs['New official section']['rows'][0][-1], 'Keep this exact sentence.')
        self.assertIn('62 more',specs['Software Skills']['rows'][0][-1])
        book.close()

    def test_compact_summary_preserves_manual_entries_and_places_them_near_identity(self):
        from material_preparation.occupation_review_layout import summary_rows,summary_workbook,HEADERS
        self.fetch()
        parse_occupation('example',self.info)
        previous = {'15-1252.00':{'JD':'通过','审核备注':'Keep note','custom':'Keep custom'}}
        rows, states = summary_rows(self.registry,previous,['custom'])
        self.assertEqual(rows[0][HEADERS.index('JD')],'通过')
        self.assertEqual(rows[0][HEADERS.index('审核备注')],'Keep note')
        self.assertEqual(rows[0][-1],'Keep custom')
        self.assertLess(HEADERS.index('JD'),10)
        book = summary_workbook(rows,['custom'])
        self.assertEqual(book.sheetnames,['职业汇总'])
        self.assertEqual(book['职业汇总'].max_row,2)
        book.close()

    def test_native_relative_link_round_trips_chinese_filename(self):
        from material_preparation.occupation_review_layout import local_workbook_link
        summary=self.root/'review'/'职业与材料审核.xlsx'
        target=self.root/'sources'/'A directory with spaces'/'职业资料.xlsx'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'target-exists')
        link=local_workbook_link(summary,target)
        self.assertFalse(link.lower().startswith('file:'))
        self.assertNotIn('%',link)
        self.assertNotIn('\\',link)
        self.assertEqual((summary.parent/link).resolve(),target.resolve())
        book=__import__('openpyxl').Workbook()
        book.active['A1']='打开职业资料'
        book.active['A1'].hyperlink=link
        save_workbook(summary,book,keep_backup=False)
        saved=load_workbook(summary)
        try:
            self.assertEqual(saved.active['A1'].hyperlink.target,link)
        finally:
            saved.close()

    def test_excel_workbook_jump_formula_is_portable_without_hardcoded_root(self):
        from material_preparation.occupation_review_layout import workbook_jump_formula
        summary=self.root/'material_preparation/review/职业与材料审核.xlsx'
        target=self.root/'material_preparation/sources/occupations/Software_Developers_15-1252.00/onet/职业资料.xlsx'
        formula=workbook_jump_formula(target,summary)
        self.assertNotIn(str(self.root),formula)
        self.assertNotIn(':',formula)
        self.assertNotIn('file:',formula.lower())
        self.assertNotIn('%',formula)
        self.assertIn('CELL("filename",A1)',formula)
        self.assertIn('sources/occupations/Software_Developers_15-1252.00/onet/职业资料.xlsx',formula)
        self.assertIn('Overview!A1',formula)


if __name__ == '__main__':
    unittest.main()
