"""Archive superseded generated resume text verbatim before a new controlled batch."""
if __name__=='__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
from shared import common as c
from shared import material_results as mr
from shared.batch import validate_run_id
from material_preparation.run_material_generation import immutable_json


def run(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-id',required=True); p.add_argument('--execute',action='store_true')
    args=p.parse_args(argv); validate_run_id(args.run_id)
    root=mr.batch_root('resume',args.run_id)
    m=mr.load_manifest('resume',args.run_id)
    if m['task']!='resume': raise ValueError('仅归档简历草稿')
    plan=[]
    for item in m['materials']:
        src=(c.ROOT/item['draft']).resolve(); out=mr.resolve_path(c.ROOT/item['output']).resolve()
        if not out.is_relative_to((mr.root()/'occupation_generation').resolve()) or c.load_json(out)['task']!='resume':
            raise ValueError('响应路径越界')
        if src!=(c.job_files(item['occupation'])['drafts']/(item['task_id']+'.txt')).resolve():
            raise ValueError('草稿路径不匹配')
        dest=out.parent/'原始草稿.txt'
        if not src.exists():
            if dest.exists() and c.sha256(dest.read_bytes())==item['draft_sha256']: continue
            raise ValueError('草稿及归档均不存在')
        raw=src.read_bytes(); response=c.load_json(out)
        if c.sha256(raw)!=item['draft_sha256'] or raw.decode('utf-8')!=response['answer']:
            raise ValueError('草稿被修改，不归档')
        if dest.exists(): raise ValueError('归档目标已存在，不覆盖')
        plan.append((src,dest,item['draft_sha256']))
    for src,dest,_ in plan: print('归档',src.relative_to(c.ROOT),'→',dest.relative_to(c.ROOT))
    if args.execute and plan:
        data=mr.info(root)
        data.setdefault('draft_archivals',[]).append({'run_id':args.run_id,'archived_utc':c.now(),
            'files':[{'original':s.relative_to(c.ROOT).as_posix(),'archive':d.relative_to(c.ROOT).as_posix(),'sha256':sha} for s,d,sha in plan]})
        mr.write(root/mr.INFO,data)
        for src,dest,sha in plan:
            if c.sha256(src.read_bytes())!=sha: raise ValueError('归档前内容变化')
            dest.parent.mkdir(parents=True,exist_ok=True)
            src.rename(dest)
            if c.sha256(dest.read_bytes())!=sha: raise ValueError('归档后摘要不一致')
    print('已归档' if args.execute else '仅预览',len(plan),'份，原始响应保留。')
    return 0


if __name__=='__main__':
    import sys
    try: sys.exit(run())
    except Exception as e: print(c.safe_error_message(e),file=sys.stderr); sys.exit(2)
