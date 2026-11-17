"""Build independent tasks; no network calls here."""
from ..common import read_job, load_json, render, new_task, FOUNDATIONS, FOUNDATION_CN


def make_tasks(kind, args, occupations, config):
    if kind=='jd':
        info=read_job(args.occupation)
        setup=load_json(info['paths']['setup'])
        if not setup.get('company_profile','').strip() or not setup.get('job_level','').strip():
            raise ValueError('先填写 job_setup.json 中的 company_profile 与 job_level')
        p=info['profile']
        user=render('generation/jd.txt',occupation_name=occupations[args.occupation]['onet_name'],
               onet_code=occupations[args.occupation]['onet_code'],
               job_title=setup['job_title'],company_profile=setup['company_profile'],
               job_level=setup['job_level'],additional_requirements=setup.get('additional_requirements','无'),
               onet_profile=p)
        return [new_task(kind,'JD01',user,{'occupation':args.occupation},False)]
    if kind=='resume':
        info=read_job(args.occupation,require_jd=True)
        if args.count>20:
            raise ValueError('单批新生成简历最多20份')
        ret=[]
        for i in range(args.start_index,args.start_index+args.count):
            rid=f'R{i:02}'
            user=render('generation/resume.txt',onet_profile=info['profile'],
                job_description=info['jd'],resume_id=rid,reference_date=config['reference_date'])
            ret.append(new_task(kind,rid,user,
                          {'occupation':args.occupation,'resume_id':rid},False))
        return ret
    if kind=='moral-generate':
        if args.foundation not in FOUNDATIONS:
            raise ValueError('请指定 --foundation care/fairness/loyalty/authority/sanctity/liberty')
        if args.count>20: raise ValueError('单次最多20组草案')
        ret=[]
        for i in range(args.start_index,args.start_index+args.count):
            pid=f'{args.foundation.upper()}_{i:03}'
            user=render('generation/morality.txt',foundation=FOUNDATION_CN[args.foundation],pair_id=pid)
            ret.append(new_task(kind,pid,user,
                    {'pair_id':pid,'foundation':args.foundation},True))
        return ret
    raise ValueError(f'Unsupported task: {kind}')
