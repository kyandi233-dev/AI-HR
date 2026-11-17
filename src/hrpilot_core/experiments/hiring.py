"""Build independent tasks; no network calls here."""
import random
from ..common import read_job, list_resumes, read_prompt, list_moral_pairs, render, new_task, sha256


def make_tasks(kind, args, occupations, config):
    if kind in ('baseline','abc'):
        info=read_job(args.occupation,require_jd=True)
        resumes=list_resumes(args.occupation,'approved')
        rub=read_prompt('experiments/score_rubric.txt')
        pairs=list_moral_pairs() if kind=='abc' else []
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
                user=render('experiments/hiring_rating.txt',job_description=info['jd'],resume_text=rtxt,
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
