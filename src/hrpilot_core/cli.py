"""Command line and batch plans; preview by default."""
import argparse
import copy
import os
import time
from . import common as c
from .api import request_kwargs
from .batch import freeze, validate_run_id
from .tasks import make_tasks, JOB_TASKS
from .storage import pending, record_task
from .exports import export_results
from .migration import migrate_results
from .onet import fetch_onet


def status(occupations):
    for slug,info in occupations.items():
        paths=c.job_files(slug); folder=paths['profile'].parent
        raw=all((folder/n).is_file() for n in ['source_details.html','source_details.txt','source_metadata.json'])
        print(f"{slug} ({info['onet_code']}) 原始抓取={'有' if raw else '无'} "
              f"审核资料={'有' if paths['profile'].exists() else '无'} "
              f"批准JD={'有' if paths['jd'].exists() else '无'} "
              f"批准简历={len(list(paths['resumes'].glob('R*.txt')))}")
    print('登记职业不是已完成抓取；原则实验不需要职业材料。')


def read_plan(args):
    data=c.load_json(args.batch) if args.batch else {}
    allowed={'task','run_id','stage','repeat','count','start_index','source','foundation','occupations','profile_overrides'}
    if set(data)-allowed: raise ValueError('批次计划包含未知字段：'+str(set(data)-allowed))
    defaults={'task':None,'run_id':'pilot01','stage':'pilot','repeat':1,'count':2,
              'start_index':1,'source':'drafts','foundation':None}
    for name,default in defaults.items():
        if getattr(args,name,None) is None: setattr(args,name,data.get(name,default))
    if args.task not in c.TASK_TO_PROFILE: raise ValueError('请指定有效的 --task 或批次计划中的 task')
    if args.stage not in ('pilot','main','development'): raise ValueError('stage 仅允许 pilot/main/development')
    if args.occupations is None:
        args.occupations=[args.occupation] if args.occupation else data.get('occupations',[])
    if not isinstance(args.occupations,list) or any(not isinstance(x,str) for x in args.occupations):
        raise ValueError('occupations 必须为职业ID列表')
    if len(set(args.occupations))!=len(args.occupations): raise ValueError('职业列表重复')
    if args.task in JOB_TASKS and not args.occupations: raise ValueError('本任务需要选择职业')
    if args.task not in JOB_TASKS and args.occupations: raise ValueError('本任务不接收职业列表')
    for name in ['count','start_index','repeat']:
        value=getattr(args,name)
        if type(value) is not int or value<1: raise ValueError(name+' 必须是正整数')
    if args.limit is not None and args.limit<1: raise ValueError('limit 必须是正整数')
    validate_run_id(args.run_id)
    return data


def main(argv=None):
    parser=argparse.ArgumentParser(description='实验任务包：默认预览；--execute 才调用 API')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('status')
    fetch=sub.add_parser('fetch-onet'); fetch.add_argument('--occupation',required=True); fetch.add_argument('--execute',action='store_true')
    exp=sub.add_parser('export'); exp.add_argument('--task',choices=list(c.TASK_TO_PROFILE))
    sub.add_parser('migrate-results')
    run=sub.add_parser('run')
    run.add_argument('--batch',type=c.Path,help='批次计划 JSON 文件')
    run.add_argument('--task',choices=list(c.TASK_TO_PROFILE))
    select=run.add_mutually_exclusive_group()
    select.add_argument('--occupation'); select.add_argument('--occupations',nargs='+')
    run.add_argument('--foundation',choices=c.FOUNDATIONS)
    run.add_argument('--source',choices=['drafts','approved'])
    for name in ['count','start-index','repeat']: run.add_argument('--'+name,type=int)
    run.add_argument('--run-id'); run.add_argument('--stage',choices=['pilot','main','development'])
    run.add_argument('--limit',type=int,help='可选：本次最多新发送多少次请求；默认运行全部未完成项')
    run.add_argument('--execute',action='store_true'); run.add_argument('--retry-failed',action='store_true')
    args=parser.parse_args(argv)
    if args.command=='export': export_results(args.task); return 0
    if args.command=='migrate-results': migrate_results(); return 0
    if args.command in ('status','fetch-onet'):
        occupations=c.load_json(c.ROOT/'config'/'occupations.json')
        if args.command=='status': status(occupations)
        else: fetch_onet(args,occupations)
        return 0
    plan=read_plan(args)
    settings=copy.deepcopy(c.load_json(c.ROOT/'config'/'settings.json'))
    profile=settings['profiles'][c.TASK_TO_PROFILE[args.task]]
    overrides=plan.get('profile_overrides',{})
    if not isinstance(overrides,dict) or set(overrides)-{'model','temperature','thinking','max_tokens'}:
        raise ValueError('profile_overrides 只能覆盖 model/temperature/thinking/max_tokens')
    profile.update(overrides)
    occupations=c.load_json(c.ROOT/'config'/'occupations.json') if args.task in JOB_TASKS else {}
    tasks=[]
    for slug in args.occupations or [None]:
        task_args=copy.copy(args); task_args.occupation=slug
        tasks.extend(make_tasks(args.task,task_args,occupations,settings))
    if not tasks: raise ValueError('本批没有可运行任务')
    request_kwargs(settings,tasks[0])  # Validate parameters even in preview.
    todo=[t for t in tasks if pending(t,settings,args)]
    selected=todo[:args.limit] if args.limit is not None else todo
    print(f"任务={args.task} 计划={len(tasks)} 待运行={len(todo)} 本次={len(selected)} "
          f"模型={profile['model']} thinking={profile['thinking']} 温度={profile.get('temperature')} 批次={args.run_id}")
    if not args.execute:
        print('DRY RUN：未发送请求、未创建结果文件。每个试次均为独立新对话。')
        for t in selected: print(t['metadata'].get('occupation',''),t['task_id'])
        if selected: print('\n第一条完整 user 消息：\n'+selected[0]['messages'][0]['content'])
        return 0
    # A batch can run all 100 requests in one command. No arbitrary group of 12.
    cap=settings.get('max_requests_per_command')
    if cap is not None and len(selected)>cap:
        raise ValueError(f'本次新请求 {len(selected)} 超过自设上限 {cap}；调整配置或使用可选 --limit')
    if not os.environ.get('DEEPSEEK_API_KEY','').strip(): raise ValueError('未设置 DEEPSEEK_API_KEY')
    freeze(tasks,settings,args)
    errors=0
    sequence={(t['metadata'].get('occupation'),t['task_id']):i for i,t in enumerate(tasks,1)}
    for i,t in enumerate(selected):
        args.sequence=sequence[(t['metadata'].get('occupation'),t['task_id'])]
        if record_task(t,settings,args)=='error': errors+=1
        if i+1<len(selected): time.sleep(settings['request_pause_seconds'])
    export_results(args.task)
    print('本次完成；失败=',errors,'。成功项不会重复发送；重试失败项需显式 --retry-failed。')
    return 1 if errors else 0
