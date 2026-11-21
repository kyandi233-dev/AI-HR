from __future__ import annotations
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shlex
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TASK_TO_PROFILE = {'jd':'generation', 'resume':'generation', 'moral-generate':'generation',
                   'resume-review':'material_review', 'moral-check':'material_review', 'moral-relevance':'material_review',
                   'principles':'evaluation', 'baseline':'evaluation', 'abc':'evaluation',
                   'moral-review':'material_review'}
TASK_FOLDERS = {
    'principles':'experiments/exp_1_principles',
    'moral-check':'experiments/exp_2_material_evaluation',
    'moral-relevance':'experiments/exp_2_material_evaluation',
    'baseline':'experiments/exp_3_hiring', 'abc':'experiments/exp_3_hiring',
    **{task:'material_preparation' for task in ['jd','resume','moral-generate','resume-review','moral-review']},
}


FOUNDATIONS = ['care','fairness','loyalty','authority','sanctity','liberty']
FOUNDATION_CN = {'care':'关怀/伤害','fairness':'公平/欺骗','loyalty':'忠诚/背叛',
                 'authority':'权威/颠覆','sanctity':'神圣/纯洁','liberty':'自由/压迫'}

def task_folder(kind):
    return ROOT / TASK_FOLDERS[kind]


def load_settings(kind):
    return load_json(task_folder(kind)/'config/settings.json')


def occupations_file():
    return ROOT/'material_preparation/config/occupations.json'



def load_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))

def load_text(path: Path):
    if not path.is_file():
        raise ValueError(f'缺少必要文件：{path.relative_to(ROOT)}')
    s = path.read_text(encoding='utf-8').strip()
    if not s:
        raise ValueError(f'文件内容为空：{path.relative_to(ROOT)}')
    return s


def load_api_key():
    """Read the current terminal first, then the project's .env file."""
    value=os.environ.get('DEEPSEEK_API_KEY','').strip()
    if value: return value
    path=ROOT/'.env'
    if not path.is_file(): return ''
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        name,separator,value=line.removeprefix('export ').partition('=')
        if separator and name.strip()=='DEEPSEEK_API_KEY':
            tokens=shlex.split(value,comments=True)
            return tokens[0] if len(tokens)==1 else ''
    return ''

def canonical(obj: Any):
    return json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(',',':'))

def sha256(x: str | bytes):
    return hashlib.sha256(x.encode('utf-8') if isinstance(x,str) else x).hexdigest()

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='microseconds')

def safe_error_message(error):
    message=str(error)
    try: api_key=load_api_key()
    except (OSError,ValueError): api_key=''
    if api_key:
        message=message.replace(api_key,'[REDACTED]')
    return re.sub(r'(?i)(api key:\s*).*?(?=\s+is invalid)',r'\1[REDACTED]',message)

def sdk_version():
    try:
        return importlib.metadata.version('openai')
    except importlib.metadata.PackageNotFoundError:
        return None

def read_prompt(name):
    return load_text(ROOT/name)

def render(name: str, **kwargs):
    """Template uses Python str.format; escaped {{ }} are literal JSON braces."""
    return read_prompt(name).format(**kwargs)

def job_files(slug, materials_root=None):
    preparation = ROOT/'material_preparation'
    d = (Path(materials_root) if materials_root else preparation/'approved')/'occupations'/slug
    from material_preparation.onet_data import source_folder
    registry = load_json(occupations_file())
    source = source_folder(registry[slug]) if slug in registry else preparation/'sources/occupations'/slug/'onet'
    return {'profile':d/'onet/profile.txt', 'jd':d/'jd.txt', 'resumes':d/'resumes',
            'drafts':preparation/'drafts/occupations'/slug/'resumes',
            'jd_draft':preparation/'drafts/occupations'/slug/'jd.txt',
            'source':source,
            'setup':preparation/'sources/occupations'/slug/'job_setup.json'}

def read_job(slug, require_profile=True, require_jd=False, materials_root=None):
    paths=job_files(slug,materials_root)
    data = {'paths':paths}
    if require_profile:
        data['profile'] = load_text(paths['profile'])
    if require_jd:
        data['jd'] = load_text(paths['jd'])
    return data

def list_resumes(slug, source='approved', materials_root=None):
    folder=job_files(slug,materials_root)['resumes' if source=='approved' else 'drafts']
    files=sorted(folder.glob('R*.txt'))
    if not files:
        raise ValueError(f'没有可用简历：{folder.relative_to(ROOT)}；生成草案后请先人工审核。')
    return [(f.stem,load_text(f)) for f in files]

def list_moral_pairs(materials_root=None, source='approved'):
    base=Path(materials_root) if materials_root else ROOT/'material_preparation'/source
    files=sorted((base/'morality').glob('*.json'))
    if not files:
        raise ValueError('没有可用的道德配对材料：'+str(base/'morality/*.json'))
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
    project=Path(__file__).resolve().parents[1]
    files=[p for name in ['shared','experiments','material_preparation']
           for p in (project/name).rglob('*.py') if '__pycache__' not in p.parts]
    return sha256(canonical({p.relative_to(project).as_posix():sha256(p.read_bytes())
                             for p in sorted(files)}))
