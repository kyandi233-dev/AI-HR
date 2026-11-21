"""Export saved O*NET sources as English XLSX/CSV; no network or AI calls."""
if __name__ == '__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import csv
import io
import json
import math
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter
from shared import common as c
from material_preparation.onet_data import digest, read_registry, source_folder, source_identity, write_json

SUMMARY = ['大类编码', 'Job Family', 'O*NET Code', 'Occupation', '抓取状态', '解析状态',
           '职业资料文件', '来源网址', 'Tasks条数', 'WorkStyles条数', '来源摘要', '提示']
MANUAL = ['是否选用', '人工分类', 'JD', '简历1', '简历2', '审核人', '审核日期', '审核备注']
SHEETS = {
    '职业汇总': SUMMARY + MANUAL,
    '模块目录': ['O*NET Code', 'Occupation', 'Section', 'Title', '条目数', '页面声明数量', '分组数量', '提示', 'Source URL'],
    'Tasks': ['O*NET Code', 'Occupation', 'Job Family', 'Source Order', 'Importance', 'Category', 'Task', 'Source Key', 'Source URL'],
    '条目明细': ['O*NET Code', 'Occupation', 'Section', 'Source Order', 'Kind', 'Group', 'Metric', 'Value', 'Category', '原始字段JSON', '原文', 'Source Key', 'Source URL'],
    '原文段落': ['O*NET Code', 'Occupation', 'Section', 'Part', 'Source Text'],
    '页面链接': ['O*NET Code', 'Occupation', 'Source Order', 'Link Text', 'Original href', 'URL', 'Title'],
}


def existing_manual(path):
    if not path.exists():
        return {}, []
    old = load_workbook(path, read_only=True)
    if '职业汇总' not in old.sheetnames:
        old.close()
        raise ValueError('Existing workbook has no 职业汇总 sheet; will not overwrite')
    rows = old['职业汇总'].iter_rows(values_only=True)
    headers = list(next(rows))
    extra = [h for h in headers if h and h not in SUMMARY and h not in MANUAL]
    result = {}
    for row in rows:
        values = dict(zip(headers, row))
        code = values.get('O*NET Code')
        if code:
            if code in result:
                raise ValueError('Duplicate code in existing review workbook')
            result[code] = values
    old.close()
    return result, extra


def build_rows(registry, previous=None, extra=None):
    previous, extra = previous or {}, extra or []
    rows = {name: [] for name in SHEETS}
    by_occupation = {}
    for slug, info in registry.items():
        code, name = info['onet_code'], info['onet_name']
        folder = source_folder(info)
        download, parsed, warnings = '未下载', '未解析', []
        data, sha = None, ''
        if (folder / 'source_metadata.json').exists():
            try:
                meta = source_identity(folder)
                sha = meta['stored_html_sha256']
                download = '已下载'
                path = folder / 'structured_en.json'
                if path.exists():
                    data = c.load_json(path)
                    if data['source']['stored_html_sha256'] != sha:
                        raise ValueError('Structured data does not match current source')
                    warnings.extend(data['warnings'])
                    parsed = '已解析' if data['has_detail_sections'] else '资料有限'
                    if warnings:
                        parsed += '（有提示）'
                    military_notice = 'O*NET does not collect data on military occupations.'
                    if any(military_notice in s['source_text'] for s in data['sections']):
                        parsed = '资料有限（来源说明）'
                        warnings.append(military_notice)
            except Exception as exc:
                download, parsed = '需检查', '需检查'
                warnings.append(str(exc))
                data = None
        old = previous.get(code, {})
        if old.get('来源摘要') and old['来源摘要'] != sha:
            warnings.append('来源已变化；保留原审核记录，请复核')
        sections = data['sections'] if data else []
        counts = {s['id']: s['record_count'] for s in sections}
        file = folder / '职业资料.xlsx'
        summary = [info.get('job_family_code', code[:2]), info.get('job_family_name', ''), code, name,
                   download, parsed, str(file.relative_to(c.ROOT)) if data else '',
                   info.get('source_url', f'https://www.onetonline.org/link/details/{code}'),
                   counts.get('Tasks', ''), counts.get('WorkStyles', ''), sha, '\n'.join(warnings)]
        summary += [old.get(key) for key in MANUAL + extra]
        rows['职业汇总'].append(summary)
        local = {key: [] for key in SHEETS if key != '职业汇总'}
        for section in sections:
            sid = section['id']
            local['模块目录'].append([code, name, sid, section['title'], section['record_count'],
                                      json.dumps(section['declared_counts']), json.dumps(section['list_group_counts']),
                                      '\n'.join(section['warnings']), data['source']['url']])
            for record in section['records']:
                fields = {f['name']: f['value'] for f in record['fields']}
                metric = next((k for k in ['Importance', 'Impact', 'Occupational Interest'] if k in fields), '')
                local['条目明细'].append([code, name, sid, record['order'], record['kind'], record['group'],
                                          metric, fields.get(metric, ''), fields.get('Category', ''),
                                          json.dumps(record['fields'], ensure_ascii=False), record['text'],
                                          record['source_key'], data['source']['url']])
                if sid == 'Tasks':
                    local['Tasks'].append([code, name, info.get('job_family_name', ''), record['order'],
                                           fields.get('Importance', ''), fields.get('Category', ''),
                                           fields.get('Task', record['text']), record['source_key'], data['source']['url']])
            # Short exact chunks are readable in Excel; concatenation restores every character.
            raw = section['source_text']
            offset, part = 0, 0
            while offset < len(raw):
                chunk = raw[offset:offset+350]
                boundaries = [i for i, ch in enumerate(chunk) if ch == '\n']
                if len(boundaries) > 4:
                    chunk = chunk[:boundaries[3]+1]
                part += 1
                local['原文段落'].append([code, name, sid, part, chunk])
                offset += len(chunk)
        if data:
            for order, link in enumerate(data['page_links'], 1):
                local['页面链接'].append([code, name, order, link['text'], link['href_original'], link['url'], link['title']])
        for key in local:
            rows[key].extend(local[key])
        if data:
            by_occupation[slug] = local
    return rows, by_occupation


def write_csv(path, headers, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig permits direct opening in Windows Excel without corrupting Chinese headers.
    with path.open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(headers)
        writer.writerows(rows)


def make_workbook(rows, headers):
    book = Workbook()
    book.remove(book.active)
    for name, values in rows.items():
        sheet = book.create_sheet(name)
        sheet.append(headers[name])
        for row in values:
            if any(isinstance(value, str) and len(value) > 32767 for value in row):
                raise ValueError(f'Excel cell exceeds limit in {name}; raw data retained, no truncation allowed')
            sheet.append(row)
        sheet.freeze_panes = 'D2' if name == '职业汇总' else 'C2'
        sheet.auto_filter.ref = sheet.dimensions
        sheet.sheet_view.zoomScale = 85
        for cell in sheet[1]:
            cell.font = Font(name='Calibri', size=11, bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor='234E70')
            cell.alignment = Alignment(vertical='center', wrap_text=True)
        sheet.row_dimensions[1].height = 34
        widths = []
        for col, header in enumerate(headers[name], 1):
            width = 22
            if header in ['Occupation', 'Job Family', 'Title']:
                width = 44
            if header in ['Task', '原文', 'Source Text', '提示', '审核备注']:
                width = 95
            if header in ['原始字段JSON', 'Source URL', '来源网址', 'URL', '职业资料文件', 'Original href']:
                width = 42
            if header in ['Source Order', '条目数', 'Part', 'Tasks条数', 'WorkStyles条数', '大类编码', 'Kind', 'Group']:
                width = 14
            sheet.column_dimensions[get_column_letter(col)].width = width
            widths.append(width)
        for cells in sheet.iter_rows(min_row=2):
            max_lines = 1
            for index, cell in enumerate(cells):
                if isinstance(cell.value, str):
                    # Source strings beginning '=' must remain text, never spreadsheet formulas.
                    cell.data_type = 's'
                    max_lines = max(max_lines, sum(max(1, math.ceil(len(line) / widths[index])) for line in cell.value.split('\n')))
                cell.font = Font(name='Calibri', size=11)
                cell.alignment = Alignment(vertical='top', wrap_text=True)
                if name == '职业汇总' and index >= len(SUMMARY):
                    cell.fill = PatternFill('solid', fgColor='FFF2CC')
            sheet.row_dimensions[cells[0].row].height = min(120, max(30, max_lines * 14))
        if name == '职业汇总':
            for key, options in [('是否选用', '选用,待定,不选用'), ('JD', '通过,需修改,不采用'),
                                 ('简历1', '通过,需修改,不采用'), ('简历2', '通过,需修改,不采用')]:
                validation = DataValidation(type='list', formula1=f'"{options}"', allow_blank=True)
                sheet.add_data_validation(validation)
                col = get_column_letter(headers[name].index(key) + 1)
                validation.add(f'{col}2:{col}{max(2, sheet.max_row)}')
            for row in sheet.iter_rows(min_row=2):
                if row[6].value:
                    row[6].hyperlink = Path(c.ROOT / row[6].value).as_uri()
                    row[6].font = Font(color='0563C1', underline='single')
                if row[7].value:
                    row[7].hyperlink = row[7].value
        elif name == '模块目录':
            for row in sheet.iter_rows(min_row=2):
                row[-1].hyperlink = row[-1].value
    notes = book.create_sheet('使用说明')
    for row in [
        ['项目', '说明'],
        ['抓取范围', 'Only initial Details responses. No more links, CSV links, state searches, or external sites are fetched.'],
        ['原文', 'English source content is not translated, summarized, selected, re-ranked, or edited.'],
        ['条目单位', 'Counts are source rows/list items/layout fields, not uniformly skills; queries are not downloaded search results.'],
        ['原文段落', 'All section text is retained. Long text is split into ordered parts, never truncated. Full original HTML is saved beside the workbook.'],
        ['人工填写', 'Yellow columns in 职业汇总 are blank initially and preserved by O*NET Code on re-export. New custom columns are also preserved.'],
        ['来源变化', 'A source hash change adds a re-review notice; existing human entries are retained.'],
        ['Excel更新', 'Re-export rebuilds source sheets, preserves only review columns in 职业汇总, and saves the previous workbook under backups.'],
        ['目录链接', 'Local workbook links use this machine’s absolute paths. Re-export after moving the repository.'],
        ['数据依据', 'Source URL and SHA-256 are in 职业汇总 and each occupation source_metadata.json.'],
    ]:
        notes.append(row)
    notes.column_dimensions['A'].width = 20
    notes.column_dimensions['B'].width = 120
    for row in notes:
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical='top')
        notes.row_dimensions[row[0].row].height = 42
    return book


def encode_carriage_returns(path):
    """XML parsers normalize literal CR; character references preserve exact source text."""
    original = path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(original)) as archive:
        changed = any(b'\r' in archive.read(n) for n in archive.namelist() if n.startswith('xl/worksheets/') and n.endswith('.xml'))
        if not changed:
            return False
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as encoded:
            for item in archive.infolist():
                content = archive.read(item.filename)
                if item.filename.startswith('xl/worksheets/') and item.filename.endswith('.xml'):
                    # et_xmlfile's Windows text writer expands LF to CRLF, even inside
                    # cell strings. Undo that transport expansion before encoding original CR.
                    if os.name == 'nt':
                        content = content.replace(b'\r\n', b'\n')
                    content = content.replace(b'\r', b'&#13;')
                encoded.writestr(item, content)
    path.write_bytes(output.getvalue())
    return True


def save_workbook(path, book):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(suffix='.xlsx', dir=path.parent)
    os.close(fd)
    try:
        book.save(temp)
        encode_carriage_returns(Path(temp))
        # On Windows replacing an open workbook fails, preserving the user's old file.
        if path.exists():
            backup = path.parent / 'backups' / (path.stem + '_' + c.now().replace(':', '-').replace('+', '_') + '.xlsx')
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, backup)
        os.replace(temp, path)
    finally:
        if Path(temp).exists():
            Path(temp).unlink()


def main(argv=None):
    from material_preparation.occupation_review_layout import run
    return run(argv)


if __name__ == '__main__':
    raise SystemExit(main())
