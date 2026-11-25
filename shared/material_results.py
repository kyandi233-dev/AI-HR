"""Batch-first material records. Experiments keep their existing storage layout."""
from __future__ import annotations
import csv
import datetime as dt
import json
import re
import threading
from pathlib import Path
from zipfile import ZipFile
from . import common as c

KINDS={'jd','resume','moral-generate','resume-review','moral-review'}
INFO='批次信息.json'
_lock=threading.RLock()
_mapping_cache=(None,None)


def root():return c.ROOT/'material_preparation/results'
def mapping_path():return c.ROOT/'material_preparation/config/results_layout.json'
def mapping():
    global _mapping_cache
    p=mapping_path()
    if not p.exists():return {'aliases':{},'files':{}}
    key=(str(p),p.stat().st_mtime_ns,p.stat().st_size)
    if _mapping_cache[0]!=key:_mapping_cache=(key,json.loads(p.read_text(encoding='utf-8')))
    return _mapping_cache[1]
def category(kind):return 'morality_generation' if kind in {'moral-generate','moral-review'} else 'occupation_generation'
def relative(path):return Path(path).resolve().relative_to(c.ROOT.resolve()).as_posix()
def write(path,data):
    from .storage import write_json
    write_json(path,data)
def info(base):return json.loads((Path(base)/INFO).read_text(encoding='utf-8'))
def is_batch(base):return (Path(base)/INFO).is_file()


def old_key(path):
    path=Path(path)
    try:return relative(path)
    except ValueError:return None


def resolve_path(path):
    p=Path(path)
    if p.exists():return p
    item=mapping()['files'].get(old_key(p))
    if item and item.get('path'):return c.ROOT/item['path']
    return p


def legacy_bytes(path):
    item=mapping()['files'].get(old_key(path))
    if not item:raise FileNotFoundError(path)
    if item.get('path'):return (c.ROOT/item['path']).read_bytes()
    with ZipFile(c.ROOT/item['archive']) as z:return z.read(item['member'])


def aliases_for(base,kind):return info(base).get('aliases',{}).get(kind,[])
def run_matches(kind,requested,recorded):
    if requested==recorded:return True
    try:
        base=batch_root(kind,requested)
        return recorded in aliases_for(base,kind) or recorded==base.name
    except (ValueError,FileNotFoundError):return False


def batch_root(kind,run_id,create=False):
    parent=root()/category(kind)
    alias=mapping()['aliases'].get(kind+':'+run_id)
    if alias:return c.ROOT/alias
    direct=parent/run_id
    if re.fullmatch(r'\d{8}_\d{3,}',run_id):return direct
    if parent.exists():
        matches=[p.parent for p in parent.glob('*/'+INFO) if run_id in info(p.parent).get('aliases',{}).get(kind,[])]
        if len(matches)>1:raise ValueError('批次别名不唯一：'+run_id)
        if matches:return matches[0]
    if not create:raise ValueError('找不到材料批次：'+run_id)
    date=re.search(r'20\d{6}',run_id)
    date=date.group() if date else dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%Y%m%d')
    used=[int(p.name.rsplit('_',1)[1]) for p in parent.glob('*') if p.is_dir() and re.fullmatch(r'\d{8}_\d{3,}',p.name)] if parent.exists() else []
    return parent/f'{date}_{max(used,default=0)+1:03}'


def group(task):
    meta=task['metadata']
    if meta.get('occupation'):
        return meta.get('material_directory') or c.job_files(meta['occupation'])['jd_draft'].parent.name
    if meta.get('foundation'):
        return meta['foundation']
    pid=meta.get('pair_id','')
    if pid:
        prefix=pid.split('_',1)[0].lower()
        if prefix in c.FOUNDATIONS:return prefix
        pair_file=c.ROOT/'material_preparation'/meta.get('source','drafts')/'morality'/(pid+'.json')
        if pair_file.is_file():
            found=c.load_json(pair_file).get('foundation')
            if found in c.FOUNDATIONS:return found
    return 'unknown'


def task_key(task):return '|'.join((task['task'],group(task),task['task_id']))
def group_root(task,run_id):return batch_root(task['task'],run_id,True)/group(task)
def owner(path):
    p=Path(path)
    for parent in [p,*p.parents]:
        if is_batch(parent):return parent
        if parent==c.ROOT:break
    return None


def output_path(inp):
    inp=Path(inp)
    return inp.with_name('output.json') if inp.name=='input.json' else inp.with_name(inp.name.replace('.input.json','.output.json'))


def inputs(base,task_id=None,kind=None):
    base=Path(base)
    found=[]
    if base.exists():
        pattern=('*_jd*/input.json' if task_id=='JD01' else '*_'+task_id+'*/input.json') if task_id else 'input.json'
        for p in base.rglob(pattern):
            d=json.loads(p.read_text(encoding='utf-8'))
            if task_id is not None and d.get('task_id')!=task_id:continue
            if kind and d.get('task')!=kind:continue
            found.append(p)
    return sorted(found,key=lambda p:(json.loads(p.read_text(encoding='utf-8')).get('sequence') or 0,
                                     json.loads(p.read_text(encoding='utf-8')).get('attempt',1)))


def request_equivalent(first,second):
    # Metadata contains source-code fingerprints and historical path aliases. The
    # frozen request remains authoritative when the model's inputs are unchanged.
    return (first['config']==second['config'] and first['api_base_url']==second['api_base_url']
            and first['task']['messages']==second['task']['messages']
            and first['task']['json_mode']==second['task']['json_mode'])


def prepare(tasks,settings,args,plan=None):
    """Freeze a stage and its complete inputs before previewing or executing."""
    from .storage import request_for
    if not tasks:return None
    with _lock:
        kind=tasks[0]['task'];base=batch_root(kind,args.run_id,True)
        base.mkdir(parents=True,exist_ok=True)
        data=info(base) if is_batch(base) else {'format_version':3,'run_id':base.name,'created_utc':c.now(),
                    'aliases':{},'plans':{},'tasks':{},'generated':{}}
        aliases=data['aliases'].setdefault(kind,[])
        for name in [args.run_id,base.name]:
            if name not in aliases:aliases.append(name)
        stage_plan=plan or {'task':kind,'occupations':getattr(args,'occupations',[])}
        def comparable(p):
            value={k:v for k,v in p.items() if k not in {'run_id','concurrency','requests'}}
            if 'config' in value:
                value['config']={k:v for k,v in value['config'].items() if k not in {'run_id','reviewers','review_files','review_config'}}
            if value.get('jd_run_id'):
                value['jd_run_id']=str(batch_root('jd',value['jd_run_id']))
            return value
        if kind in data['plans'] and comparable(data['plans'][kind])!=comparable(stage_plan):
            raise ValueError('批次计划已变化，请使用新批次')
        data['plans'].setdefault(kind,stage_plan)
        parameters={'model':settings['profiles'][c.TASK_TO_PROFILE[kind]],'api_base_url':settings['api_base_url']}
        saved=data.setdefault('parameters',{}).get(kind)
        if saved is not None and saved!=parameters:raise ValueError('同一批次的模型参数已变化，请使用新批次')
        data['parameters'].setdefault(kind,parameters)
        known={key for key,value in data['tasks'].items() if value['task']==kind}
        requested={task_key(task) for task in tasks}
        if known and known!=requested:raise ValueError('同一阶段的任务范围已变化，请使用新批次')
        sequence=max((x['sequence'] for x in data['tasks'].values()),default=0)
        prepared=[]
        for task in tasks:
            key=task_key(task);request=request_for(task,settings)
            existing=inputs(base/group(task),task['task_id'],kind)
            if existing:
                for p in existing:
                    old=json.loads(p.read_text(encoding='utf-8'))
                    if not request_equivalent(old['request'],request):raise ValueError('同一批次的输入已变化，请使用新批次')
                prepared.append((task,None,None));continue
            if key not in data['tasks']:
                sequence+=1
                data['tasks'][key]={'sequence':sequence,'group':group(task),'task_id':task['task_id'],'task':kind}
            number=data['tasks'][key]['sequence']
            name=(f'{number:03}_'+('jd' if kind=='jd' else 'resume_'+task['task_id'] if kind=='resume'
                                else task['task_id'] if kind=='moral-generate' else 'review_'+task['task_id']))
            path=base/group(task)/name/'input.json'
            content={'run_id':args.run_id,'task_id':task['task_id'],'attempt':1,'task':kind,
                     'stage':getattr(args,'stage','pilot'),'concurrency':getattr(args,'concurrency',1),
                     'sequence':number,'context':task['metadata'],'timestamp_utc':c.now(),
                     'request':request,'request_sha256':c.sha256(c.canonical(request)),
                     'transport':{'api_timeout_seconds':settings['api_timeout_seconds'],'stream':bool(settings.get('_stream'))}}
            prepared.append((task,path,content))
        if not is_batch(base) or info(base)!=data:write(base/INFO,data)
        for task,path,content in prepared:
            if path is not None:
                if path.exists():
                    if json.loads(path.read_text(encoding='utf-8'))['request']!=content['request']:raise ValueError('调用目录已被占用')
                else:
                    from .storage import write_json
                    write_json(path,content,exclusive=True)
        refresh(base)
        return base


def begin(task,settings,args):
    """Claim one immutable input; retries get a new sibling, never overwrite."""
    from .storage import write_json
    with _lock:
        base=batch_root(task['task'],args.run_id)
        files=inputs(base/group(task),task['task_id'],task['task'])
        if not files:raise ValueError('请先冻结批次输入')
        latest=files[-1];out=output_path(latest)
        if not out.exists():inp=latest;data=json.loads(inp.read_text(encoding='utf-8'))
        else:
            old=json.loads(latest.read_text(encoding='utf-8'))
            attempt=old['attempt']+1
            first=files[0].parent.name.split('_retry')[0].removesuffix('_fail')
            inp=latest.parent.parent/(first+f'_retry{attempt-1:03}')/'input.json'
            data={**old,'attempt':attempt,'timestamp_utc':c.now(),
                  'transport':{'api_timeout_seconds':settings['api_timeout_seconds'],'stream':bool(settings.get('_stream'))}}
            write_json(inp,data,exclusive=True)
        claim=inp.parent/'.executing.lock'
        try:
            with claim.open('x') as f:f.write(c.now())
        except FileExistsError:raise ValueError('此调用正在执行；停止重复请求')
        return inp,output_path(inp),data,claim


def finish(inp,status,claim):
    with _lock:
        if claim.exists():claim.unlink()
        if status!='ok' and not inp.parent.name.endswith('_fail'):
            target=inp.parent.with_name(inp.parent.name+'_fail')
            if target.exists():raise ValueError('失败记录目录已存在，不能覆盖')
            inp.parent.rename(target)


def refresh(base):
    """One readable table for every task and attempt in the whole batch."""
    with _lock:
        base=Path(base)
        if not is_batch(base):return
        data=info(base)
        if data.get('task')=='onet-download':
            download=data.get('download',data)
            with (base/'调用清单.csv').open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.writer(f);w.writerow(['职业','O*NET编码','状态','来源网址','错误说明'])
                for item in download.get('occupations',[]):
                    w.writerow([item['occupation'],item['onet_code'],item['status'],item.get('url',''),item.get('error','')])
            return
        rows=[]
        for p in inputs(base):
            d=json.loads(p.read_text(encoding='utf-8'));op=output_path(p)
            out=json.loads(op.read_text(encoding='utf-8')) if op.exists() else {}
            meta=d['context'];kind=d['task']
            draft=None
            if kind in {'jd','resume'}:
                paths=c.job_files(meta['occupation'])
                draft=paths['jd_draft'] if kind=='jd' else paths['drafts']/(d['task_id']+'.txt')
                if not draft.exists() or draft.read_bytes().decode('utf-8')!=out.get('answer'):draft=None
            elif kind=='moral-generate':
                candidate=c.ROOT/'material_preparation/drafts/morality'/(d['task_id']+'.json')
                if candidate.exists() and out.get('status')=='ok' and c.load_json(candidate)==out.get('parsed'):draft=candidate
            display_sequence=data.get('tasks',{}).get(task_key(d['request']['task']),{}).get('sequence',d.get('sequence'))
            rows.append([display_sequence,kind,meta.get('occupation',meta.get('foundation')),d['task_id'],
                         meta.get('ability_level'),d.get('attempt',1),out.get('status','未执行'),
                         relative(p),relative(op) if op.exists() else '',relative(draft) if draft else '',out.get('error_message','')])
        with (base/'调用清单.csv').open('w',encoding='utf-8-sig',newline='') as f:
            rows.sort(key=lambda row:(row[0] or 0,row[5]))
            w=csv.writer(f);w.writerow(['序号','类型','职业或维度','材料编号','目标水平','尝试次数','状态','输入','输出','当前草稿','错误说明']);w.writerows(rows)


def load_manifest(kind,run_id):
    try:base=batch_root(kind,run_id)
    except ValueError:
        legacy=root()/'material_generation'/run_id/'generated_manifest.json'
        if legacy.is_file():return json.loads(legacy.read_text(encoding='utf-8'))
        raise
    data=info(base).get('generated',{}).get(kind)
    if data is None:raise ValueError('此批次没有成功材料清单：'+kind)
    data=json.loads(json.dumps(data))
    data.setdefault('source_run_id',data['run_id'])
    data['run_id']=base.name
    for item in data['materials']:
        for key in ('input','output'):
            item[key]=relative(resolve_path(c.ROOT/item[key]))
    return data


def save_manifest(kind,run_id,manifest):
    base=batch_root(kind,run_id);data=info(base)
    data['generated'][kind]=manifest;write(base/INFO,data);refresh(base)


def manifest_for_id(run_id,kind=None):
    if kind:return load_manifest(kind,run_id)
    found=[]
    for candidate in ('jd','resume'):
        try:found.append(load_manifest(candidate,run_id))
        except ValueError:pass
    if len(found)!=1:raise ValueError('请用 --task jd 或 --task resume 明确批准类型')
    return found[0]


def manifest_source(kind,run_id):
    data=load_manifest(kind,run_id)
    return data['run_id']
