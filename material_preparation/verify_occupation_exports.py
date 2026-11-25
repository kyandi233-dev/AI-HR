"""Verify readable review workbooks against saved HTML and untouched archives."""
if __name__ == '__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import csv
import os
from pathlib import Path
from openpyxl import load_workbook
from shared import common as c
from material_preparation.onet_data import read_registry, source_folder, source_identity, digest
from material_preparation.occupation_review_layout import HEADERS, occupation_workbook, summary_rows, workbook_jump_formula


def compare(actual, expected, label):
    actual = list(actual)
    if len(actual) != len(expected):
        raise ValueError(f'{label}: row count {len(actual)} != {len(expected)}')
    for number, (a, b) in enumerate(zip(actual, expected), 1):
        if [('' if v is None else v) for v in a] != [('' if v is None else v) for v in b]:
            raise ValueError(f'{label}: value mismatch at row {number}')


def verify_archived_inputs(manifest,strict_templates=False):
    template_changes=[]
    for relative, sha in manifest['unchanged_inputs'].items():
        if digest(c.ROOT/relative) != sha:
            if relative.replace('\\','/').startswith('material_preparation/prompts/') and not strict_templates:
                template_changes.append(relative)
                continue
            raise ValueError(f'Archived input was changed: {relative}')
    return template_changes


def verify(path,strict_templates=False):
    manifest = c.load_json(path.parent/'export_manifest.json')
    changes=verify_archived_inputs(manifest,strict_templates)
    if changes:print('生成模板相对旧导出已有新版本：',len(changes),'项；原始来源仍严格校验，各次实际提示词以input记录为准。')
    registry = read_registry()
    book = load_workbook(path, read_only=True)
    try:
        if book.sheetnames != ['职业汇总']:
            raise ValueError('Review summary must contain only 职业汇总')
        values = list(book['职业汇总'].iter_rows(values_only=True))
        headers = list(values[0])
        modern='JD是否纳入' in headers
        if not modern and headers[:len(HEADERS)] != HEADERS:
            raise ValueError('Review header mismatch')
        previous = {row[headers.index('O*NET Code')]:dict(zip(headers,row)) for row in values[1:]}
        if modern:
            from material_preparation.review_material_links import model,validate
            state=c.load_json(path.parent/'review_navigation_manifest.json')
            payload=model(path,state['run_id'],state['jd_run_id']);validate(path,payload)
            expected=payload['rows']
        else:expected, _ = summary_rows(registry, previous, headers[len(HEADERS):])
        # Summary records must retain official identity, order and all reviewer fields.
        for a,b in zip(values[1:],expected):
            for i,name in enumerate(headers):
                if name in ['资料状态','职业资料文件']:
                    continue
                if (a[i] or '') != (b[i] or ''):
                    raise ValueError(f'Summary field mismatch: {name}')
        if len(values)-1 != len(registry) or len(previous)!=len(registry):
            raise ValueError('Summary occupation count mismatch')
    finally:
        book.close()
    links_book = load_workbook(path,read_only=False)
    try:
        for row in links_book['职业汇总'].iter_rows(min_row=2):
            code = row[3].value
            expected_target = (c.ROOT/manifest['occupations'][code]['workbook']).resolve()
            if row[4].value != workbook_jump_formula(expected_target, path) or row[4].hyperlink:
                raise ValueError(f'Invalid Excel workbook jump formula: {code}')
            if not expected_target.is_file():
                raise ValueError(f'Workbook target does not exist: {code}: {expected_target}')
    finally:
        links_book.close()
    counts = {}
    for info in registry.values():
        folder = source_folder(info)
        source_identity(folder)
        data = c.load_json(folder/'structured_en.json')
        expected_book, specs = occupation_workbook(info,data,(folder/'source_details.html').read_bytes())
        actual_book = load_workbook(folder/'职业资料.xlsx', read_only=True)
        try:
            if actual_book.sheetnames != expected_book.sheetnames:
                raise ValueError(f'Section sheet mismatch: {info["onet_name"]}')
            for name in expected_book.sheetnames:
                compare(actual_book[name].iter_rows(values_only=True),
                        list(expected_book[name].iter_rows(values_only=True)),info['onet_name']+'/'+name)
            for title,spec in specs.items():
                counts[title] = counts.get(title,0)+len(spec['rows'])
                with (folder/'csv'/(title+'.csv')).open(encoding='utf-8-sig',newline='') as file:
                    csv_values = list(csv.reader(file))
                expected_csv = [spec['headers']]+[[str(v) if v is not None else '' for v in row] for row in spec['rows']]
                compare(csv_values,expected_csv,info['onet_name']+'/'+title+'.csv')
        finally:
            actual_book.close()
            expected_book.close()
    csv_expected = [[str(v) if v is not None else '' for v in row] for row in values]
    if not modern:
        for row in csv_expected[1:]:row[headers.index('职业资料文件')] = '打开职业资料'
    with (path.parent/'职业汇总.csv').open(encoding='utf-8-sig',newline='') as file:
        compare(list(csv.reader(file)),csv_expected,'summary CSV')
    print(f'核验通过：职业={len(registry)}；独立资料表={len(registry)}；Tasks={counts.get("Tasks",0)}；全部栏目、CSV及原始存档一致。')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workbook',type=Path,default=c.ROOT/'material_preparation/review/职业与材料审核.xlsx')
    parser.add_argument('--strict-templates',action='store_true',help='同时要求当前模板与旧导出时版本完全一致')
    args=parser.parse_args();verify(args.workbook,args.strict_templates)
