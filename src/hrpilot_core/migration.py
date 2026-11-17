"""Convert historical archives locally without resending any API request."""
import json
import shutil
from . import common as c
from .storage import results_root, path_for, write_json
from .exports import export_results


def read_jsonl(path):
    return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()] if path.exists() else []


def migrate_batch(source):
    old=c.load_json(source/'manifest.json')
    if (source/'records.jsonl').exists():
        inputs=read_jsonl(source/'requests.jsonl')
        outputs={(x['task_id'],x['attempt']):x for x in read_jsonl(source/'responses.jsonl')}
        records={(x['task_id'],x['attempt']):x for x in read_jsonl(source/'records.jsonl')}
    else:
        inputs=[]; outputs={}; records={}
        for d in sorted(p for p in source.iterdir() if p.is_dir()):
            attempt=0
            for folder in [*sorted((d/'failed_attempts').glob('*')),d]:
                if not (folder/'request.json').exists(): continue
                attempt+=1; key=(d.name,attempt)
                inputs.append({'task_id':d.name,'attempt':attempt,'request':c.load_json(folder/'request.json')})
                records[key]=c.load_json(folder/'record.json') if (folder/'record.json').exists() else {}
                records[key]['parsed']=c.load_json(folder/'parsed.json') if (folder/'parsed.json').exists() else None
                outputs[key]={'raw_response':c.load_json(folder/'raw_response.json') if (folder/'raw_response.json').exists() else None,
                              'answer':(folder/'answer.txt').read_text(encoding='utf-8') if (folder/'answer.txt').exists() else None}
    if not inputs: return
    target=path_for(inputs[0]['request']['task'],old['run_id'])
    if (target/'batch.json').exists():
        if target==source and c.load_json(target/'batch.json').get('historical_import'):
            _archive_originals(source,target)
            return
        raise ValueError('迁移目标已存在，请检查：'+str(target))
    originals={str(p.relative_to(source)):c.sha256(p.read_bytes()) for p in source.rglob('*')
               if p.is_file() and 'legacy' not in p.relative_to(source).parts
               and not p.name.endswith(('.input.json','.output.json'))
               and p.name not in ('batch.json','results.csv')}
    for item in inputs:
        key=(item['task_id'],item['attempt']); record=records.get(key,{})
        stem=f"{key[0]}_a{key[1]:02}"
        # Preserve historical request/response objects and metadata verbatim.
        input_data={**item,'run_id':old['run_id'],'timestamp_utc':record.get('timestamp_utc')}
        output={**record,**outputs.get(key,{}),'run_id':old['run_id'],
                'task_id':key[0],'attempt':key[1],
                'status':record.get('status','interrupted'),'parsed':record.get('parsed')}
        ip=target/(stem+'.input.json'); op=target/(stem+'.output.json')
        for path,value in [(ip,input_data),(op,output)]:
            if path.exists() and c.load_json(path)!=value: raise ValueError('迁移内容冲突：'+str(path))
            if not path.exists(): write_json(path,value,exclusive=True)
        if c.load_json(ip)['request']!=item['request'] or c.load_json(op)!=output:
            raise ValueError('迁移校验失败；原文件未移除')
    manifest={'format_version':2,'task':old['task'],'run_id':old['run_id'],
              'stage':c.load_json(source/'run_summary.json').get('stage','unknown') if (source/'run_summary.json').exists() else 'unknown',
              'historical_import':True,'planned_requests':len({x['task_id'] for x in inputs}),
              'original_file_sha256':originals,'original_manifest':old}
    write_json(target/'batch.json',manifest,exclusive=True)
    _archive_originals(source,target,originals)
    print('迁移并逐条核对',len(inputs),'次尝试：',target)


def _archive_originals(source,target,originals=None):
    originals=originals or c.load_json(target/'batch.json')['original_file_sha256']
    for name,digest in originals.items():
        origin=source/name; dest=target/'legacy'/name
        if dest.exists():
            if c.sha256(dest.read_bytes())!=digest: raise ValueError('历史存档冲突')
            continue
        if c.sha256(origin.read_bytes())!=digest: raise ValueError('原文件发生变化，停止归档')
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.move(str(origin),str(dest))


def migrate_results():
    sources=list(results_root().rglob('manifest.json'))
    for path in sorted(sources):
        if 'legacy' in path.relative_to(results_root()).parts: continue
        migrate_batch(path.parent)
    # The former mixed-task CSV was derived; originals remain in Git history.
    old=results_root()/'all_results.csv'
    if old.exists(): old.unlink()
    export_results()
