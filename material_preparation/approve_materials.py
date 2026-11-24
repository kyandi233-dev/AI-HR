"""Read Excel approvals; extract JD or copy resumes without rewriting source outputs."""
if __name__=='__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
from pathlib import Path
from shared import common as c
from shared.batch import validate_run_id
from material_preparation.generation_inputs import extract_jd
from material_preparation.run_material_generation import review_rows,is_selected,immutable_bytes,immutable_json
from material_preparation.review_schema import approval_value,is_approved


def approval_plan(review,manifest):
    rows=review_rows(review)
    registry=c.load_json(c.occupations_file())
    data=c.load_json(manifest)
    kind=data['task']
    if kind not in ('jd','resume'): raise ValueError('不支持的材料类型')
    planned=[]; seen=set()
    for item in data['materials']:
        slug=item['occupation']; key=(slug,item['task_id'])
        if key in seen: raise ValueError('生成记录重复')
        seen.add(key)
        row=rows.get(registry[slug]['onet_code'],{})
        column='JD' if kind=='jd' else '简历'+str(int(item['task_id'][1:]))
        if not is_selected(row.get('是否选用')) or not is_approved(approval_value(row,column)): continue
        def local(name):
            path=(c.ROOT/name).resolve()
            if not path.is_relative_to(c.ROOT.resolve()): raise ValueError('记录中的路径越界')
            return path
        draft,inp,out=[local(item[k]) for k in ('draft','input','output')]
        raw=draft.read_bytes()
        request=c.load_json(inp); response=c.load_json(out)
        if (c.sha256(raw)!=item['draft_sha256'] or response.get('status')!='ok'
            or response.get('answer')!=raw.decode('utf-8')
            or response.get('raw_response',{}).get('choices',[{}])[0].get('message',{}).get('content')!=response['answer']
            or request['context']['occupation']!=slug or request['task_id']!=item['task_id']
            or response['context']['occupation']!=slug or response['task_id']!=item['task_id']
            or request['run_id']!=data['run_id'] or response['run_id']!=data['run_id']
            or response['request_sha256']!=request['request_sha256']
            or c.sha256(c.canonical(request['request']))!=request['request_sha256']):
            raise ValueError('草稿或调用记录发生变化：'+slug)
        paths=c.job_files(slug)
        if kind=='resume' and request['context'].get('approved_jd_sha256',request['context'].get('jd_input_sha256'))!=c.sha256(paths['jd'].read_bytes()):
            raise ValueError('简历所依据的 JD 与当前批准版不同：'+slug)
        target=paths['jd'] if kind=='jd' else paths['resumes']/(item['task_id']+'.txt')
        content=extract_jd(raw.decode('utf-8')).encode('utf-8') if kind=='jd' else raw
        receipt={'occupation':slug,'task':kind,'task_id':item['task_id'],
                 'run_id':data['run_id'],'draft_sha256':c.sha256(raw),
                 'approved_sha256':c.sha256(content),'output':item['output'],
                 'output_sha256':c.sha256(out.read_bytes())}
        receipt_path=target.with_name('jd_approval.json' if kind=='jd' else target.stem+'_approval.json')
        for path,expected in [(target,content),(receipt_path,(c.canonical(receipt)+'\n').encode('utf-8'))]:
            if path.exists() and path.read_bytes()!=expected:
                raise ValueError('已批准材料不同，不覆盖：'+str(path))
        planned.append((target,content,receipt_path,receipt))
    return planned


def run(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--review',type=Path,default=c.ROOT/'material_preparation/review/职业与材料审核.xlsx')
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args(argv); validate_run_id(args.run_id)
    manifest=c.ROOT/'material_preparation/results/material_generation'/args.run_id/'generated_manifest.json'
    review_hash=c.sha256(args.review.read_bytes()); manifest_hash=c.sha256(manifest.read_bytes())
    plan=approval_plan(args.review,manifest)
    print('审核通过、可导入材料：',len(plan),'份')
    for path,_,_,_ in plan: print(path.relative_to(c.ROOT))
    if args.execute:
        if review_hash!=c.sha256(args.review.read_bytes()) or manifest_hash!=c.sha256(manifest.read_bytes()):
            raise ValueError('审核表或生成记录在读取期间变化，请重试')
        for path,content,receipt_path,receipt in plan:
            immutable_bytes(path,content); immutable_json(receipt_path,receipt)
        print('导入完成；原始草稿和调用记录保留。')
    else: print('仅预览；添加 --execute 后写入 approved。')
    return 0


if __name__=='__main__':
    import sys
    try: sys.exit(run())
    except Exception as error:
        print('失败：'+c.safe_error_message(error),file=sys.stderr); sys.exit(2)
