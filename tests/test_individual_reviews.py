import copy
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from unittest.mock import patch
from openpyxl import Workbook
from shared import common as c
from material_preparation.export_individual_reviews import OCCUPATION_HEADERS,preserve_reviews,morality_items


class IndividualReviewTests(unittest.TestCase):
    def test_retiring_display_hash_preserves_opinion_for_the_same_original(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'A.xlsx'
            material={'材料编号':'15-1252.00_R01','材料批次':'batch','原稿SHA256':'original','_links':{}}
            old_headers=OCCUPATION_HEADERS+['审核文本SHA256']
            row={**material,'审核文本SHA256':'old_formatted_copy','审核结论':'可用','问题说明':'原意见保留'}
            w=Workbook();s=w.active;s.title='材料审核'
            for _ in range(4):s.append([])
            s.append(old_headers);s.append([row.get(key) for key in old_headers]);w.save(path);w.close()
            rows,_=preserve_reviews(path,OCCUPATION_HEADERS,[material])
            self.assertEqual(rows[0][OCCUPATION_HEADERS.index('审核结论')],'可用')
            self.assertEqual(rows[0][OCCUPATION_HEADERS.index('问题说明')],'原意见保留')

    def test_removing_redundant_jd_column_keeps_reviewer_decisions(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'A.xlsx'
            material={'材料编号':'15-1252.00_R01','材料批次':'batch','原稿SHA256':'raw','审核文本SHA256':'display','_links':{}}
            old_headers=OCCUPATION_HEADERS[:5]+['对应JD']+OCCUPATION_HEADERS[5:]
            row={**material,'对应JD':'打开对应JD','审核结论':'可用','问题说明':'已有人工意见'}
            w=Workbook();s=w.active;s.title='材料审核'
            for _ in range(4):s.append([])
            s.append(old_headers);s.append([row.get(name) for name in old_headers]);w.save(path);w.close()
            rows,_=preserve_reviews(path,OCCUPATION_HEADERS,[material])
            self.assertEqual(rows[0][OCCUPATION_HEADERS.index('审核结论')],'可用')
            self.assertEqual(rows[0][OCCUPATION_HEADERS.index('问题说明')],'已有人工意见')
            self.assertNotIn('对应JD',OCCUPATION_HEADERS)

    def test_empty_template_does_not_have_an_invalid_empty_hyperlinks_element(self):
        from material_preparation.review_material_links import external_links
        from material_preparation.review_navigation import xml,Q
        with tempfile.TemporaryDirectory() as temp:
            original=Path(temp)/'a.xlsx';target=Path(temp)/'b.xlsx'
            w=Workbook();w.save(original);w.close()
            external_links(original,target,{'review':str(target),'links':[]})
            with ZipFile(target) as z:self.assertIsNone(xml(z.read('xl/worksheets/sheet1.xml')).find(Q('hyperlinks')))

    def test_source_jump_reuses_master_formula_and_preserves_other_workbook_parts(self):
        from openpyxl import load_workbook
        from material_preparation.export_individual_reviews import patch_workbook_jumps
        from material_preparation.occupation_review_layout import workbook_jump_formula
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);source=folder/'职业资料.xlsx';source.write_bytes(b'source')
            raw=folder/'jd.txt';raw.write_text('unchanged original',encoding='utf-8')
            target=folder/'review.xlsx'
            material={'材料编号':'15-1252.00_JD','材料批次':'batch','原稿SHA256':'raw',
                      '_links':{'材料文件':str(raw),'职业资料':str(source)}}
            self.make_file(target,material)
            book=load_workbook(target);sheet=book.active
            sheet['E6']='打开材料';sheet['E6'].hyperlink='jd.txt'
            sheet['F6']='打开职业资料';sheet['F6'].hyperlink='职业资料.xlsx'
            sheet.column_dimensions['K'].hidden=True;sheet.column_dimensions['L'].hidden=True
            sheet.column_dimensions['I'].width=57
            sheet.freeze_panes='E6'
            sheet.sheet_view.pane.topLeftCell='F17'
            book.save(target);book.close()
            with ZipFile(target) as z:before={n:z.read(n) for n in z.namelist()}
            rows,links=preserve_reviews(target,OCCUPATION_HEADERS,[material])
            self.assertEqual(rows[0][5],workbook_jump_formula(source,target))
            self.assertEqual([x['cell'] for x in links],['E6'])
            patch_workbook_jumps(target,{'review':str(target),'headers':OCCUPATION_HEADERS,'rows':rows,'links':links})
            with ZipFile(target) as z:
                for name,data in before.items():
                    if name not in {'xl/worksheets/sheet1.xml','xl/worksheets/_rels/sheet1.xml.rels'}:
                        self.assertEqual(z.read(name),data,name)
            book=load_workbook(target);sheet=book.active
            self.assertEqual(sheet['F6'].value,workbook_jump_formula(source,target));self.assertIsNone(sheet['F6'].hyperlink)
            self.assertEqual(sheet['I6'].value,'保留独立意见')
            self.assertEqual(sheet.column_dimensions['I'].width,57)
            self.assertEqual(sheet.freeze_panes,'F6')
            self.assertEqual(sheet.sheet_view.pane.topLeftCell,'F6')
            self.assertEqual(sheet['E6'].hyperlink.target,'jd.txt')
            book.close()

    def make_file(self,path,material):
        w=Workbook();s=w.active;s.title='材料审核'
        for _ in range(4):s.append([])
        s.append(OCCUPATION_HEADERS)
        row={**material,'审核结论':'需重新生成','问题类型':'自然性','问题说明':'保留独立意见'}
        s.append([row.get(name) for name in OCCUPATION_HEADERS]);w.save(path);w.close()

    def test_review_follows_material_identity_not_row_order(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'A.xlsx'
            one={'材料编号':'15-1252.00_R01','材料批次':'batch','原稿SHA256':'raw','审核文本SHA256':'display','_links':{}}
            self.make_file(p,one)
            two={**one,'材料编号':'15-1252.00_R02'}
            rows,links=preserve_reviews(p,OCCUPATION_HEADERS,[two,one])
            note=OCCUPATION_HEADERS.index('问题说明');decision=OCCUPATION_HEADERS.index('审核结论')
            self.assertIsNone(rows[0][note]);self.assertEqual(rows[1][note],'保留独立意见')
            self.assertEqual(rows[1][decision],'需重新生成')
            with self.assertRaisesRegex(ValueError,'停止覆盖'):preserve_reviews(p,OCCUPATION_HEADERS,[two])
            changed={**one,'原稿SHA256':'new'}
            with self.assertRaisesRegex(ValueError,'停止覆盖'):preserve_reviews(p,OCCUPATION_HEADERS,[changed])

    def test_morality_only_includes_explicitly_selected_complete_generated_pairs(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(c,'ROOT',Path(temp)):
            folder=Path(temp)/'material_preparation/drafts/morality';folder.mkdir(parents=True)
            record={'pair_id':'CARE_001','foundation':'care','neutral':'原始中性正文','negative':'原始负面正文'}
            path=folder/'CARE_001.json';path.write_text(c.canonical(record),encoding='utf-8');before=path.read_bytes()
            self.assertEqual(morality_items({'morality_pairs':[]}),[])
            rows=morality_items({'morality_pairs':['CARE_001']})
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['材料编号'],'CARE_001')
            self.assertEqual(path.read_bytes(),before)
            record['negative']='';path.write_text(c.canonical(record),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'完整'):morality_items({'morality_pairs':['CARE_001']})


if __name__=='__main__':unittest.main()
