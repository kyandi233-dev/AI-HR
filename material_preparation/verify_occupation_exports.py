"""Verify exported values against saved initial HTML sources; no network requests."""
if __name__ == '__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import csv
from pathlib import Path
from collections import defaultdict
from openpyxl import load_workbook
from shared import common as c
from material_preparation.onet_data import read_registry, source_folder, source_identity
from material_preparation.export_occupation_review import build_rows, SHEETS, SUMMARY, MANUAL


def verify(path):
    registry = read_registry()
    expected, local = build_rows(registry)
    book = load_workbook(path, read_only=True)
    counts = {}
    for key in SHEETS:
        sheet = book[key]
        actual = list(sheet.iter_rows(min_row=2, values_only=True))
        counts[key] = len(actual)
        if len(actual) != len(expected[key]):
            raise ValueError(f'{key}: row count mismatch')
        for row, reference in zip(actual, expected[key]):
            limit = len(SUMMARY) if key == '职业汇总' else len(reference)
            # The changed-source re-review notice can depend on previous human review data.
            for col in range(limit):
                if key == '职业汇总' and SHEETS[key][col] == '提示':
                    continue
                a, b = row[col], reference[col]
                if ('' if a is None else a) != ('' if b is None else b):
                    raise ValueError(f'{key}: value mismatch at source row {row[0]}, column {col+1}')
        with (path.parent/'csv'/(key+'.csv')).open(encoding='utf-8-sig', newline='') as file:
            csv_rows = list(csv.reader(file))
        if len(csv_rows)-1 != len(actual):
            raise ValueError(f'{key}: CSV row count mismatch')
        for excel, csv_row in zip(actual, csv_rows[1:]):
            if [str(v) if v is not None else '' for v in excel] != csv_row:
                raise ValueError(f'{key}: CSV values do not match workbook')
    book.close()
    for slug, data in local.items():
        folder = source_folder(registry[slug])
        source_identity(folder)
        parsed = c.load_json(folder/'structured_en.json')
        texts = defaultdict(list)
        for row in data['原文段落']:
            texts[row[2]].append(row[-1])
        for section in parsed['sections']:
            if ''.join(texts[section['id']]) != section['source_text']:
                raise ValueError(f'{slug}: source text is incomplete')
        with_book = load_workbook(folder/'职业资料.xlsx', read_only=True)
        for key, rows in data.items():
            if with_book[key].max_row-1 != len(rows):
                raise ValueError(f'{slug}: individual workbook row count mismatch in {key}')
        with_book.close()
    print(f'核验通过：职业={len(registry)}；独立资料表={len(local)}；各表行数={counts}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workbook', type=Path, default=c.ROOT/'material_preparation/review/职业与材料审核.xlsx')
    verify(parser.parse_args().workbook)
