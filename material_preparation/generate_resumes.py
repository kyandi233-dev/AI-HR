"""根据职业资料与批准 JD 组装简历生成请求。"""
# 直接运行脚本时，将项目根目录加入模块查找路径。
if __name__=='__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from shared import common as c
from material_preparation.generation_inputs import read_jd_occupation_data
from material_preparation.resume_inputs import generated_jd


def make_tasks(kind, args, occupations, config):
    jd_run_id=getattr(args,'jd_run_id',None)
    if jd_run_id:
        jd,jd_provenance=generated_jd(args.occupation,jd_run_id)
    else:
        info=c.read_job(args.occupation,require_profile=False,require_jd=True,verbatim_jd=True)
        jd=info['jd']; jd_provenance={'jd_input_mode':'approved',
            'approved_jd_sha256':c.sha256(info['paths']['jd'].read_bytes())}
    data, provenance=read_jd_occupation_data(args.occupation)
    level_path=c.ROOT/'material_preparation/config/resume_levels.json'
    definitions=c.load_json(level_path)
    levels=getattr(args,'levels',None) or ['medium']
    if len(set(levels))!=len(levels) or any(level not in definitions['levels'] for level in levels):
        raise ValueError('简历水平必须为不重复的medium、low')
    ret=[]
    for offset,level in enumerate(levels):
        profile=definitions['levels'][level]
        for number in range(args.count):
            rid=f'R{args.start_index+offset*args.count+number:02}'
            timeline=dict(profile['timelines'][number%len(profile['timelines'])])
            timeline['major']=definitions['education_majors'].get(args.occupation,{}).get(level,'与岗位相关的本科专业' if level=='medium' else '与岗位仅部分相关的本科专业')
            writing_profile={k:v for k,v in profile.items() if k!='timelines'}
            user=c.render('material_preparation/prompts/resume.txt',occupation_data_json=data,
                job_description=jd,resume_id=rid,reference_date=config['reference_date'],
                ability_level_name=profile['name'],ability_profile=c.canonical(writing_profile),
                employment_plan=c.canonical(timeline))
            ret.append(c.new_task(kind,rid,user,
                {'occupation':args.occupation,'resume_id':rid,'ability_level':level,'level_replica':number+1,
                 'level_config_sha256':c.sha256(level_path.read_bytes()),
                 'resume_prompt_sha256':c.sha256((c.ROOT/'material_preparation/prompts/resume.txt').read_bytes()),
                 'employment_plan':timeline,
                 **jd_provenance,**provenance},False))
    return ret


if __name__=='__main__':
    from shared.cli import task_main
    import sys
    sys.exit(task_main('resume'))
