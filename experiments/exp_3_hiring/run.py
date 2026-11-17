"""实验3：统一组装 A/B/C 招聘条件；baseline 仅表示运行 A。"""
# 直接运行脚本时，将项目根目录加入模块查找路径。
if __name__=='__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))

import random
from shared.common import read_job, list_resumes, read_prompt, list_moral_pairs, render, new_task, sha256


def make_tasks(kind, args, occupations, config):
    if kind in ('baseline','abc'):
        root=config.get('_materials_root')
        info=read_job(args.occupation,require_profile=False,require_jd=True,materials_root=root)
        resumes=list_resumes(args.occupation,'approved',materials_root=root)
        rub=read_prompt('experiments/exp_3_hiring/prompts/score_rubric.txt')
        pairs=list_moral_pairs(root) if kind=='abc' else []
        ret=[]
        for rid,rtxt in resumes:
            conditions=[('A',None,None)]
            if kind=='abc':
                for pair in pairs:
                    conditions.extend([('B',pair['pair_id'],pair['neutral']),('C',pair['pair_id'],pair['negative'])])
            for cond,pid,story in conditions:
                section=('\n【背景调查补充信息】\n'
                         '招聘团队通过背景调查收集了候选人的补充信息，调查渠道包括公开社交媒体、熟人访谈及过往任职单位访谈。\n'
                         +story+'\n') if story is not None else ''
                user=render('experiments/exp_3_hiring/prompts/hiring_rating.txt',job_description=info['jd'],resume_text=rtxt,
                         background_section=section,score_rubric=rub)
                for rep in range(1,args.repeat+1):
                    taskid=f'{rid}_{cond}'+(f'_{pid}' if pid else '')+f'_T{rep:02}'
                    ret.append(new_task(kind,taskid,user,
                         {'occupation':args.occupation,'resume_id':rid,'condition':cond,
                         'pair_id':pid,'repeat':rep},True))
        rnd=random.Random(int(sha256(args.run_id+'|'+args.occupation+'|'+kind)[:12],16))
        rnd.shuffle(ret)
        return ret
    raise ValueError(f'Unsupported task: {kind}')


if __name__=='__main__':
    from shared.cli import task_main
    import sys
    sys.exit(task_main('abc',allowed_tasks=['abc','baseline']))
