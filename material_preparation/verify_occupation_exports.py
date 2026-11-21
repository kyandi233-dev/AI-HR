"""Verify readable review workbooks against saved HTML and untouched archives."""
if __name__ == '__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import csv
from pathlib import Path
from openpyxl import load_workbook
from shared import common as c
from material_preparation.onet_data import read_registry, source_folder, source_identity, digest
from material_preparation.occupation_review_layout import HEADERS, occupation_workbook, summary_rows


def compare(actual, expected, label):
    actual = list(actual)
    if len(actual) != len(expected):
        raise ValueError(f'{label}: row count {len(actual)} != {len(expected)}')
    for number, (a, b) in enumerate(zip(actual, expected), 1):
        if [('' if v is None else v) for v in a] != [('' if v is None else v) for v in b]:
            raise ValueError(f'{label}: value mismatch at row {number}')


def verify(path):
    manifest = c.load_json(path.parent/'review_layout_manifest.json')
    for relative, sha in manifest['unchanged_inputs'].items():
        if digest(c.ROOT/relative) != sha:
            raise ValueError(f'Archived input was changed: {relative}')
    registry = read_registry()
    book = load_workbook(path, read_only=True)
    try:
        if book.sheetnames != ['职业汇总']:
            raise ValueError('Review summary must contain only 职业汇总')
        values = list(book['职业汇总'].iter_rows(values_only=True))
        headers = list(values[0])
        if headers[:len(HEADERS)] != HEADERS:
            raise ValueError('Review header mismatch')
        previous = {row[headers.index('O*NET Code')]:dict(zip(headers,row)) for row in values[1:]}
        expected, _ = summary_rows(registry, previous, headers[len(HEADERS):])
        # Summary records must retain official identity, order and all reviewer fields.
        for a,b in zip(values[1:],expected):
            for i,name in enumerate(headers):
                if name == '资料状态':
                    continue
                if (a[i] or '') != (b[i] or ''):
                    raise ValueError(f'Summary field mismatch: {name}')
        if len(values)-1 != len(registry) or len(previous)!=len(registry):
            raise ValueError('Summary occupation count mismatch')
    finally:
        book.close()
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
                with (folder/'review_csv'/(title+'.csv')).open(encoding='utf-8-sig',newline='') as file:
                    csv_values = list(csv.reader(file))
                expected_csv = [spec['headers']]+[[str(v) if v is not None else '' for v in row] for row in spec['rows']]
                compare(csv_values,expected_csv,info['onet_name']+'/'+title+'.csv')
        finally:
            actual_book.close()
            expected_book.close()
    with (path.parent/'review_csv/职业汇总.csv').open(encoding='utf-8-sig',newline='') as file:
        compare(list(csv.reader(file)),[[str(v) if v is not None else '' for v in row] for row in values],'summary CSV')
    print(f'核验通过：职业={len(registry)}；独立资料表={len(registry)}；Tasks={counts.get("Tasks",0)}；全部栏目、CSV及原始存档一致。')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workbook',type=Path,default=c.ROOT/'material_preparation/review/职业与材料审核.xlsx')
    verify(parser.parse_args().workbook)
