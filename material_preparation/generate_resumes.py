"""根据职业资料与批准 JD 组装简历生成请求。"""
# 直接运行脚本时，将项目根目录加入模块查找路径。
if __name__=='__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import json
from shared import common as c
from material_preparation.generation_inputs import read_jd_occupation_data
from material_preparation.resume_inputs import generated_jd


def compact_occupation_tasks(projected_json):
    data=json.loads(projected_json)
    lines=[]
    for section in data.get('sections',[]):
        if section.get('id')=='Tasks':
            for rec in section.get('records',[])[:10]:
                fields={f.get('name'):f.get('value','') for f in rec.get('fields',[])}
                task_text=fields.get('Task') or rec.get('text','')
                if task_text:
                    lines.append('- '+task_text)
    if not lines:
        overview=next((s.get('source_text','') for s in data.get('sections',[]) if s.get('id')=='Overview'),'')
        return overview[:600]
    return '\n'.join(lines)


def build_slot_assignment(definitions, slug, level, number, timeline):
    shared=definitions['shared_institutions']
    school=shared['schools'][0]
    work_periods=timeline['work_periods']
    companies=shared['companies'][:len(work_periods)]
    occ_slots=definitions.get('occupation_slots',{}).get(slug,{}).get(level)
    if occ_slots:
        slot=occ_slots[number%len(occ_slots)]
        roles=slot['roles']
        skill_focus=slot['skill_focus']
    else:
        roles=(['初级专员','业务专员'] if level=='medium' else ['业务实习生','基础支持助理'])
        skill_focus=('选取JD部分常规核心工具，不含加分项工具' if level=='medium'
                     else '基础办公软件与单一入门工具')
    work_lines=[
        f"- 工作经历{idx}：{roles[i]}｜{companies[i]}｜{work_periods[i]}"
        for idx,i in enumerate(range(len(work_periods)-1,-1,-1),1)
    ]
    return '\n'.join([
        f"- 毕业院校：{school}",
        f"- 本科专业：{timeline['major']}",
        f"- 教育期间：{timeline['education_period']}",
        *work_lines,
        f"- 项目期间：{timeline['project_period']}",
        f"- 技术范围：{skill_focus}",
    ]), {'school':school,'companies':companies,'roles':roles,'skill_focus':skill_focus}


def format_ability_profile(profile):
    return '\n'.join([
        f"- 教育：{profile['education']}",
        f"- 经历：{profile['experience']}",
        f"- 项目：{profile['accomplishments']}",
        f"- 技能：{profile['skills']}",
    ])


def make_tasks(kind, args, occupations, config):
    jd_run_id=getattr(args,'jd_run_id',None)
    if jd_run_id:
        jd,jd_provenance=generated_jd(args.occupation,jd_run_id)
    else:
        info=c.read_job(args.occupation,require_profile=False,require_jd=True,verbatim_jd=True)
        jd=info['jd']; jd_provenance={'jd_input_mode':'approved',
            'approved_jd_sha256':c.sha256(info['paths']['jd'].read_bytes())}
    data, provenance=read_jd_occupation_data(args.occupation)
    compact_tasks=compact_occupation_tasks(data)
    level_path=c.ROOT/'material_preparation/config/resume_levels.json'
    definitions=c.load_json(level_path)
    levels=getattr(args,'levels',None) or ['medium']
    if len(set(levels))!=len(levels) or any(level not in definitions['levels'] for level in levels):
        raise ValueError('简历水平必须为不重复的medium、low')
    ret=[]
    for offset,level in enumerate(levels):
        profile=definitions['levels'][level]
        for number in range(args.count):
            idx=args.start_index+offset*args.count+number
            rid=f'R{idx:02}'
            timeline=dict(profile['timelines'][number%len(profile['timelines'])])
            timeline['major']=definitions['education_majors'].get(args.occupation,{}).get(
                level,'与岗位相关的本科专业' if level=='medium' else '与岗位仅部分相关的本科专业')
            slot_text,slot_meta=build_slot_assignment(definitions,args.occupation,level,number,timeline)
            timeline.update(slot_meta)
            user=c.render('material_preparation/prompts/resume.txt',
                occupation_tasks=compact_tasks,
                job_description=jd,resume_id=rid,
                ability_level_name=profile['name'],
                ability_profile=format_ability_profile(profile),
                employment_plan=slot_text)
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
