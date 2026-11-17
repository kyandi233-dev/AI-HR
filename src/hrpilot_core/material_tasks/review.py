"""Build independent tasks; no network calls here."""
import random
from ..common import read_job, list_resumes, list_moral_pairs, render, new_task, sha256


def make_tasks(kind, args, occupations, config):
    if kind=='resume-review':
        info=read_job(args.occupation,require_jd=True)
        ret=[]
        for rid, rtxt in list_resumes(args.occupation,args.source):
            user=render('validation/resume_review.txt',job_description=info['jd'],resume_text=rtxt)
            ret.append(new_task(kind,rid,user,
                                {'occupation':args.occupation,'resume_id':rid,'source':args.source},True))
        return ret
    if kind in ('moral-check','moral-relevance'):
        info=read_job(args.occupation,require_profile=False,require_jd=True) if kind=='moral-relevance' else None
        pairs=list_moral_pairs()
        items=[]
        for d in pairs:
            for type_ in ['neutral','negative']:
                items.append((d['pair_id'],type_,d[type_]))
        rnd=random.Random(int(sha256(args.run_id)[:12],16))
        rnd.shuffle(items)
        ret=[]
        for pid,kind_,story in items:
            if kind=='moral-relevance':
                user=render('validation/moral_relevance.txt',job_description=info['jd'],behavior_text=story)
                meta={'pair_id':pid,'background_type':kind_,'occupation':args.occupation}
            else:
                user=render('validation/moral_check.txt',behavior_text=story)
                meta={'pair_id':pid,'background_type':kind_}
            # Label and foundation are local metadata only, not sent to the judge.
            ret.append(new_task(kind,f'{pid}_{kind_}',user,meta,True))
        return ret
    raise ValueError(f'Unsupported task: {kind}')
