"""Freeze scientific inputs separately from human-facing exports."""
import re
from pathlib import Path
from . import common as c
from .storage import path_for, write_json


def validate_run_id(run_id):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',run_id):
        raise ValueError('run-id 使用字母、数字、下划线或短横线，以字母或数字开头')


def manifest_for(tasks,settings,args):
    protocol={name:c.sha256((Path(__file__).parent/name).read_bytes())
              for name in ['api.py','storage.py','validation.py']}
    return {'format_version':2,'task':args.task,'run_id':args.run_id,'stage':args.stage,
            'occupations':args.occupations,'settings':settings['profiles'][c.TASK_TO_PROFILE[args.task]],
            'api_base_url':settings['api_base_url'],'reference_date':settings['reference_date'],
            'protocol':protocol,'planned_requests':len(tasks),
            'concurrency':getattr(args,'concurrency',1),
            'materials_snapshot':settings.get('_materials_snapshot'),
            'trials':[{'task_id':t['task_id'],'occupation':t['metadata'].get('occupation'),
                       'sha256':c.sha256(c.canonical(t))} for t in tasks]}


def freeze(tasks,settings,args):
    from . import material_results as mr
    if tasks and tasks[0]['task'] in mr.KINDS:
        kind=tasks[0]['task'];base=mr.batch_root(kind,args.run_id,True)
        if not mr.is_batch(base) or kind not in mr.info(base).get('plans',{}):
            mr.prepare(tasks,settings,args)
        return
    manifest=manifest_for(tasks,settings,args)
    bases={path_for(t,args.run_id) for t in tasks}
    # Check every destination before creating any new manifests.
    for base in bases:
        path=base/'batch.json'
        if (base/'records.jsonl').exists():
            raise ValueError('旧数据请先 migrate-results；本次未发送请求')
        if path.exists():
            # Source digests and worker count describe the run; trial inputs define the batch.
            comparable=lambda value:{k:v for k,v in value.items() if k not in ('protocol','concurrency')}
            if comparable(c.load_json(path))!=comparable(manifest):
                raise ValueError('批次计划/输入/参数已变化，请使用新 run-id')
    for base in bases:
        path=base/'batch.json'
        if not path.exists(): write_json(path,manifest,exclusive=True)
