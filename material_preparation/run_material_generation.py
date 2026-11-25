"""Preview every exact request; execute selected occupations through the shared runner."""
if __name__=='__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from openpyxl import load_workbook
from shared import common as c
from shared.storage import path_for, request_for, write_json, input_files
from shared.batch import validate_run_id
from shared import material_results as mr
from material_preparation.review_schema import approval_value,is_approved


def review_rows(path):
    book=load_workbook(path,read_only=True,data_only=False)
    try:
        rows=book['职业汇总'].iter_rows(values_only=True)
        headers=list(next(rows))
        for key in ('O*NET Code','是否选用','JD'):
            if key not in headers: raise ValueError('审核表缺少字段：'+key)
        result={}
        for row in rows:
            item=dict(zip(headers,row)); code=item.get('O*NET Code')
            if code:
                if code in result: raise ValueError('审核表职业编码重复：'+str(code))
                result[code]=item
        return result
    finally:
        book.close()


def is_selected(value):
    return str(value).strip() in ('1','1.0','选用','是','True')


def immutable_bytes(path,content):
    if path.exists():
        if path.read_bytes()!=content: raise ValueError('已有不同内容，不覆盖：'+str(path))
        return
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as f: f.write(content)


def immutable_json(path,value):
    immutable_bytes(path,(c.canonical(value)+'\n').encode('utf-8'))


def successful_record(task,run_id):
    base=path_for(task,run_id)
    for inp in reversed(mr.inputs(base,task['task_id'],task['task'])):
        out=mr.output_path(inp)
        if out.exists():
            result=c.load_json(out)
            if result.get('status')=='ok': return inp,out,result
    raise ValueError('没有成功生成记录：'+str(base))


def run(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task',choices=['jd','resume'],required=True)
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--count',type=int,default=2)
    parser.add_argument('--levels',nargs='+',choices=['medium','low'])
    parser.add_argument('--jd-run-id',help='用户明确指定的JD生成批次；不代替材料批准')
    parser.add_argument('--concurrency',type=int,default=1)
    parser.add_argument('--api-timeout',type=int,help='本次传输等待秒数；不改变提示词和模型参数')
    parser.add_argument('--stream',action='store_true',help='流式接收；完整保留返回片段和拼接原文')
    parser.add_argument('--review',type=Path,default=c.ROOT/'material_preparation/review/职业与材料审核.xlsx')
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--retry-failed',action='store_true')
    args=parser.parse_args(argv)
    validate_run_id(args.run_id)
    if args.count<1: raise ValueError('简历数量必须为正整数')
    if args.concurrency<1: raise ValueError('并发数必须为正整数')
    if args.task!='resume' and (args.levels or args.jd_run_id):
        raise ValueError('水平和JD来源批次只适用于简历生成')
    if args.jd_run_id: validate_run_id(args.jd_run_id)
    registry=c.load_json(c.occupations_file())
    rows=review_rows(args.review)
    selected=[slug for slug,info in registry.items() if is_selected(rows.get(info['onet_code'],{}).get('是否选用'))]
    selected.sort(key=lambda slug:registry[slug]['onet_code'])
    if not selected: raise ValueError('审核表中没有选用职业')
    if args.task=='resume' and not args.jd_run_id:
        for slug in selected:
            if not is_approved(approval_value(rows[registry[slug]['onet_code']],'JD')):
                raise ValueError('JD 尚未审核通过：'+slug)
            receipt=c.job_files(slug)['jd'].parent/'jd_approval.json'
            record=c.load_json(receipt)
            if c.sha256(c.job_files(slug)['jd'].read_bytes())!=record['approved_sha256']:
                raise ValueError('批准 JD 已变化：'+slug)
    from shared.tasks import make_tasks
    settings=c.load_settings(args.task)
    settings['_stream']=args.stream
    if args.api_timeout is not None:
        if args.api_timeout<1: raise ValueError('等待秒数必须为正整数')
        settings['api_timeout_seconds']=args.api_timeout
    tasks=[]
    for slug in selected:
        task_args=SimpleNamespace(occupation=slug,count=args.count,start_index=1,
                                  levels=args.levels,jd_run_id=args.jd_run_id)
        tasks.extend(make_tasks(args.task,task_args,registry,settings))
    from shared.api import request_kwargs
    for task in tasks: request_kwargs(settings,task)
    # Previewing a revised prompt must not require moving or overwriting old drafts.
    for task in tasks:
        paths=c.job_files(task['metadata']['occupation'])
        draft=paths['jd_draft'] if args.task=='jd' else paths['drafts']/(task['metadata']['resume_id']+'.txt')
        if args.execute and draft.exists():
            _,_,result=successful_record(task,args.run_id)
            if draft.read_bytes().decode('utf-8')!=result['answer']:
                raise ValueError('草稿与原始响应不同，停止：'+str(draft))
    plan={'task':args.task,'run_id':args.run_id,'stage':'pilot','occupations':selected,'count':args.count}
    if args.task=='resume': plan.update(levels=args.levels or ['medium'],jd_run_id=args.jd_run_id)
    root=mr.prepare(tasks,settings,SimpleNamespace(**plan,concurrency=args.concurrency),plan)
    print('已保存完整输入预览：',len(tasks),'份；职业：',', '.join(selected))
    if not args.execute:
        print('未调用模型。执行同一命令并添加 --execute 才开始生成。')
        return 0
    from shared.storage import pending,record_task
    from shared.batch import freeze
    from shared.exports import export_results
    execution=SimpleNamespace(**plan,concurrency=args.concurrency,retry_failed=args.retry_failed)
    todo=[task for task in tasks if pending(task,settings,execution)]
    if todo and not c.load_api_key(): raise ValueError('未找到 API 密钥')
    if todo:
        from openai import OpenAI
    freeze(tasks,settings,execution)
    def execute_numbered(pair):
        sequence,task=pair
        trial=SimpleNamespace(**vars(execution),sequence=sequence)
        return record_task(task,settings,trial)
    if args.concurrency==1:
        statuses=[execute_numbered(pair) for pair in enumerate(tasks,1)]
    else:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            statuses=list(pool.map(execute_numbered,enumerate(tasks,1)))
    export_results(args.task)
    status=1 if 'error' in statuses else 0
    generated=[]
    for task in tasks:
        try:
            inp,out,result=successful_record(task,args.run_id)
        except ValueError:
            continue
        if not mr.request_equivalent(c.load_json(inp)['request'],request_for(task,settings)):
            raise ValueError('请求记录与预览不一致')
        paths=c.job_files(task['metadata']['occupation'])
        draft=paths['jd_draft'] if args.task=='jd' else paths['drafts']/(task['metadata']['resume_id']+'.txt')
        if draft.read_bytes().decode('utf-8')!=result['answer']:
            raise ValueError('草稿不是原始响应原文')
        flags=[]
        if args.task=='jd':
            from material_preparation.generation_inputs import extract_jd,review_flags
            flags=review_flags(extract_jd(result['answer']))
        generated.append({'occupation':task['metadata']['occupation'],'task_id':task['task_id'],
                          'draft':draft.relative_to(c.ROOT).as_posix(),'draft_sha256':c.sha256(draft.read_bytes()),
                          'input':inp.relative_to(c.ROOT).as_posix(),'output':out.relative_to(c.ROOT).as_posix(),
                          **{k:task['metadata'][k] for k in ('ability_level','level_replica','jd_run_id') if k in task['metadata']},
                          'review_flags':flags})
    mr.save_manifest(args.task,args.run_id,{'task':args.task,'run_id':args.run_id,'materials':generated})
    print('原文及调用记录核验通过：',len(generated),'份；记录：',root.relative_to(c.ROOT))
    return status


if __name__=='__main__':
    import sys
    try: sys.exit(run())
    except Exception as error:
        print('失败：'+c.safe_error_message(error),file=sys.stderr); sys.exit(2)
