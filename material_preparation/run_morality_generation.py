"""Preview all source-grounded requests; call the configured model only with --execute."""
if __name__ == '__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from shared import common as c
from shared.api import request_kwargs
from shared.batch import freeze, validate_run_id
from shared import material_results as mr
from shared.storage import path_for, request_for, pending, record_task
from material_preparation.morality_inputs import build_tasks
from material_preparation.run_material_generation import immutable_bytes, immutable_json


def preview(config_path=None, run_id=None):
    config, protocol, catalog, tasks = build_tasks(config_path)
    run_id = run_id or config['run_id']
    validate_run_id(run_id)
    settings = c.load_settings('moral-generate')
    plan = {'task': 'moral-generate', 'run_id': run_id, 'stage': 'pilot', 'occupations': [],
            'protocol_version': protocol['protocol_version'],
            'config': {k: v for k, v in config.items() if k not in ('reviewers', 'review_files', 'review_config')},
            'requests': [{'pair_id': t['task_id'], 'source_id': t['metadata']['spec']['source_id'],
                          'request_sha256': c.sha256(c.canonical(request_for(t, settings)))} for t in tasks]}
    # Validate every request and any previous immutable plan before writing files.
    for task in tasks:
        request_kwargs(settings, task)
    root=mr.prepare(tasks,settings,SimpleNamespace(run_id=run_id,stage='pilot',concurrency=1),plan)
    return config, protocol, catalog, tasks, settings, root, run_id


def run(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path)
    p.add_argument('--run-id')
    p.add_argument('--foundation', choices=c.FOUNDATIONS)
    p.add_argument('--source-id', help='例如mfv_003；仅限制本次执行，不改变冻结的总任务池')
    p.add_argument('--limit', type=int)
    p.add_argument('--concurrency', type=int, default=1)
    p.add_argument('--api-timeout', type=int, help='本次传输等待秒数；不改变提示词和模型参数')
    p.add_argument('--stream', action='store_true', help='流式接收；完整保留返回片段和拼接原文')
    p.add_argument('--execute', action='store_true')
    p.add_argument('--retry-failed', action='store_true')
    args = p.parse_args(argv)
    if args.concurrency < 1 or (args.limit is not None and args.limit < 1):
        raise ValueError('并发数与limit必须为正整数')
    if args.api_timeout is not None and args.api_timeout < 1:
        raise ValueError('等待秒数必须为正整数')
    config, protocol, catalog, tasks, settings, root, run_id = preview(args.config, args.run_id)
    settings['_stream'] = args.stream
    if args.api_timeout is not None:
        settings['api_timeout_seconds'] = args.api_timeout
    execution = SimpleNamespace(task='moral-generate', run_id=run_id, stage='pilot', occupations=[],
                                concurrency=args.concurrency, retry_failed=args.retry_failed)
    matching = [t for t in tasks if (not args.foundation or t['metadata']['foundation'] == args.foundation)
                and (not args.source_id or t['metadata']['spec']['source_id'] == args.source_id)]
    if not matching:
        raise ValueError('未匹配任何任务，请检查主题或来源编号')
    todo = [t for t in matching if pending(t, settings, execution)]
    if args.limit:
        todo = todo[:args.limit]
    print(f'任务池={len(tasks)}；匹配={len(matching)}；本次待生成={len(todo)}；模型={settings["profiles"]["generation"]["model"]}')
    print('完整提示词与请求预览：', root)
    if not args.execute:
        print('仅预览：未调用模型、未产生正文。')
        return 0
    if todo and not c.load_api_key():
        raise ValueError('未找到API密钥')
    for task in todo:
        draft = c.ROOT / 'material_preparation/drafts/morality' / (task['task_id'] + '.json')
        if draft.exists():
            raise ValueError('待生成编号已有草稿，先归档或调整编号，避免调用后冲突：' + task['task_id'])
    freeze(tasks, settings, execution)
    sequence = {t['task_id']: n for n, t in enumerate(tasks, 1)}
    def execute(task):
        trial = SimpleNamespace(**vars(execution), sequence=sequence[task['task_id']])
        return record_task(task, settings, trial)
    if args.concurrency == 1:
        statuses = [execute(t) for t in todo]
    else:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            statuses = list(pool.map(execute, todo))
    mr.refresh(root)
    print(f'成功={statuses.count("ok")}；失败={statuses.count("error")}；请刷新道德审核表。')
    return 1 if 'error' in statuses else 0


if __name__ == '__main__':
    import sys
    try:
        sys.exit(run())
    except Exception as error:
        print(c.safe_error_message(error), file=sys.stderr)
        sys.exit(2)
