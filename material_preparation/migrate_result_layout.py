"""Reproducible, hash-checked migration. Default is a read-only inventory."""
if __name__=='__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
import datetime as dt
import json
import re
import shutil
import tempfile
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from shared import common as c,material_results as mr

OLD={'jd_generation','resume_generation','resume_review','material_generation','morality_generation','morality_preview','onet_download'}


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def date_for(name):
    found=re.search(r'20\d{6}',name)
    if not found:raise ValueError('历史批次缺少日期：'+name)
    return found.group()


def inventory():
    result=mr.root();stages={};assignments={}
    def stage(kind,rid):
        return stages.setdefault((kind,rid),{'kind':kind,'run_id':rid,'files':set(),'inputs':[],
                                           'previews':[],'plan':None,'generated':None})
    for name,kind in [('jd_generation','jd'),('resume_generation','resume'),('resume_review','resume-review')]:
        for folder in (result/name).glob('*/*'):
            if not folder.is_dir():continue
            item=stage(kind,folder.name)
            for p in folder.rglob('*'):
                if not p.is_file():continue
                item['files'].add(p)
                if p.name.endswith('.input.json'):item['inputs'].append(p)
                if p.name.endswith('.request.json'):item['previews'].append(p)
    for folder in (result/'material_generation').glob('*'):
        if not folder.is_dir():continue
        plan=read(folder/'plan.json');item=stage(plan['task'],folder.name);item['plan']=plan
        item['files'].update(p for p in folder.rglob('*') if p.is_file())
        if (folder/'generated_manifest.json').exists():item['generated']=read(folder/'generated_manifest.json')
        if (folder/'preview_manifest.json').exists():
            for rec in read(folder/'preview_manifest.json')['requests']:
                request=c.ROOT/rec['request'];prompt=c.ROOT/rec['prompt']
                item['previews'].append(request);item['files'].update([request,prompt])
    for folder in (result/'morality_generation').glob('*'):
        if not folder.is_dir() or re.fullmatch(r'\d{8}_\d{3,}',folder.name):continue
        item=stage('moral-generate',folder.name)
        item['files'].update(p for p in folder.rglob('*') if p.is_file())
        item['plan']=read(folder/'plan.json')
        item['previews']=list(folder.glob('*.request.json'))
        item['inputs']=list(folder.rglob('*.input.json'))
    config=c.load_json(c.ROOT/'material_preparation/config/human_review.json')
    pair=(config['jd_run_id'],config['resume_run_id'])
    if stages[('resume',pair[1])]['plan'].get('jd_run_id')!=pair[0]:raise ValueError('当前JD和简历批次未配对')
    groups={}
    for key,item in stages.items():
        if item['kind']=='resume-review':continue
        paired=key in {('jd',pair[0]),('resume',pair[1])}
        ident=('paired',pair[0]) if paired else key
        groups.setdefault(ident,[]).append(item)
    output=[]
    for cat in ['occupation_generation','morality_generation']:
        selected=[(key,items) for key,items in groups.items() if mr.category(items[0]['kind'])==cat]
        selected.sort(key=lambda x:(date_for(x[0][1]),x[0][1]))
        for number,(key,items) in enumerate(selected,1):
            base=result/cat/f'{date_for(key[1])}_{number:03}'
            output.append((base,items))
            for item in items:
                for p in item['files']:assignments[p]=base
    # These two archived AI checks match the first resume draft by exact content.
    for (kind,rid),item in stages.items():
        if kind!='resume-review':continue
        matches=[]
        for base,items in output:
            for source in items:
                if source['kind']!='resume':continue
                answers=[read(p.with_name(p.name.replace('.input.json','.output.json'))).get('answer') for p in source['inputs']]
                checks=['\n'.join(x['content'] for x in read(p)['request']['task']['messages']) for p in item['inputs']]
                if checks and all(any(answer and answer in check for answer in answers) for check in checks):matches.append(base)
        if len(set(matches))!=1:raise ValueError('历史AI审读未唯一匹配原简历')
        base=matches[0]
        for p in item['files']:assignments[p]=base
    onet=sorted((p for p in (result/'onet_download').glob('*/*.json')),key=lambda p:read(p)['started_utc'])
    for number,p in enumerate(onet,1):
        date=read(p)['started_utc'][:10].replace('-','')
        base=result/'onet_download'/f'{date}_{number:03}'
        output.append((base,[]));assignments[p]=base
    for p in (result/'onet_download').glob('*.json'):
        if not onet:raise ValueError('下载历史收据没有可归档批次')
        assignments[p]=assignments[onet[0]]
    images=list((result/'morality_preview').glob('*'))
    all_old={p for name in OLD for p in (result/name).rglob('*') if p.is_file()
             and not (name in {'morality_generation','onet_download'} and any(re.fullmatch(r'\d{8}_\d{3,}',x) for x in p.relative_to(result/name).parts[:-1]))}
    if all_old-set(assignments)-set(images):raise ValueError('存在未登记文件：'+str(all_old-set(assignments)-set(images)))
    return output,assignments,images


def make_stage(base,items,files_map):
    data={'format_version':3,'run_id':base.name,'created_utc':c.now(),'aliases':{},'plans':{},'tasks':{},'generated':{}}
    tasks={};actual={};previews={};data['legacy_link_targets']={}
    for item in items:
        kind=item['kind'];rid=item['run_id'];data['aliases'][kind]=[rid,base.name]
        if item['plan']:data['plans'][kind]=item['plan']
        else:data['plans'][kind]={'task':kind,'run_id':rid}
        if item['generated']:data['generated'][kind]=item['generated']
        for p in item['inputs']:
            rec=read(p);task=rec['request']['task'];key=mr.task_key(task)
            tasks[key]=task;actual.setdefault(key,[]).append((p,rec))
        for p in set(item['previews']):
            req=read(p);task=req['task'];key=mr.task_key(task)
            tasks.setdefault(key,task);previews[key]=(p,req)
    def order(key):
        task=tasks[key];g=mr.group(task)
        return (g,0 if task['task']=='jd' else 1,task['task_id'])
    for number,key in enumerate(sorted(tasks,key=order),1):
        task=tasks[key];kind=task['task'];tid=task['task_id'];g=mr.group(task)
        request=(actual[key][0][1]['request'] if actual.get(key) else previews[key][1])
        data.setdefault('parameters',{}).setdefault(kind,{'model':request['config'],'api_base_url':request['api_base_url']})
        name=f'{number:03}_'+('jd' if kind=='jd' else 'resume_'+tid if kind=='resume' else tid)
        data['tasks'][key]={'sequence':number,'group':g,'task_id':tid,'task':kind}
        records=sorted(actual.get(key,[]),key=lambda x:x[1]['attempt'])
        if not records:
            original,request=previews[key]
            rec={'run_id':next(x['run_id'] for x in items if x['kind']==kind),'task_id':tid,'attempt':1,
                 'task':kind,'stage':'pilot','concurrency':1,'sequence':number,'context':task['metadata'],
                 'timestamp_utc':None,'request':request,'request_sha256':c.sha256(c.canonical(request)),
                 'transport':{'api_timeout_seconds':None,'stream':None}}
            target=base/g/name/'input.json';mr.write(target,rec)
            if key in previews:
                original=previews[key][0]
                data['legacy_link_targets'][mr.relative(original)]=mr.relative(target)
                data['legacy_link_targets'][mr.relative(original.with_name(original.name.replace('.request.json','.prompt.txt')))]=mr.relative(target)
            continue
        for p,rec in records:
            op=p.with_name(p.name.replace('.input.json','.output.json'))
            state=read(op).get('status') if op.exists() else None
            suffix='' if rec['attempt']==1 else f"_retry{rec['attempt']-1:03}"
            if state and state!='ok':suffix+='_fail'
            folder=base/g/(name+suffix);folder.mkdir(parents=True,exist_ok=True)
            for source,target in [(p,folder/'input.json'),(op,folder/'output.json')]:
                if not source.exists():continue
                shutil.copyfile(source,target)
                files_map[mr.relative(source)]={'path':mr.relative(target),'sha256':c.sha256(source.read_bytes())}
        if key in previews:
            original=previews[key][0]
            first=records[0][0]
            target=files_map[mr.relative(first)]['path']
            data['legacy_link_targets'][mr.relative(original)]=target
            data['legacy_link_targets'][mr.relative(original.with_name(original.name.replace('.request.json','.prompt.txt')))]=target
    mr.write(base/mr.INFO,data)
    return data


def migrate(execute=False):
    if mr.mapping_path().exists():
        if execute:retire_sources(mr.mapping())
        return verify()
    batches,assignments,images=inventory()
    for base,items in batches:print(' →',base.relative_to(mr.root()),'来源：',','.join(x['run_id'] for x in items) or '下载记录')
    print('迁移范围：',len(assignments),'份档案、',len(images),'张图片；',len(batches),'个总批次')
    if not execute:return 0
    # Every resolved path must stay inside the named workspace; never traverse junctions.
    original={p:c.sha256(p.read_bytes()) for p in assignments}
    for p in [*assignments,*images]:
        if not p.resolve().is_relative_to(mr.root().resolve()):raise ValueError('历史文件越界')
        if any(parent.is_symlink() or getattr(parent,'is_junction',lambda:False)() for parent in [p,*p.parents] if parent!=c.ROOT and parent.is_relative_to(c.ROOT)):
            raise ValueError('迁移范围含链接目录')
    record={'version':3,'created_utc':c.now(),'aliases':{},'files':{},'batches':[]}
    # Originals remain untouched until every new record and archive is checked.
    for base,items in batches:
        if base.exists():raise ValueError('新批次目录已存在，停止：'+str(base))
        data=make_stage(base,items,record['files'])
        record['batches'].append(mr.relative(base))
        for kind,names in data['aliases'].items():
            for name in names:record['aliases'][kind+':'+name]=mr.relative(base)
        extra=[p for p,target in assignments.items() if target==base and mr.relative(p) not in record['files']]
        archive=base/'历史附档.zip'
        if extra:
            with ZipFile(archive,'w',ZIP_DEFLATED) as z:
                for p in sorted(extra):
                    member=mr.relative(p);z.writestr(member,p.read_bytes())
                    record['files'][member]={'archive':mr.relative(archive),'member':member,'sha256':original[p]}
        for old,new in data.get('legacy_link_targets',{}).items():
            if old in record['files']:record['files'][old]['link_path']=new
        if not items:
            data['download_records']=[mr.relative(p) for p in extra if read(p).get('started_utc')]
            data['task']='onet-download'
            data['download']=read(next(p for p in extra if read(p).get('started_utc')))
            mr.write(base/mr.INFO,data)
        mr.refresh(base)
    image_root=c.ROOT/'material_preparation/review/历史预览图片'
    for p in images:
        if not p.is_file():raise ValueError('未知图片目录项')
        target=image_root/p.name
        if target.exists() and target.read_bytes()!=p.read_bytes():raise ValueError('图片目标已存在且不同')
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
        record['files'][mr.relative(p)]={'path':mr.relative(target),'sha256':c.sha256(p.read_bytes())}
    # Verify every original byte before retiring any original path.
    for p,sha in original.items():
        item=record['files'][mr.relative(p)]
        if item.get('path'):raw=(c.ROOT/item['path']).read_bytes()
        else:
            with ZipFile(c.ROOT/item['archive']) as z:raw=z.read(item['member'])
        if c.sha256(raw)!=sha or c.sha256(p.read_bytes())!=sha:raise ValueError('迁移指纹不一致：'+str(p))
    mr.write(mr.mapping_path(),record)
    retire_sources(record)
    return verify()


def retire_sources(record):
    """A committed migration can resume retirement after a process interruption."""
    pending=[]
    for old,item in record['files'].items():
        source=c.ROOT/old
        if not source.resolve().is_relative_to(mr.root().resolve()):raise ValueError('原文件路径越界')
        if c.sha256(mr.legacy_bytes(source))!=item['sha256']:raise ValueError('新档案校验失败，保留旧文件')
        if source.exists():
            if c.sha256(source.read_bytes())!=item['sha256']:raise ValueError('旧文件迁移后被修改，停止清理')
            pending.append(source)
    for source in pending:source.unlink()
    for name in OLD:
        directory=mr.root()/name
        if not directory.exists():continue
        for p in sorted((x for x in directory.rglob('*') if x.is_dir()),key=lambda x:len(x.parts),reverse=True):
            if not any(p.iterdir()):p.rmdir()
        if not any(directory.iterdir()):directory.rmdir()


def verify():
    record=mr.mapping()
    count=0
    for old,item in record['files'].items():
        raw=mr.legacy_bytes(c.ROOT/old)
        if c.sha256(raw)!=item['sha256']:raise ValueError('历史档案指纹变化：'+old)
        if old.endswith('.output.json'):count+=1
    expected={'onet_download','occupation_generation','morality_generation'}
    actual={p.name for p in mr.root().iterdir() if p.is_dir()}
    if actual!=expected:raise ValueError('根目录分类不符：'+str(actual))
    print('核验通过：',len(record['files']),'份历史文件原始字节一致；API输出',count,'份；根目录仅3类。')
    return 0


def recover(destination,execute=False):
    destination=Path(destination).resolve()
    if destination.is_relative_to(c.ROOT.resolve()):raise ValueError('恢复副本必须放在项目外，避免重新混入旧目录')
    if destination.exists() and any(destination.iterdir()):raise ValueError('恢复目标必须为空目录或新目录')
    files=mr.mapping()['files']
    print('恢复原始布局副本至：',destination,'文件：',len(files))
    if not execute:return 0
    for old,item in files.items():
        target=(destination/old).resolve()
        if not target.is_relative_to(destination):raise ValueError('恢复路径越界')
        raw=mr.legacy_bytes(c.ROOT/old)
        if c.sha256(raw)!=item['sha256']:raise ValueError('恢复内容指纹不符')
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as f:f.write(raw)
    print('恢复副本完成；当前项目目录未改动。')
    return 0


def run(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true');p.add_argument('--verify',action='store_true')
    p.add_argument('--recover-to',type=Path,help='将完整旧布局恢复为项目外副本；默认只预览，加--execute才写入')
    args=p.parse_args(argv)
    if args.recover_to:return recover(args.recover_to,args.execute)
    return verify() if args.verify else migrate(args.execute)

if __name__=='__main__':
    import sys
    try:sys.exit(run())
    except Exception as exc:print(c.safe_error_message(exc),file=sys.stderr);sys.exit(2)
