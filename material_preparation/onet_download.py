"""Download only the initial Details response. Never follow more/table links."""
import argparse
import shutil
import time
from bs4 import BeautifulSoup
import requests
from shared import common as c
from material_preparation.onet_data import (
    digest, read_registry, select_occupations, source_folder, source_identity, write_json,
)


def fetch_onet(args, occ):
    if args.occupation not in occ:
        raise ValueError('未知职业')
    info = occ[args.occupation]
    url = f"https://www.onetonline.org/link/details/{info['onet_code']}"
    folder = source_folder(info)
    if not args.execute:
        print('预览：只下载初始详情页', url)
        print('保存目录：', folder.relative_to(c.ROOT))
        return {'status': 'preview', 'url': url}
    if (folder / 'source_metadata.json').exists():
        source_identity(folder)
        print('复用：', info['onet_name'], flush=True)
        return {'status': 'reused', 'url': url}
    if folder.exists() and any(folder.iterdir()):
        raise ValueError(f'来源目录不完整，保留现场，不覆盖：{folder}')
    legacy = c.ROOT / 'material_preparation/sources/occupations' / args.occupation / 'onet'
    if (legacy / 'source_metadata.json').exists():
        meta = source_identity(legacy)
        if meta['url'] != url:
            raise ValueError('旧来源与登记职业不一致')
        folder.mkdir(parents=True, exist_ok=True)
        for name in ['source_details.html', 'source_details.txt', 'source_metadata.json']:
            shutil.copyfile(legacy / name, folder / name)
        print('复用旧下载（原文件保留）：', info['onet_name'], flush=True)
        return {'status': 'reused_legacy', 'url': url, 'legacy_path': str(legacy)}
    response = requests.get(url, timeout=45, allow_redirects=False,
                            headers={'User-Agent': 'Mozilla/5.0 (compatible; Academic research download)'})
    response.raise_for_status()
    if response.status_code != 200:
        raise ValueError(f'初始详情页未返回200（不跟随重定向）：{response.status_code}')
    soup = BeautifulSoup(response.content, 'html.parser')
    if not soup.find('h1'):
        raise ValueError('详情页缺少标题，可能是访问限制页面')
    for tag in soup(['script', 'style', 'nav', 'footer']):
        tag.decompose()
    body = soup.find('main') or soup.find(id='content') or soup.body or soup
    text = body.get_text('\n', strip=True)
    if not text:
        raise ValueError('职业网页正文为空')
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'source_details.html').write_bytes(response.content)
    (folder / 'source_details.txt').write_text(text, encoding='utf-8', newline='')
    write_json(folder / 'source_metadata.json', {
        'url': url, 'retrieved_utc': c.now(), 'status_code': response.status_code,
        'sha256_html': digest(folder / 'source_details.html'),
        'sha256_text': digest(folder / 'source_details.txt'),
        'source': 'O*NET OnLine', 'researcher_reviewed': False,
        'scope': 'initial_details_response_only', 'followed_links': [],
    })
    print('下载成功：', info['onet_name'], flush=True)
    return {'status': 'downloaded', 'url': url}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    select = parser.add_mutually_exclusive_group(required=True)
    select.add_argument('--occupation')
    select.add_argument('--all', action='store_true')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--delay', type=float, default=0.5)
    parser.add_argument('--run-id', help='YYYYMMDD_累计编号；省略时按本地日期分配新批次')
    args = parser.parse_args(argv)
    if args.delay < 0:
        parser.error('--delay must be nonnegative')
    from shared.batch import validate_run_id
    if args.run_id:validate_run_id(args.run_id)
    manifest = {'started_utc': c.now(), 'scope': 'initial_details_response_only',
                'registry_sha256': digest(c.occupations_file()),
                'script_sha256': digest(__file__), 'occupations': []}
    from datetime import datetime,timezone,timedelta
    import re
    parent=c.ROOT/'material_preparation/results/onet_download'
    if args.run_id and re.fullmatch(r'\d{8}_\d{3,}',args.run_id):name=args.run_id
    else:
        date=datetime.now(timezone(timedelta(hours=9))).strftime('%Y%m%d')
        numbers=[int(p.name.rsplit('_',1)[1]) for p in parent.glob('*') if p.is_dir() and re.fullmatch(r'\d{8}_\d{3,}',p.name)]
        name=f'{date}_{max(numbers,default=0)+1:03}'
    destination=parent/name/'批次信息.json'
    if args.execute and destination.exists():raise ValueError('下载批次已存在，请使用新批次号')
    manifest.update(format_version=3,run_id=name,task='onet-download')
    for index, (slug, info) in enumerate(select_occupations(read_registry(), args.occupation, args.all)):
        if args.execute and index:
            time.sleep(args.delay)
        try:
            result = fetch_onet(argparse.Namespace(occupation=slug, execute=args.execute), {slug: info})
        except Exception as exc:
            result = {'status': 'error', 'error': str(exc)}
            print('下载失败：', info['onet_name'], str(exc), flush=True)
        manifest['occupations'].append({'occupation': slug, 'onet_code': info['onet_code'], **result})
        if args.execute:
            write_json(destination, manifest)
    manifest['completed_utc'] = c.now()
    if args.execute:
        write_json(destination, manifest)
        from shared.material_results import refresh
        refresh(destination.parent)
    errors = sum(x['status'] == 'error' for x in manifest['occupations'])
    print(f"职业={len(manifest['occupations'])} 失败={errors}")
    return 1 if errors else 0
