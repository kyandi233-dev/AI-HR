"""Command line and batch plans; preview by default."""
import argparse
import copy
from concurrent.futures import ThreadPoolExecutor
from . import common as c
from .api import request_kwargs
from .batch import freeze, validate_run_id
from .tasks import make_tasks, JOB_TASKS
from .storage import pending, record_task
from .exports import export_results
from .migration import migrate_results
from material_preparation.fetch_occupations import fetch_onet
from .materials import verified_snapshot


def status(occupations):
    for slug,info in occupations.items():
        paths=c.job_files(slug); folder=paths['source']
        raw=all((folder/n).is_file() for n in ['source_details.html','source_details.txt','source_metadata.json'])
        print(f"{slug} ({info['onet_code']}) 原始抓取={'有' if raw else '无'} "
              f"审核资料={'有' if paths['profile'].exists() else '无'} "
              f"批准JD={'有' if paths['jd'].exists() else '无'} "
              f"批准简历={len(list(paths['resumes'].glob('R*.txt')))}")
    print('以上为职业材料准备状态；原则实验使用自身的定义与问题。')


def read_plan(args):
    data=c.load_json(args.batch) if args.batch else {}
    allowed={'task','run_id','stage','repeat','count','start_index','source','foundation','occupations','profile_overrides','materials_version','concurrency'}
    if set(data)-allowed: raise ValueError('批次计划包含未知字段：'+str(set(data)-allowed))
    defaults={'task':None,'run_id':'pilot01','stage':'pilot','repeat':1,'count':2,
              'start_index':1,'source':'drafts','foundation':None,'materials_version':None}
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


def main(argv=None,allowed_tasks=None):
    parser=argparse.ArgumentParser(description='实验任务包：默认预览；--execute 才调用 API')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('status')
    fetch=sub.add_parser('fetch-onet'); fetch.add_argument('--occupation',required=True); fetch.add_argument('--execute',action='store_true')
    exp=sub.add_parser('export'); exp.add_argument('--task',choices=list(c.TASK_TO_PROFILE))
    sub.add_parser('migrate-results')
    run=sub.add_parser('run')
    run.add_argument('--batch',type=c.Path,help='批次计划 JSON 文件')
    run.add_argument('--task',choices=allowed_tasks or list(c.TASK_TO_PROFILE))
    select=run.add_mutually_exclusive_group()
    select.add_argument('--occupation'); select.add_argument('--occupations',nargs='+')
    run.add_argument('--foundation',choices=c.FOUNDATIONS)
    run.add_argument('--source',choices=['drafts','approved'])
    for name in ['count','start-index','repeat']: run.add_argument('--'+name,type=int)
    run.add_argument('--run-id'); run.add_argument('--stage',choices=['pilot','main','development'])
    run.add_argument('--materials-version',help='实验2或3的本地固定材料版本，位于该实验 materials/<版本>/')
    run.add_argument('--concurrency',type=int,help='同时执行的请求数，默认读取 settings.json 的 concurrency')
    run.add_argument('--limit',type=int,help='可选：本次最多新发送多少次请求；默认运行全部未完成项')
    run.add_argument('--execute',action='store_true'); run.add_argument('--retry-failed',action='store_true')
    args=parser.parse_args(argv)
    if args.command=='export': export_results(args.task); return 0
    if args.command=='migrate-results': migrate_results(); return 0
    if args.command in ('status','fetch-onet'):
        occupations=c.load_json(c.occupations_file())
        if args.command=='status': status(occupations)
        else: fetch_onet(args,occupations)
        return 0
    plan=read_plan(args)
    if allowed_tasks and args.task not in allowed_tasks:
        raise ValueError('此入口仅支持任务：'+', '.join(allowed_tasks))
    settings=copy.deepcopy(c.load_settings(args.task))
    if args.concurrency is None: args.concurrency=plan.get('concurrency',settings.get('concurrency',1))
    if type(args.concurrency) is not int or args.concurrency<1: raise ValueError('concurrency必须是正整数')
    profile=settings['profiles'][c.TASK_TO_PROFILE[args.task]]
    overrides=plan.get('profile_overrides',{})
    if not isinstance(overrides,dict) or set(overrides)-{'model','temperature','thinking','max_tokens'}:
        raise ValueError('profile_overrides 只能覆盖 model/temperature/thinking/max_tokens')
    profile.update(overrides)
    occupations=c.load_json(c.occupations_file()) if args.task in JOB_TASKS else {}
    if args.task in ('moral-check','moral-relevance','baseline','abc'):
        root,identity=verified_snapshot(args.task,args.materials_version)
        settings['_materials_root']=root
        settings['_materials_snapshot']=identity
    elif args.materials_version:
        raise ValueError('本任务不使用实验材料快照')
    tasks=[]
    for slug in args.occupations or [None]:
        task_args=copy.copy(args); task_args.occupation=slug
        tasks.extend(make_tasks(args.task,task_args,occupations,settings))
    if settings.get('_materials_snapshot'):
        for task in tasks:
            task['metadata'].update(materials_version=args.materials_version,
                                    materials_sha256=settings['_materials_snapshot']['sha256'])
    if not tasks: raise ValueError('本批没有可运行任务')
    request_kwargs(settings,tasks[0])  # Validate parameters even in preview.
    todo=[t for t in tasks if pending(t,settings,args)]
    selected=todo[:args.limit] if args.limit is not None else todo
    print(f"任务={args.task} 阶段={args.stage} 计划={len(tasks)} 待运行={len(todo)} 本次={len(selected)} "
          f"模型={profile['model']} thinking={profile['thinking']} 温度={profile.get('temperature')} "
          f"max_tokens={profile['max_tokens']} 并发={args.concurrency} 批次={args.run_id}")
    if not args.execute:
        print('预览：以下为执行计划和完整提示词。添加 --execute 开始采集。')
        for t in selected: print(t['metadata'].get('occupation',''),t['task_id'])
        if selected: print('\n第一条完整 user 消息：\n'+selected[0]['messages'][0]['content'])
        return 0
    if selected:
        if not c.load_api_key(): raise ValueError('请在项目根目录 .env 中填写 DEEPSEEK_API_KEY，或在当前终端设置同名环境变量')
        from openai import OpenAI  # Check dependencies before freezing or writing trial records.
    freeze(tasks,settings,args)
    statuses=[]
    sequence={(t['metadata'].get('occupation'),t['task_id']):i for i,t in enumerate(tasks,1)}
    def execute_task(task):
        trial_args=copy.copy(args)
        trial_args.sequence=sequence[(task['metadata'].get('occupation'),task['task_id'])]
        return record_task(task,settings,trial_args)
    if args.concurrency==1:
        statuses=[execute_task(task) for task in selected]
    elif selected:
        executor=ThreadPoolExecutor(max_workers=min(args.concurrency,len(selected)))
        try:
            statuses=list(executor.map(execute_task,selected))
        finally:
            executor.shutdown(wait=True,cancel_futures=True)
    export_results(args.task)
    errors=statuses.count('error')
    print(f"执行结束：成功={statuses.count('ok')}，失败={errors}，跳过={statuses.count('skip')}")
    return 1 if errors else 0


def task_main(task,allowed_tasks=None,default_batch=None):
    """Small direct entry for one research step; defaults to preview."""
    import sys
    argv=sys.argv[1:]
    def has_option(name):
        return any(arg==name or arg.startswith(name+'=') for arg in argv)
    if default_batch and not has_option('--batch'):
        argv=['--batch',str(c.task_folder(task)/'config'/default_batch),*argv]
    if not has_option('--batch') and not has_option('--task'):
        argv=['--task',task,*argv]
    try:
        return main(['run',*argv],allowed_tasks=allowed_tasks or [task])
    except Exception as exc:
        print('失败：'+c.safe_error_message(exc),file=sys.stderr)
        return 2


if __name__=='__main__':
    import sys
    try:
        sys.exit(main())
    except Exception as exc:
        print('失败：'+c.safe_error_message(exc),file=sys.stderr)
        sys.exit(2)
