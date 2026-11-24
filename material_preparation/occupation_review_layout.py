"""Readable review layout over saved sources. Does not change source files or prompts."""
import argparse
import csv
import math
import os
import textwrap
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup, NavigableString
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter
from shared import common as c
from material_preparation.onet_data import digest, read_registry, source_folder, source_identity, write_json
from material_preparation.export_occupation_review import existing_manual, MANUAL, save_workbook

HEADERS = ['大类编码', 'Job Family', 'Occupation', 'O*NET Code', '职业资料文件',
           '是否选用', '人工分类', 'JD', '简历1', '简历2', '审核备注', '审核人', '审核日期',
           '资料状态', '来源网址']


def text(node):
    return node.get_text(' ', strip=True) if node else ''


def add_sheet(book, title, headers, rows, widths=None):
    title = title[:31]
    if title in book.sheetnames:
        raise ValueError(f'Duplicate review sheet name: {title}')
    sheet = book.create_sheet(title)
    sheet.append(headers)
    for row in rows:
        if any(isinstance(v, str) and len(v) > 32767 for v in row):
            raise ValueError(f'Long cell in {title}; source is preserved, will not truncate')
        sheet.append(row)
    widths = widths or [12] + [30]*(len(headers)-2) + [110]
    if len(widths) != len(headers):
        raise ValueError(f'Column width count mismatch: {title}')
    sheet.freeze_panes = 'A2'
    sheet.auto_filter.ref = sheet.dimensions
    sheet.sheet_view.zoomScale = 90
    body_font = Font(name='Calibri', size=11)
    alignment = Alignment(vertical='top', wrap_text=True)
    for i, width in enumerate(widths, 1):
        sheet.column_dimensions[get_column_letter(i)].width = width
    for cell in sheet[1]:
        cell.font = Font(name='Calibri', size=11, bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='234E70')
        cell.alignment = alignment
    sheet.row_dimensions[1].height = 30
    for row in sheet.iter_rows(min_row=2):
        lines = 1
        for i, cell in enumerate(row):
            cell.font = body_font
            cell.alignment = alignment
            if isinstance(cell.value, str):
                cell.data_type = 's'
                lines = max(lines, sum(max(1, len(textwrap.wrap(line, max(8, int(widths[i]*0.87)))))
                                       for line in cell.value.splitlines()) or 1)
        sheet.row_dimensions[row[0].row].height = min(409, max(30, lines*15+6))
    sheet.print_options.horizontalCentered = True
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = 'landscape'
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.print_title_rows = '1:1'
    return sheet


def top_list_items(section):
    result = []
    for listing in section.find_all(['ul', 'ol']):
        if not any(p.name in ['ul', 'ol', 'dl', 'table'] for p in listing.parents if p is not section):
            result.extend(listing.find_all('li', recursive=False))
    return result


def response_text(li):
    percent = li.select_one('span.h6')
    answer = li.select_one('div.flex-grow-1.ms-2')
    if answer:
        spans = [s for s in answer.find_all('span', recursive=False)
                 if 'visually-hidden' not in s.get('class', [])]
        value = ' '.join(text(s) for s in spans) if spans else text(answer)
        return text(percent), value
    return '', text(li)


def section_table(section, saved):
    """Presentation extraction from original HTML; no semantic selection or rewriting."""
    sid = saved['id']
    tables = section.find_all('table')
    if tables:
        if len(tables) != 1:
            raise ValueError(f'Multiple native tables in {sid}; specify a layout rather than merging silently')
        table = tables[0]
        headers = ['No.']+[text(h) for h in table.select('thead th')]
        described = any(cell.select_one('div.order-2.flex-grow-1 b') for cell in table.select('tbody tr td:last-child'))
        if described:
            headers.append('Description')
        rows = []
        for number, tr in enumerate(table.select('tbody > tr'), 1):
            values = []
            for cell in tr.find_all(['td', 'th'], recursive=False):
                primary = cell.select_one('div.order-2.flex-grow-1')
                values.append(cell.get('data-text', text(primary) if primary else text(cell)))
            if described:
                primary = tr.find_all('td', recursive=False)[-1].select_one('div.order-2.flex-grow-1')
                label = primary.find('b') if primary else None
                description = ''.join(n.get_text(' ', strip=False) if hasattr(n, 'get_text') else str(n)
                                      for n in primary.children if n is not label).strip() if primary else ''
                values.append(description)
            rows.append([number]+values)
        widths = [8]+[17]*(len(headers)-2)+[115]
        if described:
            widths[-2] = 38
        return headers, rows, widths
    if section.find('dl'):
        rows = []
        for listing in section.find_all('dl'):
            for dt in listing.find_all('dt', recursive=False):
                dd = dt.find_next_sibling('dd')
                rows.append([text(dt), text(dd)])
        # Actual descriptions, query controls and choices all remain in these source fields.
        return ['Field', 'Content'], rows, [30, 120]
    items = top_list_items(section)
    if sid == 'WorkContext':
        rows = []
        for number, li in enumerate(items, 1):
            primary = li.select_one('div.order-2.flex-grow-1') or li
            label = primary.find('b')
            question = ''.join(str(n) for n in primary.children if isinstance(n, NavigableString)).strip()
            answers = [' — '.join(filter(None, response_text(answer))) for answer in primary.select('ul > li')]
            rows.append([number, text(label), question, '\n'.join(answers)])
        return ['No.', 'Work Context', 'Question', 'Responses shown'], rows, [8, 34, 70, 65]
    if sid == 'SoftwareSkills':
        rows = []
        for number, li in enumerate(items, 1):
            primary = li.select_one('div.order-2.flex-grow-1') or li
            label = primary.find('b')
            # Exclude only the category label already shown in its own column.
            examples = ''.join(n.get_text(' ', strip=False) if hasattr(n, 'get_text') else str(n)
                               for n in primary.children if n is not label).strip()
            rows.append([number, text(label), examples])
        return ['No.', 'Software category', 'Examples shown on initial page'], rows, [8, 38, 115]
    if sid == 'Education':
        return ['No.', 'Respondents', 'Education'], [[i, *response_text(li)] for i, li in enumerate(items, 1)], [8, 18, 110]
    if sid in ['RelatedOccupations', 'CareerSummaries', 'ProfessionalAssociations']:
        rows = []
        for number, li in enumerate(items, 1):
            anchor = li.find('a', href=True)
            if sid == 'RelatedOccupations':
                code = li.select_one('span.d-none.d-sm-inline-block')
                rows.append([number, text(code), text(anchor), anchor.get('href', '') if anchor else ''])
            else:
                rows.append([number, text(anchor) if anchor else text(li), anchor.get('href', '') if anchor else ''])
        if sid == 'RelatedOccupations':
            return ['No.', 'O*NET Code', 'Occupation', 'URL'], rows, [8, 18, 65, 65]
        return ['No.', 'Name', 'URL'], rows, [8, 75, 80]
    if items:
        rows = []
        for number, li in enumerate(items, 1):
            primary = li.select_one('div.order-2.flex-grow-1') or li
            rows.append([number, text(primary)])
        return ['No.', saved['title'] or sid], rows, [8, 125]
    # Unknown text-only sections retain whole native paragraphs, not character slices.
    paragraphs = [text(p) for p in section.find_all('p')]
    if not paragraphs:
        paragraphs = [saved['source_text']]
    return ['No.', 'Content'], [[i, p] for i, p in enumerate(paragraphs, 1)], [8, 125]


def occupation_workbook(info, data, raw):
    soup = BeautifulSoup(raw, 'html.parser')
    book = Workbook()
    book.remove(book.active)
    overview_rows = [['Occupation', info['onet_name']], ['O*NET Code', info['onet_code']],
                     ['Job Family', info.get('job_family_name', '')], ['Source', data['source']['url']]]
    h1 = soup.find('h1')
    if h1:
        overview_rows.append(['Page heading', text(h1)])
        for sibling in h1.next_siblings:
            if getattr(sibling, 'name', None) == 'nav' or (getattr(sibling, 'get', None) and 'reportsection' in sibling.get('class', [])):
                break
            if getattr(sibling, 'name', None) == 'p':
                overview_rows.append(['Overview', text(sibling)])
    overview = add_sheet(book, 'Overview', ['Field', 'Content'], overview_rows, [25, 125])
    overview.cell(5, 2).hyperlink = data['source']['url']
    specs = {}
    for saved in data['sections']:
        if saved['id'] == 'Overview':
            continue
        section = soup.find(id=saved['id'])
        if section is None:
            raise ValueError(f"Missing source section: {saved['id']}")
        title = (saved['title'] or saved['id'])[:31]
        headers, rows, widths = section_table(section, saved)
        if saved['records'] and len(rows) != saved['record_count']:
            raise ValueError(f"{saved['id']}: layout has {len(rows)} rows; source has {saved['record_count']}")
        sheet = add_sheet(book, title, headers, rows, widths)
        specs[title] = {'headers': headers, 'rows': rows, 'section_id': saved['id']}
        # Source URL is attached to the native section heading, keeping data columns compact.
        sheet.cell(1, len(headers)).hyperlink = data['source']['url']+'#'+saved['id']
    start = overview.max_row+3
    overview.cell(start, 1, 'Contents')
    overview.cell(start, 2, 'Entries')
    for number, (title, spec) in enumerate(specs.items(), start+1):
        cell = overview.cell(number, 1, title)
        cell.hyperlink = f"#'{title}'!A1"
        cell.font = Font(color='0563C1', underline='single', size=11)
        overview.cell(number, 2, len(spec['rows']))
        overview.row_dimensions[number].height = 24
    return book, specs


def summary_rows(registry, previous, extra):
    rows, states = [], {}
    for slug, info in sorted(registry.items(), key=lambda item: item[1]['onet_code']):
        code = info['onet_code']
        folder = source_folder(info)
        status, sha, notice = '未整理', '', ''
        if (folder/'structured_en.json').exists():
            meta = source_identity(folder)
            sha = meta['stored_html_sha256']
            data = c.load_json(folder/'structured_en.json')
            if data['source']['stored_html_sha256'] != sha:
                raise ValueError(f'Structured data/source mismatch: {code}')
            status = '已整理'
            if any('O*NET does not collect data on military occupations.' in s['source_text'] for s in data['sections']):
                status = '资料有限（军职）'
            if data['warnings']:
                status = '需检查来源提示'
        old = previous.get(code, {})
        if old.get('来源摘要') and old['来源摘要'] != sha:
            notice = '来源已变化，请复核'
        manual = {key: old.get(key) for key in MANUAL+extra}
        values = {'大类编码': info.get('job_family_code', code[:2]), 'Job Family': info.get('job_family_name', ''),
                  'Occupation': info['onet_name'], 'O*NET Code': code, '职业资料文件': '打开职业资料' if sha else '',
                  '资料状态': status if not notice else notice, '来源网址': info.get('source_url', '') or f'https://www.onetonline.org/link/details/{code}', **manual}
        rows.append([values.get(key) for key in HEADERS+extra])
        states[code] = {'source_sha256': sha, 'workbook': str((folder/'职业资料.xlsx').relative_to(c.ROOT))}
    return rows, states


def summary_workbook(rows, extra):
    headers = HEADERS+extra
    widths = [10, 34, 43, 17, 18, 13, 18, 12, 12, 12, 42, 14, 18, 24, 40]+[24]*len(extra)
    book = Workbook()
    book.remove(book.active)
    sheet = add_sheet(book, '职业汇总', headers, rows, widths)
    sheet.freeze_panes = 'E2'
    for row in sheet.iter_rows(min_row=2):
        for i, name in enumerate(headers):
            if name in MANUAL+extra:
                row[i].fill = PatternFill('solid', fgColor='FFF2CC')
    for key, options in [('是否选用','选用,待定,不选用'),('JD','通过,需修改,不采用'),('简历1','通过,需修改,不采用'),('简历2','通过,需修改,不采用')]:
        rule = DataValidation(type='list', formula1=f'"{options}"', allow_blank=True)
        sheet.add_data_validation(rule)
        column = get_column_letter(headers.index(key)+1)
        rule.add(f'{column}2:{column}{max(2,sheet.max_row)}')
    return book


def write_review_csv(path, headers, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(headers)
        writer.writerows(rows)


def snapshot_inputs(registry):
    hashes = {}
    for info in registry.values():
        folder = source_folder(info)
        for name in ['source_details.html','source_details.txt','source_metadata.json','structured_en.json']:
            path = folder/name
            if path.exists():
                hashes[str(path.relative_to(c.ROOT))] = digest(path)
    for path in (c.ROOT/'material_preparation/prompts').glob('*.txt'):
        hashes[str(path.relative_to(c.ROOT))] = digest(path)
    return hashes


def local_workbook_link(summary_path, target):
    """A native relative filename, not a percent-encoded file URI (Excel/WPS compatible)."""
    return os.path.relpath(Path(target).resolve(), start=Path(summary_path).resolve().parent)


def workbook_jump_formula(target):
    """Excel workbook reference syntax, opening the Overview sheet without file-URI encoding."""
    reference = '['+str(Path(target).resolve())+']Overview!A1'
    return '=HYPERLINK("'+reference.replace('"','""')+'","打开职业资料")'


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=c.ROOT/'material_preparation/review/职业与材料审核.xlsx')
    parser.add_argument('--summary-only',action='store_true',help='Refresh only the summary when existing native-section workbooks are unchanged')
    args = parser.parse_args(argv)
    modern=None
    if args.output.exists():
        current=load_workbook(args.output,read_only=True)
        try:
            if 'JD是否纳入' in [cell.value for cell in next(current['职业汇总'].iter_rows())]:
                modern=c.load_json(args.output.parent/'review_navigation_manifest.json')
        finally:current.close()
    registry = read_registry()
    original = snapshot_inputs(registry)
    previous, extra = existing_manual(args.output)
    # Technical columns from the old layout are not custom reviewer columns.
    extra = [key for key in extra if key not in HEADERS]
    old_manifest_path = args.output.parent/'export_manifest.json'
    if old_manifest_path.exists():
        old_manifest = c.load_json(old_manifest_path)
        for code, state in old_manifest.get('occupations', {}).items():
            if code in previous:
                previous[code].setdefault('来源摘要', state.get('source_sha256',''))
    rows, states = summary_rows(registry, previous, extra)
    sheet_counts = {}
    for slug, info in registry.items():
        folder = source_folder(info)
        if not (folder/'structured_en.json').exists():
            continue
        data = c.load_json(folder/'structured_en.json')
        if args.summary_only:
            existing = load_workbook(folder/'职业资料.xlsx',read_only=True)
            expected_names = ['Overview']+[(s['title'] or s['id'])[:31] for s in data['sections'] if s['id']!='Overview']
            try:
                if existing.sheetnames != expected_names:
                    raise ValueError('Existing individual layout is old; run export without --summary-only')
                sheet_counts[info['onet_code']] = {name:existing[name].max_row-1 for name in expected_names[1:]}
            finally:
                existing.close()
            continue
        book, specs = occupation_workbook(info, data, (folder/'source_details.html').read_bytes())
        save_workbook(folder/'职业资料.xlsx', book, keep_backup=False)
        book.close()
        for title, spec in specs.items():
            write_review_csv(folder/'csv'/(title+'.csv'),spec['headers'],spec['rows'])
        sheet_counts[info['onet_code']] = {key:len(spec['rows']) for key,spec in specs.items()}
        print('重排：',info['onet_name'],flush=True)
    if modern:
        from material_preparation.review_material_links import run as file_review
        file_review(['--review',str(args.output),'--run-id',modern['run_id'],
                     '--jd-run-id',modern['jd_run_id'],'--execute'])
        if snapshot_inputs(registry)!=original:raise ValueError('原始存档或提示词变化')
        write_json(old_manifest_path,{'layout_version':3,'exported_utc':c.now(),'script_sha256':digest(__file__),
            'workbook_sha256':digest(args.output),'occupations':states,'sheet_counts':sheet_counts,'unchanged_inputs':original})
        print('保留新版文件链接与纳入列；独立职业资料表：',len(sheet_counts))
        return 0
    book = summary_workbook(rows, extra)
    sheet = book['职业汇总']
    for number, row in enumerate(rows,2):
        code = row[HEADERS.index('O*NET Code')]
        if states[code]['source_sha256']:
            sheet.cell(number,5).hyperlink = None
            sheet.cell(number,5).value = workbook_jump_formula(c.ROOT/states[code]['workbook'])
            sheet.cell(number,5).font = Font(color='0563C1',underline='single',size=11)
    book.calculation.fullCalcOnLoad = True
    book.calculation.forceFullCalc = True
    save_workbook(args.output,book,keep_backup=False)
    book.close()
    write_review_csv(args.output.parent/'职业汇总.csv',HEADERS+extra,rows)
    if snapshot_inputs(registry) != original:
        raise ValueError('An archived source, CSV, JSON, or prompt changed during layout export')
    write_json(old_manifest_path,{'layout_version':2,'exported_utc':c.now(),'script_sha256':digest(__file__),
                                'workbook_sha256':digest(args.output),'occupations':states,'sheet_counts':sheet_counts,
                                'unchanged_inputs':original})
    print(f'完成：总表{len(rows)}行；独立资料表{len(sheet_counts)}份；原始存档及prompt未变。')
    return 0
