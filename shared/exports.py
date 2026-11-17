"""Readable per-batch CSVs and one aggregate per task type."""
import csv
from . import common as c
from .storage import results_root, result_roots, input_files

NAMES={'principles':'principles','baseline':'hiring_a_only','abc':'hiring_abc',
       'moral-check':'moral_check','moral-relevance':'moral_relevance',
       'resume-review':'resume_review','jd':'jd_generation',
       'resume':'resume_generation','moral-generate':'moral_generation','moral-review':'morality_review'}
IDENTITY=['run_id','stage','task','task_id','attempt','sequence','status','timestamp_utc',
          'occupation','condition','repeat','resume_id','pair_id','background_type',
          'materials_version','materials_sha256']
MODEL=['requested_model','returned_model','temperature','thinking','max_tokens','finish_reason',
       'prompt_tokens','completion_tokens','total_tokens','error_message','concurrency','validation_warnings']
PRINCIPLE=['priority','weight_ability','weight_morality','importance_ability','importance_morality','reason']


def flatten(value,prefix=''):
    row={}
    for key,item in value.items():
        name=prefix+key
        if isinstance(item,dict): row.update(flatten(item,name+'_'))
        elif isinstance(item,list): row[name]='; '.join(str(v) for v in item)
        else: row[name]=item
    return row


def batch_rows(base):
    manifest=c.load_json(base/'batch.json')
    rows=[]
    for path in input_files(base):
        inp=c.load_json(path)
        out_path=path.with_name(path.name.replace('.input.json','.output.json'))
        out=c.load_json(out_path) if out_path.exists() else {'status':'interrupted'}
        request=inp['request']; task=request['task']; profile=request['config']
        meta=task['metadata']; usage=out.get('usage') or {}
        row={'run_id':manifest['run_id'],'stage':manifest.get('stage','unknown'),
             'task':task['task'],'task_id':inp['task_id'],'attempt':inp['attempt'],
             'sequence':inp.get('sequence'),'status':out['status'],
             'timestamp_utc':out.get('timestamp_utc',inp.get('timestamp_utc')),
             'requested_model':profile['model'],'returned_model':out.get('returned_model'),
             'temperature':profile.get('temperature'),'thinking':profile['thinking'],
             'max_tokens':profile['max_tokens'],'finish_reason':out.get('finish_reason'),
             'error_message':out.get('error_message'),
             'concurrency':inp.get('concurrency'),
             'validation_warnings':'; '.join(out.get('validation_warnings',[])),**meta,
             **{k:usage.get(k) for k in ['prompt_tokens','completion_tokens','total_tokens']}}
        # Only validated successful answers enter analysis columns.
        if out['status']=='ok': row.update(flatten(out.get('parsed') or {}))
        rows.append(row)
    return sorted(rows,key=lambda r:(r.get('sequence') or 0,r['task_id'],r['attempt']))


def write_csv(path,rows,kind):
    path.parent.mkdir(parents=True,exist_ok=True)
    results=([f'{q}_{k}' for q in ['task1','task2'] for k in PRINCIPLE] if kind=='principles'
             else sorted(set().union(*(r.keys() for r in rows))-set(IDENTITY+MODEL)-{'definition_order','task_order'}))
    fields=IDENTITY+MODEL+results
    with path.open('w',encoding='utf-8-sig',newline='') as fp:
        writer=csv.DictWriter(fp,fieldnames=fields,extrasaction='ignore',lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)
    print('导出',len(rows),'条调用尝试：',path.relative_to(c.ROOT))


def export_results(task_filter=None):
    by_kind={}
    paths=sorted(path for root in result_roots() for path in root.rglob('batch.json'))
    for path in paths:
        if 'legacy' in path.relative_to(c.ROOT).parts: continue
        manifest=c.load_json(path); kind=manifest['task']
        if task_filter and kind!=task_filter: continue
        rows=batch_rows(path.parent)
        write_csv(path.parent/'results.csv',rows,kind)
        by_kind.setdefault(kind,[]).extend(rows)
    for kind,rows in by_kind.items():
        name=NAMES[kind]
        # All occupations and batches of this task, never unrelated tasks.
        write_csv(results_root(kind)/(name+'_all_results.csv'),rows,kind)
