"""根据职业来源与岗位设定组装 JD 生成请求。"""
# 直接运行脚本时，将项目根目录加入模块查找路径。
if __name__=='__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from shared.common import read_job, load_json, render, new_task


def make_tasks(kind, args, occupations, config):
    info=read_job(args.occupation)
    setup=load_json(info['paths']['setup'])
    if not setup.get('company_profile','').strip() or not setup.get('job_level','').strip():
        raise ValueError('先填写 job_setup.json 中的 company_profile 与 job_level')
    p=info['profile']
    user=render('material_preparation/prompts/jd.txt',occupation_name=occupations[args.occupation]['onet_name'],
           onet_code=occupations[args.occupation]['onet_code'],
           job_title=setup['job_title'],company_profile=setup['company_profile'],
           job_level=setup['job_level'],additional_requirements=setup.get('additional_requirements','无'),
           onet_profile=p)
    return [new_task(kind,'JD01',user,{'occupation':args.occupation},False)]


if __name__=='__main__':
    from shared.cli import task_main
    import sys
    sys.exit(task_main('jd'))
