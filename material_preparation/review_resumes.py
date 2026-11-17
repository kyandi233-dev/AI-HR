"""审核简历质量；结果属于材料准备，不是实验2能力评价。"""
# 直接运行脚本时，将项目根目录加入模块查找路径。
if __name__=='__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from shared.common import read_job, list_resumes, render, new_task


def make_tasks(kind, args, occupations, config):
    info=read_job(args.occupation,require_profile=False,require_jd=True)
    ret=[]
    for rid,rtxt in list_resumes(args.occupation,args.source):
        user=render('material_preparation/prompts/resume_review.txt',
                    job_description=info['jd'],resume_text=rtxt)
        ret.append(new_task(kind,rid,user,
                   {'occupation':args.occupation,'resume_id':rid,'source':args.source},True))
    return ret


if __name__=='__main__':
    from shared.cli import task_main
    import sys
    sys.exit(task_main('resume-review'))
