"""Parse saved Details HTML without selecting, translating, or rewriting content."""
if __name__ == '__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from shared import common as c
from material_preparation.onet_data import (
    digest, read_registry, select_occupations, source_folder, source_identity, write_json,
)


def text(node):
    return node.get_text(' ', strip=True)


def outer_lists(section):
    for listing in section.find_all(['ul', 'ol', 'dl']):
        if not any(p.name in ['ul', 'ol', 'dl'] for p in listing.parents if p is not section):
            yield listing


def links(node, url):
    return [{'text': text(a), 'href_original': a.get('href', ''),
             'url': urljoin(url, a.get('href', '')), 'title': a.get('title', '')}
            for a in node.find_all('a', href=True)]


def parse_section(section, index, url, section_id=None):
    heading = section.find(['h2', 'h1'])
    title = ''.join(str(n) for n in heading.find_all(string=True, recursive=False)).strip() if heading else ''
    sid = section_id or section.get('id') or f'section_{index}'
    records = []
    for table_index, table in enumerate(section.find_all('table'), 1):
        headers = [text(h) for h in table.select('thead th')]
        for row in table.select('tbody > tr'):
            cells = row.find_all(['td', 'th'], recursive=False)
            fields = [{'name': headers[i] if i < len(headers) else f'column_{i+1}',
                       'value': cell.get('data-text', text(cell)), 'text_original': text(cell)}
                      for i, cell in enumerate(cells)]
            records.append({'kind': 'table_row', 'group': str(table_index), 'fields': fields,
                            'text': text(row), 'links': links(row, url)})
    if not records:
        for group, listing in enumerate(outer_lists(section), 1):
            for item in listing.find_all('li' if listing.name != 'dl' else 'dt', recursive=False):
                values = [item]
                if listing.name == 'dl':
                    sibling = item.find_next_sibling('dd')
                    if sibling:
                        values.append(sibling)
                records.append({'kind': 'list_item' if listing.name != 'dl' else 'field',
                                'group': str(group), 'fields': [],
                                'text': '\n'.join(text(v) for v in values),
                                'links': [a for v in values for a in links(v, url)]})
    for position, record in enumerate(records, 1):
        record['order'] = position
        record['source_key'] = next((a['href_original'] for a in record['links']
                                     if '/moreinfo/' in a['href_original']), '')
    buttons = [text(b) for b in section.select('button[data-bs-toggle="collapse"]')]
    declared = [int(m.group(1)) for b in buttons if (m := re.search(r'(\d+) displayed', b))]
    warnings = []
    group_counts = [len(listing.find_all('li' if listing.name != 'dl' else 'dt', recursive=False))
                    for listing in outer_lists(section)]
    if len(declared) == 1 and len(records) != declared[0] and declared[0] not in group_counts:
        warnings.append(f'Declared {declared[0]} items, parsed {len(records)}')
    return {'id': sid, 'order': index, 'title': title, 'records': records,
            'record_count': len(records), 'declared_counts': declared,
            'list_group_counts': group_counts,
            'source_text': section.get_text('\n', strip=True),
            'source_html_sha256': c.sha256(str(section)),
            'links': links(section, url),
            'controls': [{'tag': n.name, 'attributes': dict(n.attrs), 'text': text(n)}
                         for n in section.find_all(['select', 'input', 'button'])],
            'warnings': warnings}


def parse_html(raw, url):
    soup = BeautifulSoup(raw, 'html.parser')
    body = soup.find('main') or soup.find(id='content') or soup.body or soup
    sections = body.select('div.reportsection')
    parsed = [parse_section(s, i, url) for i, s in enumerate(sections, 1)]
    overview = BeautifulSoup(str(body), 'html.parser')
    for node in overview.select('div.reportsection'):
        node.decompose()
    parsed.insert(0, parse_section(overview, 0, url, 'Overview'))
    return {'page_title': text(soup.find('h1')) if soup.find('h1') else '',
            'sections': parsed, 'page_links': links(body, url),
            'warnings': [f"{s['id']}: {w}" for s in parsed for w in s['warnings']],
            'has_detail_sections': bool(sections)}


def parse_occupation(slug, info):
    folder = source_folder(info)
    meta = source_identity(folder)
    data = parse_html((folder / 'source_details.html').read_bytes(), meta['url'])
    data.update(occupation=slug, registry=info, source=meta,
                source_html=str((folder / 'source_details.html').relative_to(c.ROOT)),
                parser_sha256=digest(__file__), schema_version=1)
    if info['onet_code'] not in data['page_title']:
        data['warnings'].append('Page heading does not contain registered occupation code')
    if not data['has_detail_sections']:
        data['warnings'].append('No detail sections; see saved page for limited data or page changes')
    write_json(folder / 'structured_en.json', data)
    print(f"解析：{info['onet_name']} 栏目={len(data['sections'])} 提示={len(data['warnings'])}", flush=True)
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    select = parser.add_mutually_exclusive_group(required=True)
    select.add_argument('--occupation')
    select.add_argument('--all', action='store_true')
    args = parser.parse_args(argv)
    errors = 0
    for slug, info in select_occupations(read_registry(), args.occupation, args.all):
        try:
            parse_occupation(slug, info)
        except Exception as exc:
            errors += 1
            print('解析失败：', info['onet_name'], str(exc), flush=True)
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
