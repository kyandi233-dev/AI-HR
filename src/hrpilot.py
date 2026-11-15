#!/usr/bin/env python3
"""Reproducible DeepSeek HR research scaffold. No API calls without --execute."""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import random
import re
import shutil
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / 'materials' / 'occupations'
MORALS = ROOT / 'materials' / 'morality'
RESULTS = ROOT / 'results'
TASK_TO_PROFILE = {'jd':'generation', 'resume':'generation', 'moral-generate':'generation',
                   'resume-review':'material_review', 'moral-check':'material_review', 'moral-relevance':'material_review',
                   'principles':'evaluation', 'baseline':'evaluation', 'abc':'evaluation'}
FOUNDATIONS = ['care','fairness','loyalty','authority','sanctity','liberty']
FOUNDATION_CN = {'care':'关怀/伤害','fairness':'公平/欺骗','loyalty':'忠诚/背叛',
                 'authority':'权威/颠覆','sanctity':'神圣/纯洁','liberty':'自由/压迫'}


def load_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))

def load_text(path: Path, min_length=1):
    if not path.is_file():
        raise ValueError(f'缺少必要文件：{path.relative_to(ROOT)}')
    s = path.read_text(encoding='utf-8').strip()
    if len(s) < min_length:
        raise ValueError(f'文件内容为空或不足：{path.relative_to(ROOT)}')
    return s

def canonical(obj: Any):
    return json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(',',':'))

def sha256(x: str | bytes):
    return hashlib.sha256(x.encode('utf-8') if isinstance(x,str) else x).hexdigest()

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')

def sdk_version():
    try:
        return importlib.metadata.version('openai')
    except importlib.metadata.PackageNotFoundError:
        return None

def read_prompt(name):
    return load_text(ROOT/'prompts'/name)

def render(name: str, **kwargs):
    """Template uses Python str.format; escaped {{ }} are literal JSON braces."""
    return read_prompt(name).format(**kwargs)

def job_files(slug):
    d = SOURCES/slug
    return {'profile':d/'onet/profile.txt', 'jd':d/'jd/approved.txt',
            'resumes':d/'resumes/approved', 'drafts':d/'resumes/drafts', 'setup':d/'job_setup.json'}

def read_job(slug, require_profile=True, require_jd=False):
    paths=job_files(slug)
    data = {'paths':paths}
    if require_profile:
        data['profile'] = load_text(paths['profile'], min_length=60)
    if require_jd:
        data['jd'] = load_text(paths['jd'], min_length=50)
    return data

def list_resumes(slug, source='approved'):
    folder=job_files(slug)['resumes' if source=='approved' else 'drafts']
    files=sorted(folder.glob('R*.txt'))
    if not files:
        raise ValueError(f'没有可用简历：{folder.relative_to(ROOT)}；生成草案后请先人工审核。')
    return [(f.stem,load_text(f,min_length=40)) for f in files]

def list_moral_pairs():
    files=sorted((MORALS/'approved').glob('*.json'))
    if not files:
        raise ValueError('没有批准的道德配对材料：materials/morality/approved/*.json')
    pairs=[]
    for f in files:
        d=load_json(f)
        for k in ['pair_id','foundation','neutral','negative']:
            if not isinstance(d.get(k),str) or not d[k].strip():
                raise ValueError(f'{f.name}: 必须有非空字段 {k}')
        if d['foundation'] not in FOUNDATIONS:
            raise ValueError(f'{f.name}: foundation 不是六个允许标签之一')
        pairs.append(d)
    if len({p['pair_id'] for p in pairs})!=len(pairs):
        raise ValueError('重复的 pair_id')
    return pairs

def new_task(kind, taskid, prompt, metadata, response_json=False):
    return {'task':kind,'task_id':taskid,'metadata':metadata,
            'messages':[{'role':'user','content':prompt}],
            'json_mode':response_json}

def make_tasks(kind, args, occupations, config):
    if kind not in TASK_TO_PROFILE:
        raise ValueError(f'任务类型不支持：{kind}')
    if kind in ['jd','resume','resume-review','baseline','abc','moral-relevance']:
        if not args.occupation:
            raise ValueError('此任务必须提供 --occupation')
        if args.occupation not in occupations:
            raise ValueError(f'未知职业：{args.occupation}')
    if kind=='jd':
        info=read_job(args.occupation)
        setup=load_json(info['paths']['setup'])
        if not setup.get('company_profile','').strip() or not setup.get('job_level','').strip():
            raise ValueError('先填写 job_setup.json 中的 company_profile 与 job_level')
        p=info['profile']
        user=render('generation/jd.txt',occupation_name=occupations[args.occupation]['onet_name'],
               onet_code=occupations[args.occupation]['onet_code'],
               job_title=setup['job_title'],company_profile=setup['company_profile'],
               job_level=setup['job_level'],additional_requirements=setup.get('additional_requirements','无'),
               onet_profile=p)
        return [new_task(kind,'JD01',user,{'occupation':args.occupation},False)]
    if kind=='resume':
        info=read_job(args.occupation,require_jd=True)
        if args.count>20:
            raise ValueError('单批新生成简历最多20份')
        ret=[]
        for i in range(args.start_index,args.start_index+args.count):
            rid=f'R{i:02}'
            user=render('generation/resume.txt',onet_profile=info['profile'],
                job_description=info['jd'],resume_id=rid,reference_date=config['reference_date'])
            ret.append(new_task(kind,rid,user,
                          {'occupation':args.occupation,'resume_id':rid},False))
        return ret
    if kind=='moral-generate':
        if args.foundation not in FOUNDATIONS:
            raise ValueError('请指定 --foundation care/fairness/loyalty/authority/sanctity/liberty')
        if args.count>20: raise ValueError('单次最多20组草案')
        ret=[]
        for i in range(args.start_index,args.start_index+args.count):
            pid=f'{args.foundation.upper()}_{i:03}'
            user=render('generation/morality.txt',foundation=FOUNDATION_CN[args.foundation],pair_id=pid)
            ret.append(new_task(kind,pid,user,
                    {'pair_id':pid,'foundation':args.foundation},True))
        return ret
    if kind=='principles':
        definitions={
            'morality':'私人道德信息：候选人在工作之外的日常生活中表现出的行为及其道德品质信息。',
            'ability':'专业能力信息：候选人的相关教育、工作经历、专业技能及工作成果所提供的专业胜任力证据。'
        }
        tasks={
            'task1':'任务一：专业能力判断。根据招聘资料，判断应聘者能否完成相应岗位的专业工作。',
            'task2':'任务二：面试推荐判断。根据招聘资料，决定是否建议候选人进入下一轮面试。'
        }
        ret=[]
        for def_order in [('morality','ability'),('ability','morality')]:
            for task_order in [('task1','task2'),('task2','task1')]:
                condition=('M' if def_order[0]=='morality' else 'A') + ('12' if task_order[0]=='task1' else '21')
                schema={x:{'priority':'','weight_ability':None,'weight_morality':None,
                     'importance_ability':None,'importance_morality':None,'reason':''} for x in task_order}
                user=render('experiments/principles.txt',definitions='\n'.join(definitions[x] for x in def_order),
                             tasks='\n'.join(tasks[x] for x in task_order),
                             json_schema=json.dumps(schema,ensure_ascii=False,indent=2))
                for rep in range(1,args.repeat+1):
                    ret.append(new_task(kind,f'{condition}_T{rep:02}',user,
                                 {'condition':condition,'definition_order':def_order,'task_order':task_order,'repeat':rep},True))
        return ret
    if kind=='resume-review':
        info=read_job(args.occupation,require_jd=True)
        ret=[]
        for rid, rtxt in list_resumes(args.occupation,args.source):
            user=render('validation/resume_review.txt',job_description=info['jd'],resume_text=rtxt)
            ret.append(new_task(kind,rid,user,
                                {'occupation':args.occupation,'resume_id':rid,'source':args.source},True))
        return ret
    if kind in ('moral-check','moral-relevance'):
        info=read_job(args.occupation,require_profile=False,require_jd=True) if kind=='moral-relevance' else None
        pairs=list_moral_pairs()
        items=[]
        for d in pairs:
            for type_ in ['neutral','negative']:
                items.append((d['pair_id'],type_,d[type_]))
        rnd=random.Random(int(sha256(args.run_id)[:12],16))
        rnd.shuffle(items)
        ret=[]
        for pid,kind_,story in items:
            if kind=='moral-relevance':
                user=render('validation/moral_relevance.txt',job_description=info['jd'],behavior_text=story)
                meta={'pair_id':pid,'background_type':kind_,'occupation':args.occupation}
            else:
                user=render('validation/moral_check.txt',behavior_text=story)
                meta={'pair_id':pid,'background_type':kind_}
            # Label and foundation are local metadata only, not sent to the judge.
            ret.append(new_task(kind,f'{pid}_{kind_}',user,meta,True))
        return ret
    if kind in ('baseline','abc'):
        info=read_job(args.occupation,require_jd=True)
        resumes=list_resumes(args.occupation,'approved')
        rub=read_prompt('experiments/score_rubric.txt')
        pairs=list_moral_pairs() if kind=='abc' else []
        ret=[]
        for rid,rtxt in resumes:
            conditions=[('A',None,None)]
            if kind=='abc':
                for pair in pairs:
                    conditions.extend([('B',pair['pair_id'],pair['neutral']),('C',pair['pair_id'],pair['negative'])])
            for cond,pid,story in conditions:
                section=('\n【背景调查补充信息】\n'
                         '招聘团队通过背景调查收集了候选人的补充信息，调查渠道包括公开社交媒体、熟人访谈及过往任职单位访谈。\n'
                         +story+'\n') if story is not None else ''
                user=render('experiments/hiring_rating.txt',job_description=info['jd'],resume_text=rtxt,
                         background_section=section,score_rubric=rub)
                for rep in range(1,args.repeat+1):
                    taskid=f'{rid}_{cond}'+(f'_{pid}' if pid else '')+f'_T{rep:02}'
                    ret.append(new_task(kind,taskid,user,
                         {'occupation':args.occupation,'resume_id':rid,'condition':cond,
                         'pair_id':pid,'repeat':rep},True))
        rnd=random.Random(int(sha256(args.run_id+'|'+args.occupation+'|'+kind)[:12],16))
        rnd.shuffle(ret)
        return ret
    raise ValueError(f'Unsupported task: {kind}')


def check_response(kind, text):
    if not text or not text.strip(): raise ValueError('空白响应')
    try: parsed=json.loads(text)
    except json.JSONDecodeError as exc: raise ValueError('JSON解析失败: '+str(exc)) from exc
    if not isinstance(parsed,dict): raise ValueError('顶层必须是JSON对象')
    def iv(d,k,lo,hi):
        v=d.get(k)
        if type(v) is not int or not lo<=v<=hi: raise ValueError(f'{k}不是{lo}–{hi}的整数: {v}')
    if kind in ('baseline','abc'):
        for k in ['education_fit','work_experience','professional_skills','accomplishments','overall_suitability']:
            iv(parsed,k,1,5)
        iv(parsed,'interview_probability',0,100)
        if not isinstance(parsed.get('reason'),str): raise ValueError('缺少reason')
    elif kind=='principles':
        for tk in ['task1','task2']:
            sub=parsed.get(tk)
            if not isinstance(sub,dict): raise ValueError(f'缺少{tk}')
            if sub.get('priority') not in ['私人道德信息','专业能力信息']:
                raise ValueError('priority无效')
            for k in ['weight_ability','weight_morality']: iv(sub,k,0,100)
            if sub['weight_ability']+sub['weight_morality']!=100: raise ValueError('权重不等于100')
            for k in ['importance_ability','importance_morality']: iv(sub,k,1,7)
            if not isinstance(sub.get('reason'),str): raise ValueError('缺少理由')
    elif kind=='moral-check':
        for k in ['moral_valence','comprehensibility','naturalness']:
            iv(parsed,k,1,7)
        v=parsed.get('moral_foundations')
        if not isinstance(v,list) or len(v)>2 or any(not isinstance(x,str) for x in v):
            raise ValueError('moral_foundations需要0–2个字符串')
    elif kind=='moral-relevance':
        iv(parsed,'direct_professional_relevance',1,7)
    elif kind=='moral-generate':
        for k in ['pair_id','foundation','neutral','negative']:
            if not isinstance(parsed.get(k),str) or len(parsed[k].strip())<3:
                raise ValueError(f'缺少{k}')
    elif kind=='resume-review':
        iv(parsed,'naturalness',1,7);iv(parsed,'professional_plausibility',1,7)
    return parsed


def path_for(task, run_id):
    kind=task['task']; m=task['metadata']
    if kind=='moral-relevance':
        folder=RESULTS/m['occupation']/'moral_relevance'
    elif kind in ['principles']:
        folder=RESULTS/'_principles'/kind
    elif kind in ['moral-generate','moral-check']:
        folder=RESULTS/'_morality'/kind
    else:
        slug=m['occupation']
        folder=RESULTS/slug/({'jd':'jd_generation','resume':'resume_generation',
                          'resume-review':'resume_review','baseline':'baseline','abc':'abc'}[kind])
    return folder/'runs'/run_id/task['task_id']


def validate_run_id(run_id):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,48}',run_id):
        raise ValueError('run-id 仅允许字母/数字/下划线/短横线，最长49字符')


def api_request(settings, task):
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError('未安装依赖：py -m pip install -r requirements.txt') from e
    api_key=os.environ.get('DEEPSEEK_API_KEY','').strip()
    if not api_key:
        raise ValueError('未设置 DEEPSEEK_API_KEY 环境变量')
    profile=settings['profiles'][TASK_TO_PROFILE[task['task']]]
    if profile['thinking']=='enabled' and 'temperature' in profile:
        raise ValueError('思考模式不可使用有效temperature。请调整配置。')
    kwargs={
        'model':profile['model'], 'messages':task['messages'],
        'max_tokens':profile['max_tokens'], 'extra_body':{'thinking':{'type':profile['thinking']}},
    }
    if profile['thinking']=='disabled' and profile.get('temperature') is not None:
        kwargs['temperature']=profile['temperature']
    if task['json_mode']:
        kwargs['response_format']={'type':'json_object'}
    client=OpenAI(api_key=api_key,base_url=settings['api_base_url'],
                  timeout=float(settings['api_timeout_seconds']),max_retries=0)
    response=client.chat.completions.create(**kwargs)
    return response,kwargs


def response_archive(task, response, request_kwargs):
    raw=response.model_dump(mode='json') if hasattr(response,'model_dump') else {}
    msg=response.choices[0].message if response.choices else None
    content=getattr(msg,'content',None) if msg else None
    finish=response.choices[0].finish_reason if response.choices else None
    if finish!='stop':
        raise ValueError('finish_reason='+str(finish))
    parsed=check_response(task['task'],content) if task['json_mode'] else None
    return raw,content,parsed


def record_task(task, settings, args):
    base=path_for(task,args.run_id)
    base.mkdir(parents=True,exist_ok=True)
    request={'task':task,'config':settings['profiles'][TASK_TO_PROFILE[task['task']]],
             'api_base_url':settings['api_base_url']}
    request_hash=sha256(canonical(request))
    meta_path=base/'record.json'
    if meta_path.exists():
        old=load_json(meta_path)
        if old.get('request_sha256')!=request_hash:
            raise ValueError(f'同一run-id/task-id的材料或Prompt已变化：{base}，请使用新 run-id')
        if old.get('status')=='ok':
            print('SKIP 已有有效记录',base.relative_to(ROOT))
            return 'skip'
        if not args.retry_failed:
            print('SKIP 上次失败，使用 --retry-failed 手动重试',base.relative_to(ROOT))
            return 'skip'
        # Preserve every failed attempt, including the raw response, before an explicit retry.
        history=base/'failed_attempts'/now().replace(':','-')
        history.mkdir(parents=True,exist_ok=False)
        for old_file in base.iterdir():
            if old_file.is_file(): shutil.copy2(old_file, history/old_file.name)
    # Save exact scientific input BEFORE API call; never record auth token.
    (base/'request.json').write_text(json.dumps(request,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    metadata={'task':task['task'],'task_id':task['task_id'],'context':task['metadata'],
              'python_version':sys.version.split()[0],
              'openai_sdk_version':sdk_version(),
              'runner_sha256':sha256(Path(__file__).read_bytes()),
              'request_sha256':request_hash,'prompt_sha256':sha256(canonical(task['messages'])),
              'timestamp_utc':now(),'status':'error'}
    try:
        response, kwargs = api_request(settings,task)
        raw=response.model_dump(mode='json')
        (base/'raw_response.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        metadata['api_id']=getattr(response,'id',None)
        metadata['returned_model']=getattr(response,'model',None)
        metadata['system_fingerprint']=getattr(response,'system_fingerprint',None)
        metadata['finish_reason']=response.choices[0].finish_reason if response.choices else None
        metadata['usage']=raw.get('usage')
        content=response.choices[0].message.content if response.choices else None
        (base/'answer.txt').write_text(content or '',encoding='utf-8')
        if metadata['finish_reason']!='stop':
            raise ValueError('finish_reason='+str(metadata['finish_reason']))
        if task['json_mode']:
            parsed=check_response(task['task'],content)
            if task['task']=='moral-generate':
                # Keep the normalized foundation code locally; generated text is still unapproved.
                parsed['foundation']=task['metadata']['foundation']
                parsed['pair_id']=task['metadata']['pair_id']
            (base/'parsed.json').write_text(json.dumps(parsed,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        else:
            if not content or not content.strip(): raise ValueError('生成的文本为空')
            if task['task']=='resume':
                draft=job_files(task['metadata']['occupation'])['drafts']/(task['metadata']['resume_id']+'.txt')
                if draft.exists() and draft.read_text(encoding='utf-8')!=content:
                    raise ValueError('同名草稿存在不同内容；请先处理或使用不同候选人编号')
                draft.write_text(content,encoding='utf-8')
            if task['task']=='jd':
                draft=job_files(task['metadata']['occupation'])['jd']/'draft.txt'
                if draft.exists() and draft.read_text(encoding='utf-8')!=content:
                    raise ValueError('已有不同 JD 草稿。请先人工审核/归档，再重新生成')
                draft.write_text(content,encoding='utf-8')
        if task['task']=='moral-generate':
            draft=MORALS/'drafts'/(task['metadata']['pair_id']+'.json')
            if draft.exists() and load_json(draft)!=parsed:
                raise ValueError('已有不同的道德草稿；请先审核或变更编号')
            draft.write_text(json.dumps(parsed,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        metadata['status']='ok'
        print('OK',base.relative_to(ROOT))
    except Exception as e:
        metadata['error_type']=type(e).__name__
        metadata['error_message']=str(e)[:1000]
        print('ERROR',base.relative_to(ROOT),type(e).__name__,str(e)[:200],file=sys.stderr)
    meta_path.write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if metadata['status']!='ok': return 'error'
    return 'ok'


def fetch_onet(args,occ):
    if args.occupation not in occ: raise ValueError('未知职业')
    code=occ[args.occupation]['onet_code']
    url=f'https://www.onetonline.org/link/details/{code}'
    folder=job_files(args.occupation)['profile'].parent
    if not args.execute:
        print('预览：将从 O*NET 唯一来源下载',url)
        print('只保存 source_details.html、source_details.txt、source_metadata.json；需人工确认再复制为 profile.txt')
        return
    import requests
    from bs4 import BeautifulSoup
    resp=requests.get(url,timeout=45,headers={'User-Agent':'Mozilla/5.0 (compatible; Academic research download)'})
    resp.raise_for_status()
    soup=BeautifulSoup(resp.text,'html.parser')
    for tag in soup(['script','style','nav','footer']): tag.decompose()
    body=soup.find('main') or soup.find(id='content') or soup.body or soup
    text=body.get_text('\n',strip=True)
    if len(text)<800:
        raise RuntimeError('页面抓取结果过短，可能被访问限制；请手工从 O*NET 复制资料')
    (folder/'source_details.html').write_text(resp.text,encoding='utf-8')
    (folder/'source_details.txt').write_text(text,encoding='utf-8')
    meta={'url':url,'retrieved_utc':now(),'status_code':resp.status_code,
          'sha256_html':sha256(resp.content),'sha256_text':sha256(text),
          'source':'O*NET OnLine','researcher_reviewed':False}
    (folder/'source_metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('抓取成功：', (folder/'source_details.txt').relative_to(ROOT))
    print('请阅读内容、保留有效职业栏目，并将审查后的文字保存为 onet/profile.txt。')


def status(occ):
    print('职业材料状态（旧版草案未自动导入）：')
    for slug,d in occ.items():
        paths=job_files(slug)
        n=len(list(paths['resumes'].glob('R*.txt')))
        print(f"  {slug:22s} {d['onet_code']:12s} O*NET={'是' if paths['profile'].exists() else '否'} JD={'是' if paths['jd'].exists() else '否'} 通过审核简历={n}")
    print('  道德材料通过审核：',len(list((MORALS/'approved').glob('*.json'))),'组')
    print('  抽象原则调查不依赖任何职业材料')


def export_results():
    records=[]
    for f in RESULTS.rglob('record.json'):
        d=load_json(f)
        row={k:v for k,v in d.items() if k not in ('usage','context')}
        row.update({f'meta_{k}':v for k,v in (d.get('context') or {}).items()})
        if d.get('usage'):
            row.update({f'token_{k}':v for k,v in d['usage'].items() if isinstance(v,int)})
        parsed=f.parent/'parsed.json'
        if parsed.exists():
            obj=load_json(parsed)
            row.update({'result_'+k:(canonical(v) if isinstance(v,(dict,list)) else v) for k,v in obj.items()})
        records.append(row)
    out=RESULTS/'all_results.csv'
    fields=sorted(set().union(*(r.keys() for r in records))) if records else ['task','task_id','status']
    with out.open('w',encoding='utf-8-sig',newline='') as fp:
        w=csv.DictWriter(fp,fieldnames=fields); w.writeheader(); w.writerows(records)
    print('已导出',len(records),'条记录：',out.relative_to(ROOT))


def main(argv=None):
    parser=argparse.ArgumentParser(description='DeepSeek HR 研究任务包：默认仅预览，不收费')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('status',help='查看材料与批准状态')
    fetch=sub.add_parser('fetch-onet',help='从 O*NET 下载职业详细资料（不会自动批准）')
    fetch.add_argument('--occupation',required=True)
    fetch.add_argument('--execute',action='store_true')
    run=sub.add_parser('run',help='生成任务、预览或使用 API 执行')
    run.add_argument('--task',required=True,choices=list(TASK_TO_PROFILE))
    run.add_argument('--occupation',help='职业slug，抽象原则与道德材料任务不需要')
    run.add_argument('--foundation',choices=FOUNDATIONS)
    run.add_argument('--source',choices=['drafts','approved'],default='drafts',help='简历审读阶段读取什么')
    run.add_argument('--count',type=int,default=2,help='简历或道德草案生成数量')
    run.add_argument('--start-index',type=int,default=1)
    run.add_argument('--repeat',type=int,default=1)
    run.add_argument('--run-id',default='pilot01')
    run.add_argument('--limit',type=int)
    run.add_argument('--execute',action='store_true',help='真正发送 API 请求并计费')
    run.add_argument('--retry-failed',action='store_true')
    sub.add_parser('export',help='汇总已保存评分与元数据到 CSV')
    args=parser.parse_args(argv)
    occ=load_json(ROOT/'config/occupations.json')
    settings=load_json(ROOT/'config/settings.json')
    if args.command=='status':status(occ);return 0
    if args.command=='fetch-onet': fetch_onet(args,occ);return 0
    if args.command=='export':export_results();return 0
    if args.count<1 or args.start_index<1 or args.repeat<1 or (args.limit is not None and args.limit<1):
        raise ValueError('count/start-index/repeat/limit 必须是正整数')
    validate_run_id(args.run_id)
    all_tasks=make_tasks(args.task,args,occ,settings)
    tasks=all_tasks[:args.limit] if args.limit is not None else all_tasks
    profile=settings['profiles'][TASK_TO_PROFILE[args.task]]
    print(f"任务={args.task} 计划={len(all_tasks)} 当前选中={len(tasks)} 模型={profile['model']} 思考={profile['thinking']} 温度={profile.get('temperature')} run-id={args.run_id}")
    if not args.execute:
        print('DRY RUN：没有发送任何 API 请求；以下是将发送的请求摘要。')
        for t in tasks:
            print('  ',t['task_id'],'元数据=',t['metadata'],'PromptSHA=',sha256(canonical(t['messages']))[:12])
        if tasks:
            m=tasks[0]['messages']
            print('\n----- 第一条请求的完整 Prompt（role=user，最多显示12000字符） -----\n',m[0]['content'][:12000])
        return 0
    if len(tasks)>settings['max_requests_per_command']:
        raise ValueError(f"本批请求{len(tasks)}条，超过安全上限{settings['max_requests_per_command']}。先使用 --limit 或修改配置后有意识地扩展。")
    if not os.environ.get('DEEPSEEK_API_KEY','').strip():
        raise ValueError('请先在 PowerShell 中设置 DEEPSEEK_API_KEY；当前未发送请求')
    # Freeze the entire planned batch (not just --limit N) to prevent silent changes on resumption.
    parent=path_for(tasks[0],args.run_id).parent
    parent.mkdir(parents=True,exist_ok=True)
    manifest={'task':args.task,'occupation':args.occupation,'run_id':args.run_id,
              'settings':settings['profiles'][TASK_TO_PROFILE[args.task]],
              'requests':{t['task_id']:sha256(canonical(t)) for t in all_tasks},
              'runner_sha256':sha256(Path(__file__).read_bytes())}
    manifest_file=parent/'manifest.json'
    if manifest_file.exists():
        if load_json(manifest_file)!=manifest:
            raise ValueError('批次清单与已有文件不同（材料/Prompt/配置/程序已变化）。改用新 --run-id。')
    else:
        manifest_file.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('请求将产生实际费用；按顺序发送，每次作为独立新会话。')
    errors=0
    for t in tasks:
        res=record_task(t,settings,args)
        if res=='error':errors+=1
        time.sleep(settings['request_pause_seconds'])
    print('批次结束；异常=',errors,'；使用 python src/hrpilot.py export 导出结果')
    return 1 if errors else 0

if __name__=='__main__':
    try: sys.exit(main())
    except Exception as exc:
        print('失败：',exc,file=sys.stderr)
        sys.exit(2)
