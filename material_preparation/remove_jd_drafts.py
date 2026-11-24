"""Remove explicitly rejected JD drafts only; retain all original API archives."""
if __name__=='__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import argparse
from shared import common as c
from shared.batch import validate_run_id
from material_preparation.run_material_generation import immutable_json


def removal_plan(manifest):
    data=c.load_json(manifest)
    if data['task']!='jd': raise ValueError('仅支持JD草稿')
    planned=[]; seen=set()
    for item in data['materials']:
        slug=item['occupation']
        if slug in seen: raise ValueError('职业重复')
        seen.add(slug)
        expected=c.job_files(slug)['jd_draft'].resolve()
        target=(c.ROOT/item['draft']).resolve()
        if target!=expected or not target.is_relative_to((c.ROOT/'material_preparation/drafts/occupations').resolve()):
            raise ValueError('删除目标不属于该职业JD草稿')
        out=(c.ROOT/item['output']).resolve()
        if not out.is_relative_to((c.ROOT/'material_preparation/results/jd_generation').resolve()):
            raise ValueError('响应档案路径越界')
        response=c.load_json(out)
        if response['run_id']!=data['run_id'] or response['context']['occupation']!=slug or response['status']!='ok':
            raise ValueError('生成记录与职业或批次不一致')
        if target.exists():
            raw=target.read_bytes()
            if c.sha256(raw)!=item['draft_sha256'] or raw.decode('utf-8')!=response['answer']:
                raise ValueError('草稿已被修改，不删除：'+str(target))
            planned.append({'path':target,'sha256':c.sha256(raw),'output':item['output']})
    return planned


def run(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args(argv); validate_run_id(args.run_id)
    base=c.ROOT/'material_preparation/results/material_generation'/args.run_id
    plan=removal_plan(base/'generated_manifest.json')
    for item in plan: print('删除：' if args.execute else '预览删除：',item['path'].relative_to(c.ROOT))
    if args.execute and plan:
        log={'run_id':args.run_id,'removed_utc':c.now(),
             'files':[{'path':x['path'].relative_to(c.ROOT).as_posix(),'sha256':x['sha256'],'output':x['output']} for x in plan],
             'preserved':'O*NET sources, prompts, requests, raw responses, all attempts'}
        # Record the checked targets before deletion. No recursive operation.
        immutable_json(base/'draft_removal.json',log)
        for item in plan:
            if c.sha256(item['path'].read_bytes())!=item['sha256']:
                raise ValueError('删除前文件内容变化，停止')
        for item in plan: item['path'].unlink()
    print('已删除：' if args.execute else '计划删除：',len(plan),'份；原始调用档案保留。')
    return 0


if __name__=='__main__':
    import sys
    try: sys.exit(run())
    except Exception as error:
        print('失败：'+c.safe_error_message(error),file=sys.stderr); sys.exit(2)
