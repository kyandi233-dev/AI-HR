from __future__ import annotations
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
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

def safe_error_message(error):
    message=str(error)
    api_key=os.environ.get('DEEPSEEK_API_KEY','').strip()
    if api_key:
        message=message.replace(api_key,'[REDACTED]')
    return re.sub(r'(?i)(api key:\s*).*?(?=\s+is invalid)',r'\1[REDACTED]',message)

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
    d = ROOT/'materials'/'occupations'/slug
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
    files=sorted((ROOT/'materials'/'morality'/'approved').glob('*.json'))
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


def program_sha256():
    """Provenance only; editing CSV presentation does not invalidate a batch."""
    folder=Path(__file__).parent
    return sha256(canonical({str(p.relative_to(folder)):sha256(p.read_bytes())
                             for p in sorted(folder.rglob('*.py'))}))
