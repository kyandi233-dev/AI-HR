"""Export the morality master and configured independent reviewers; preserve keyed human inputs."""
if __name__ == '__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import date, datetime
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from shared import common as c
from shared.storage import input_files, request_for
from material_preparation.morality_inputs import validate_generated
from material_preparation.run_morality_generation import preview
from material_preparation.run_material_generation import immutable_bytes
from material_preparation.export_individual_reviews import finish_workbook
from material_preparation.reviewer_config import load_team, reviewer_file

FIRST_ROW = 6
REVIEW_HEADERS = ['材料编号','道德主题','生成状态','配对正文','可理解性','自然性','负面效价','中性效价',
                  '主要主题','配对合理性','明显专业证据','审核结论','问题说明','审核日期','材料版本']
REVIEW_MANUAL = REVIEW_HEADERS[4:14]
MASTER_MANUAL = ['最终是否纳入','决策备注']


def review_root():
    return c.ROOT / 'material_preparation/review/mority'


def read_saved(path, manual):
    result = {}
    if not path.exists():
        return result
    book = load_workbook(path, data_only=False)
    try:
        sheet = book.worksheets[0]
        headers = [cell.value for cell in sheet[5]]
        for cells in sheet.iter_rows(min_row=FIRST_ROW):
            if any(cell.comment for cell in cells):
                raise ValueError('审核文件有批注，停止覆盖：' + str(path))
            row = dict(zip(headers, [cell.value for cell in cells]))
            if not row.get('材料编号'):
                continue
            values = {key: row.get(key) for key in manual}
            version = row.get('材料版本')
            key = (row['材料编号'], version)
            if key in result:
                raise ValueError('审核文件材料编号与版本重复')
            if version is None and any(value is not None for value in values.values()):
                raise ValueError('旧审核记录没有版本，停止覆盖')
            result[key] = values
        if len(book.worksheets) > (3 if manual == MASTER_MANUAL else 2):
            raise ValueError('审核文件有额外工作表，停止覆盖')
    finally:
        book.close()
    return result


def preserve(current, previous):
    identities = {(row['材料编号'], row['材料版本']) for row in current}
    for key, values in previous.items():
        if key not in identities and any(value is not None for value in values.values()):
            raise ValueError('已审核材料被移除或换版，停止覆盖：' + str(key[0]))
    return [{**row, **previous.get((row['材料编号'], row['材料版本']), {})} for row in current]


def validate_review(row):
    if row['生成状态'] != '已生成' and any(row.get(key) is not None for key in REVIEW_MANUAL):
        raise ValueError('尚无正文的任务不能填写材料评分或结论：' + row['材料编号'])
    for key in ['可理解性','自然性','负面效价','中性效价','配对合理性']:
        value = row.get(key)
        if value is not None and (type(value) is not int or not 1 <= value <= 7):
            raise ValueError(key + '须为1–7整数')
    if row.get('审核结论') not in (None, '可用', '需修改', '不采用'):
        raise ValueError('审核结论无效')
    if row.get('明显专业证据') not in (None, '未见明显证据', '有', '待结合岗位'):
        raise ValueError('明显专业证据选项无效')
    if row.get('主要主题') not in (None, *[c.FOUNDATION_CN[f] for f in c.FOUNDATIONS], '无明显道德主题', '多主题难区分'):
        raise ValueError('主要主题选项无效')


def material_rows(tasks, settings, root, run_id):
    latest = {}
    for inp in input_files(root):
        record = c.load_json(inp)
        key = record['task_id']
        if key not in latest or record['attempt'] > latest[key][0]['attempt']:
            latest[key] = (record, inp)
    rows = []
    content_seen = {}
    for task in tasks:
        pid = task['task_id']
        spec = task['metadata']['spec']
        req_sha = c.sha256(c.canonical(request_for(task, settings)))
        state, parsed, body, generated_sha = '待生成', None, None, None
        output = None
        if pid in latest:
            record, inp = latest[pid]
            if c.sha256(c.canonical(record['request'])) != req_sha:
                raise ValueError('已有请求与本次协议不一致：' + pid)
            out = inp.with_name(inp.name.replace('.input.json', '.output.json'))
            output = c.load_json(out) if out.exists() else {}
            if output.get('status') == 'ok':
                parsed = output['parsed']
                validate_generated(parsed, task)
                raw = output.get('raw_response') or {}
                if json.loads(output['answer']) != parsed or raw['choices'][0]['message']['content'] != output['answer']:
                    raise ValueError('解析结果与原始响应不一致：' + pid)
                if parsed['status'] == 'not_adaptable':
                    state = '不适配'
                    generated_sha = c.sha256(output['answer'])
                else:
                    draft = c.ROOT / 'material_preparation/drafts/morality' / (pid + '.json')
                    if c.load_json(draft) != parsed:
                        raise ValueError('草稿与成功响应不一致：' + pid)
                    generated_sha = c.sha256(draft.read_bytes())
                    body = review_root() / 'materials' / run_id / (pid + '.md')
                    display = (f'# {pid}\n\n## 负面版本\n\n{parsed["negative"]}\n\n'
                               f'## 中性版本\n\n{parsed["neutral"]}\n')
                    immutable_bytes(body, display.encode('utf-8'))
                    state = '已生成'
            else:
                state = '生成失败' if output.get('status') == 'error' else '调用未完成'
        version = c.sha256(c.canonical({'request': req_sha, 'generated': generated_sha}))
        notes = []
        if parsed:
            notes.extend(parsed.get('review_flags', []))
            if parsed['status'] == 'not_adaptable':
                notes.append(parsed['rejection_reason'])
            else:
                signature = c.sha256(re.sub(r'\s+', '', parsed['negative'] + '\n' + parsed['neutral']))
                if signature in content_seen:
                    notes.append('正文与' + content_seen[signature] + '完全重复，需人工处理')
                else:
                    content_seen[signature] = pid
        if (output or {}).get('error_message'):
            notes.append(output['error_message'])
        rows.append({'材料编号': pid, '道德主题': c.FOUNDATION_CN[spec['foundation']],
                     '来源方式': 'MFV改编' if spec['source'] else '规则新编',
                     'MFV编号': spec['source']['library_item_number'] if spec['source'] else None,
                     '原条目推荐': ('是' if spec['source']['recommended'] else '否') if spec['source'] else '不适用',
                     '生成状态': state, '生成备注': '；'.join(notes) or None, '材料版本': version,
                     '_body': str(body) if body else None, '_prompt': str(root / (pid + '.prompt.txt')),
                     '_parsed': parsed, '_error': (output or {}).get('error_message'),
                     '_request_sha256': req_sha})
    return rows


def serial(value):
    return {'date': value.isoformat()} if isinstance(value, (date, datetime)) else value


def sheet_spec(rows, headers, target):
    values, links = [], []
    for number, row in enumerate(rows, FIRST_ROW):
        output = {**row}
        for name, key in [('配对正文', '_body'), ('完整提示词', '_prompt')]:
            if name in headers:
                path = row.get(key)
                output[name] = '打开正文' if name == '配对正文' and path else ('打开提示词' if path else None)
                if path:
                    if not Path(path).is_file():
                        raise ValueError('链接目标不存在：' + path)
                    links.append({'cell': get_column_letter(headers.index(name) + 1) + str(number), 'target': path})
        values.append([serial(output.get(name)) for name in headers])
    return {'headers': headers, 'rows': values, 'links': links, 'review': str(target)}


def make_payload(config, protocol, catalog, tasks, settings, root, run_id):
    team = load_team(config)
    people = team['reviewers']
    current = material_rows(tasks, settings, root, run_id)
    specs, reviews = [], {}
    before = {}
    for person in people:
        target = reviewer_file(team, 'mority', person, review_root())
        before[str(target)] = c.sha256(target.read_bytes()) if target.exists() else None
        rows = preserve(current, read_saved(target, REVIEW_MANUAL))
        for row in rows:
            validate_review(row)
        reviews[person] = {row['材料编号']: row for row in rows}
        specs.append({**sheet_spec(rows, REVIEW_HEADERS, target), 'kind': 'reviewer', 'title': person + ' · 道德材料审核', 'manual': REVIEW_MANUAL})
    master = review_root() / '道德材料汇总.xlsx'
    before[str(master)] = c.sha256(master.read_bytes()) if master.exists() else None
    headers = ['材料编号','道德主题','来源方式','MFV编号','原条目推荐','生成状态','配对正文','完整提示词','生成备注',
               *people, '最终是否纳入','决策备注','材料版本']
    master_rows = preserve(current, read_saved(master, MASTER_MANUAL))
    for row in master_rows:
        for person in people:
            row[person] = reviews[person][row['材料编号']].get('审核结论')
        if row['生成状态'] != '已生成' and any(row.get(k) is not None for k in MASTER_MANUAL):
            raise ValueError('未生成材料不能作最终纳入决定')
        if row.get('最终是否纳入') not in (None, '纳入', '修改后复审', '不纳入'):
            raise ValueError('最终纳入选项无效')
    specs.insert(0, {**sheet_spec(master_rows, headers, master), 'kind': 'master', 'title': '道德材料汇总', 'manual': MASTER_MANUAL})
    return {'specs': specs, 'protocol': protocol, 'catalog': catalog,
            'run_id': run_id, 'config': config, 'reviewers': people}, before


def validate_workbook(path, spec):
    book = load_workbook(path, data_only=False)
    try:
        expected_sheets = ['材料汇总', 'MFV原条目', '定义与标准'] if spec['kind'] == 'master' else ['材料审核', '定义与标准']
        if book.sheetnames != expected_sheets:
            raise ValueError('工作表结构不符')
        sheet = book.worksheets[0]
        if [cell.value for cell in sheet[5]] != spec['headers']:
            raise ValueError('审核表列定义错误')
        version_col = get_column_letter(spec['headers'].index('材料版本') + 1)
        if not sheet.column_dimensions[version_col].hidden:
            raise ValueError('技术版本列应隐藏，避免干扰审核')
        for number, values in enumerate(spec['rows'], FIRST_ROW):
            for col, expected in enumerate(values, 1):
                actual = sheet.cell(number, col).value
                if isinstance(expected, dict) and 'date' in expected:
                    if not isinstance(actual, (date, datetime)) or actual.isoformat()[:10] != expected['date'][:10]:
                        raise ValueError('日期没有保留')
                elif actual != expected:
                    raise ValueError(f'单元格值不符：{number},{col}')
        for link in spec['links']:
            actual = sheet[link['cell']].hyperlink
            if not actual or (Path(spec['review']).parent / actual.target).resolve() != Path(link['target']).resolve():
                raise ValueError('审核文件链接错误')
    finally:
        book.close()


def run(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path)
    p.add_argument('--run-id')
    base = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node'
    p.add_argument('--node', type=Path, default=os.environ.get('CODEX_PRIMARY_RUNTIME_NODE', base / 'bin/node.exe'))
    p.add_argument('--node-modules', type=Path, default=os.environ.get('CODEX_PRIMARY_RUNTIME_NODE_MODULES', base / 'node_modules'))
    args = p.parse_args(argv)
    config, protocol, catalog, tasks, settings, root, run_id = preview(args.config, args.run_id)
    payload, before = make_payload(config, protocol, catalog, tasks, settings, root, run_id)
    work = Path(tempfile.mkdtemp(prefix='ai_hr_morality_review_'))
    subprocess.run(['cmd', '/c', 'mklink', '/J', str(work / 'node_modules'), str(args.node_modules.resolve())], check=True, capture_output=True)
    builder = Path(__file__).with_suffix('.mjs')
    shutil.copy2(builder, work / builder.name)
    (work / 'inputs.json').write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    process = subprocess.run([str(args.node), str(work / builder.name), str(work / 'inputs.json'), str(work)], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if process.returncode:
        raise ValueError('Excel生成失败：' + process.stderr[-2200:])
    for index, spec in enumerate(payload['specs']):
        candidate = work / (str(index) + '.xlsx')
        finish_workbook(work / (str(index) + '.authored.xlsx'), candidate, spec)
        validate_workbook(candidate, spec)
    for file, sha in before.items():
        path = Path(file)
        actual = c.sha256(path.read_bytes()) if path.exists() else None
        if actual != sha:
            raise ValueError('导出期间人工审核文件已变化，停止覆盖：' + file)
    review_root().mkdir(parents=True, exist_ok=True)
    for index, spec in enumerate(payload['specs']):
        target = Path(spec['review'])
        pending_file = target.with_name('.' + target.stem + '.pending.xlsx')
        shutil.copyfile(work / (str(index) + '.xlsx'), pending_file)
        pending_file.replace(target)
    manifest = {'run_id': run_id, 'exported_utc': c.now(), 'planned_pairs': len(tasks),
                'reviewers': payload['reviewers'],
                'generated_pairs': sum(row[5] == '已生成' for row in payload['specs'][0]['rows']),
                'preview_directory': str(work), 'protocol_sha256': tasks[0]['metadata']['protocol_sha256'],
                'catalog_sha256': tasks[0]['metadata']['catalog_sha256'], 'prompt_sha256': tasks[0]['metadata']['prompt_sha256'],
                'files': [{'path': s['review'], 'sha256': c.sha256(Path(s['review']).read_bytes())} for s in payload['specs']]}
    (review_root().parent / 'morality_review_manifest.json').write_text(c.canonical(manifest) + '\n', encoding='utf-8')
    print('已生成1份总表和',len(payload['reviewers']),'份独立审核表；待生成任务不计为已有正文。预览：', work)
    return 0


if __name__ == '__main__':
    import sys
    try:
        sys.exit(run())
    except Exception as error:
        print(c.safe_error_message(error), file=sys.stderr)
        sys.exit(2)
