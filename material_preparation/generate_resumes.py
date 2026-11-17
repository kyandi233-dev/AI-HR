"""根据职业资料与批准 JD 组装简历生成请求。"""
# 直接运行脚本时，将项目根目录加入模块查找路径。
if __name__=='__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from shared.common import read_job, render, new_task


def make_tasks(kind, args, occupations, config):
    info=read_job(args.occupation,require_jd=True)
    ret=[]
    for i in range(args.start_index,args.start_index+args.count):
        rid=f'R{i:02}'
        user=render('material_preparation/prompts/resume.txt',onet_profile=info['profile'],
            job_description=info['jd'],resume_id=rid,reference_date=config['reference_date'])
        ret.append(new_task(kind,rid,user,
                      {'occupation':args.occupation,'resume_id':rid},False))
    return ret


if __name__=='__main__':
    from shared.cli import task_main
    import sys
    sys.exit(task_main('resume'))
