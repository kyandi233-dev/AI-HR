import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from openpyxl import Workbook,load_workbook
from openpyxl.styles import Font,PatternFill
from material_preparation.review_navigation import xml,encoded


class ReviewNavigationTests(unittest.TestCase):
    def test_file_link_labels_are_separate_from_inclusion_decisions(self):
        from material_preparation.review_schema import approval_value,is_approved,HEADERS,LINK_COLUMNS,APPROVAL_COLUMNS
        row={'JD':'打开JD原稿','JD是否纳入':None,'简历3（低）':'打开简历3','简历3是否纳入':1}
        self.assertFalse(is_approved(approval_value(row,'JD')))
        self.assertTrue(is_approved(approval_value(row,'简历3')))
        self.assertTrue(is_approved(approval_value({'JD':'通过'},'JD')))
        self.assertNotIn('人工分类',HEADERS)
        for link,decision in zip(LINK_COLUMNS,APPROVAL_COLUMNS):self.assertEqual(HEADERS.index(link)+1,HEADERS.index(decision))

    def test_external_targets_are_native_relative_filenames(self):
        from material_preparation.review_material_links import external_links
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);authored=folder/'authored.xlsx';target=folder/'review.xlsx'
            w=Workbook();w.active.title='职业汇总';w.active['A1']='打开简历';w.save(authored);w.close()
            raw=folder/'resumes/English_15-1252.00/R01.txt';raw.parent.mkdir(parents=True);raw.write_text('- Original.',encoding='utf-8')
            external_links(authored,target,{'review':str(target),'links':[{'cell':'A1','target':str(raw)}]})
            w=load_workbook(target)
            try:
                link=w.active['A1'].hyperlink.target
                self.assertFalse(link.startswith('file:'))
                self.assertEqual((folder/link).resolve(),raw.resolve())
                self.assertEqual(w.sheetnames,['职业汇总'])
            finally:w.close()

    def test_excel_compatibility_prefixes_survive_serialization(self):
        raw=b'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" xmlns:x15="http://schemas.microsoft.com/office/spreadsheetml/2010/11/main" mc:Ignorable="x15"><sheets/></workbook>'
        actual=encoded(xml(raw))
        self.assertIn(b'xmlns:x15=',actual)
        self.assertIn(b'Ignorable="x15"',actual)
        xml(actual)

    def test_retargeting_changes_only_native_link_targets(self):
        from material_preparation.review_material_links import retarget_links
        from shared import common as c
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);review=folder/'review.xlsx'
            raw=folder/'drafts/R01.txt';raw.parent.mkdir();raw.write_bytes(b'1. Keep original.\r\n')
            w=Workbook();s=w.active;s.title='职业汇总'
            s.append(['简历1','简历1是否纳入','审核备注'])
            s.append(['打开简历1',1,'保留意见'])
            s['A2'].hyperlink='resumes/R01.txt';s['C2'].font=Font(bold=True)
            s.freeze_panes='A2';w.save(review);w.close()
            with ZipFile(review) as z:before={n:z.read(n) for n in z.namelist()}
            payload={'review':str(review),'headers':['简历1','简历1是否纳入','审核备注'],
                     'rows':[['打开简历1',1,'保留意见']],'links':[{'cell':'A2','target':str(raw)}],
                     'sources':{str(raw):c.sha256(raw.read_bytes())}}
            retarget_links(review,payload)
            w=load_workbook(review)
            try:
                self.assertEqual(w.active['B2'].value,1);self.assertEqual(w.active['C2'].value,'保留意见')
                self.assertTrue(w.active['C2'].font.bold);self.assertEqual(w.active.freeze_panes,'A2')
                self.assertEqual((folder/w.active['A2'].hyperlink.target).resolve(),raw.resolve())
            finally:w.close()
            with ZipFile(review) as z:
                for name,contents in before.items():
                    if name not in ('xl/worksheets/sheet1.xml','xl/worksheets/_rels/sheet1.xml.rels'):
                        self.assertEqual(z.read(name),contents)
                self.assertNotIn(b'resumes/R01.txt',z.read('xl/worksheets/_rels/sheet1.xml.rels'))
            self.assertEqual(raw.read_bytes(),b'1. Keep original.\r\n')


if __name__=='__main__':unittest.main()
