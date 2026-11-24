"""Individual immutable inputs and atomic outputs for each API attempt."""
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from . import common as c
from .api import api_request
from .validation import check_response


RESULT_NAMES={'principles':'principles','baseline':'a_only','abc':'abc',
              'moral-check':'morality','moral-relevance':'relevance',
              'resume-review':'resume_review','moral-review':'morality_review',
              'jd':'jd_generation','resume':'resume_generation','moral-generate':'morality_generation'}


def results_root(kind):
    return c.task_folder(kind)/'results'


def result_roots():
    return sorted({results_root(kind) for kind in c.TASK_TO_PROFILE})


def path_for(task, run_id):
    kind=task['task']; meta=task['metadata']
    folder=results_root(kind)
    if kind!='principles': folder=folder/RESULT_NAMES[kind]
    if meta.get('occupation'): folder=folder/meta.get('material_directory',meta['occupation'])
    return folder/run_id


def write_json(path, value, exclusive=False):
    path.parent.mkdir(parents=True,exist_ok=True)
    text=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
    if exclusive:
        with path.open('x',encoding='utf-8') as fp:
            fp.write(text); fp.flush(); os.fsync(fp.fileno())
        return
    fd,name=tempfile.mkstemp(prefix='.'+path.name,dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as fp:
            fp.write(text); fp.flush(); os.fsync(fp.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)


def records_dir(base):
    return base/'records'


def input_files(base, task_id=None):
    records=records_dir(base)
    files=list(records.glob('*.input.json')) if records.is_dir() else []
    files+=list(base.glob('*.input.json'))
    if task_id is not None:
        # Other workers may still be writing their input files.
        pattern=re.compile(re.escape(task_id)+r'_a[0-9]+\.input\.json')
        files=[p for p in files if pattern.fullmatch(p.name)]
    return sorted(files,key=lambda p:(c.load_json(p)['task_id'],c.load_json(p)['attempt']))


def request_for(task, settings):
    return {'task':task,'config':settings['profiles'][c.TASK_TO_PROFILE[task['task']]],
            'api_base_url':settings['api_base_url']}


def pending(task, settings, args):
    base=path_for(task,args.run_id)
    if (base/'records.jsonl').exists() or (base/'legacy').exists() and not (base/'batch.json').exists():
        raise ValueError('旧批次请先 migrate-results；新实验使用新的 run-id')
    files=input_files(base,task['task_id'])
    if not files: return True
    expected=c.sha256(c.canonical(request_for(task,settings)))
    if any(c.sha256(c.canonical(c.load_json(p)['request']))!=expected for p in files):
        raise ValueError('同一批次的输入已变化，请使用新 run-id')
    output=files[-1].with_name(files[-1].name.replace('.input.json','.output.json'))
    last=c.load_json(output) if output.exists() else {}
    if last.get('status')=='ok': return False
    return args.retry_failed


def save_draft(task, content, parsed):
    kind=task['task']; meta=task['metadata']
    if kind=='moral-generate':
        if meta.get('generation_protocol'):
            from material_preparation.morality_inputs import validate_generated
            validate_generated(parsed,task)
        if parsed.get('status')=='not_adaptable':
            return  # Keep the successful response and rejection reason, but no material draft.
        parsed['foundation']=meta['foundation']; parsed['pair_id']=meta['pair_id']
        path=c.ROOT/'material_preparation/drafts/morality'/(meta['pair_id']+'.json')
        if path.exists() and c.load_json(path)!=parsed:
            raise ValueError('已有不同的道德草稿；请先归档或变更编号')
        write_json(path,parsed)
    elif kind in ('jd','resume'):
        paths=c.job_files(meta['occupation'])
        path=paths['jd_draft'] if kind=='jd' else paths['drafts']/(meta['resume_id']+'.txt')
        path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists() and path.read_bytes().decode('utf-8')!=content:
            raise ValueError('已有同名不同草稿；请先归档或变更编号')
        path.write_bytes(content.encode('utf-8'))


def record_task(task, settings, args):
    if not re.fullmatch(r'[A-Za-z0-9_-]+',task['task_id']):
        raise ValueError('task_id 只能包含字母、数字、下划线、短横线')
    if not pending(task,settings,args): return 'skip'
    base=path_for(task,args.run_id)
    records=records_dir(base)
    files=input_files(base,task['task_id'])
    attempt=max((c.load_json(p)['attempt'] for p in files),default=0)+1
    stem=f"{task['task_id']}_a{attempt:02}"
    request=request_for(task,settings)
    identity={'run_id':args.run_id,'task_id':task['task_id'],'attempt':attempt,
              'task':task['task'],'stage':getattr(args,'stage','pilot'),
              'concurrency':getattr(args,'concurrency',1),
              'sequence':getattr(args,'sequence',None),'context':task['metadata']}
    input_data={**identity,'timestamp_utc':c.now(),'request':request,
                'transport':{'api_timeout_seconds':settings['api_timeout_seconds'],'stream':bool(settings.get('_stream'))},
                'request_sha256':c.sha256(c.canonical(request))}
    # Exclusive creation prevents two processes from charging the same attempt.
    write_json(records/(stem+'.input.json'),input_data,exclusive=True)
    result={**identity,'timestamp_utc':input_data['timestamp_utc'],'status':'interrupted',
            'request_sha256':input_data['request_sha256'],
            'prompt_sha256':c.sha256(c.canonical(task['messages'])),
            'python_version':sys.version.split()[0],'openai_sdk_version':c.sdk_version(),
            'api_timeout_seconds':settings['api_timeout_seconds'],
            'program_sha256':c.program_sha256(),'raw_response':None,'answer':None,'parsed':None,
            'validation_warnings':[]}
    out=records/(stem+'.output.json')
    write_json(out,result)
    try:
        response,kwargs=api_request(settings,task)
        raw=response.model_dump(mode='json')
        choices=response.choices
        content=choices[0].message.content if choices else None
        result.update(raw_response=raw,answer=content,api_kwargs=kwargs,
                      api_id=getattr(response,'id',None),returned_model=getattr(response,'model',None),
                      system_fingerprint=getattr(response,'system_fingerprint',None),usage=raw.get('usage'),
                      finish_reason=choices[0].finish_reason if choices else None)
        # Save the unmodified API response even if validation or draft saving fails.
        write_json(out,result)
        if result['finish_reason']!='stop':
            raise ValueError('finish_reason='+str(result['finish_reason']))
        if not content or not content.strip(): raise ValueError('空白响应')
        if task['task']=='resume' and task['metadata'].get('employment_plan'):
            from material_preparation.resume_inputs import validate_resume_text
            validate_resume_text(content,task['metadata'])
        parsed=check_response(task['task'],content) if task['json_mode'] else None
        if task['task']=='principles':
            returned_order=[key for key in parsed if key in ('task1','task2')]
            if returned_order!=list(task['metadata']['task_order']):
                result['validation_warnings'].append('任务键顺序与提示要求不同')
        save_draft(task,content,parsed)
        result.update(parsed=parsed,status='ok')
        print('OK',task['task_id'],f'attempt={attempt}')
    except Exception as exc:
        if getattr(exc,'partial_response',None) is not None:
            result['raw_response']=exc.partial_response.model_dump(mode='json')
            result['answer']=exc.partial_response.choices[0].message.content
        chain=[]; cause=exc.__cause__
        while cause is not None and len(chain)<4:
            chain.append({'type':type(cause).__name__,'message':c.safe_error_message(cause)[:1000]})
            cause=cause.__cause__
        result['error_chain']=chain
        result.update(status='error',error_type=type(exc).__name__,error_message=c.safe_error_message(exc)[:1000])
        print('ERROR',task['task_id'],result['error_message'][:200],file=sys.stderr)
    result['completed_utc']=c.now()
    write_json(out,result)
    return result['status']
