"""Bind an explicitly named generated JD batch without fabricating Excel approval."""
from shared import common as c
from shared.batch import validate_run_id
from material_preparation.generation_inputs import extract_jd
import re


def generated_jd(slug,run_id):
    validate_run_id(run_id)
    manifest=c.ROOT/'material_preparation/results/material_generation'/run_id/'generated_manifest.json'
    data=c.load_json(manifest)
    if data['task']!='jd' or data['run_id']!=run_id:
        raise ValueError('指定批次不是JD生成记录')
    items=[item for item in data['materials'] if item['occupation']==slug]
    if len(items)!=1: raise ValueError('指定JD批次未唯一包含职业：'+slug)
    item=items[0]
    def local(name):
        p=(c.ROOT/name).resolve()
        if not p.is_relative_to(c.ROOT.resolve()): raise ValueError('JD档案路径越界')
        return p
    draft,inp,out=[local(item[k]) for k in ('draft','input','output')]
    if draft!=c.job_files(slug)['jd_draft'].resolve(): raise ValueError('JD草稿路径不匹配')
    raw=draft.read_bytes(); request=c.load_json(inp); response=c.load_json(out)
    if (c.sha256(raw)!=item['draft_sha256'] or raw.decode('utf-8')!=response.get('answer')
        or response.get('status')!='ok' or response['run_id']!=run_id
        or response['context']['occupation']!=slug or request['context']['occupation']!=slug
        or request['run_id']!=run_id or request['request_sha256']!=response['request_sha256']
        or request['request_sha256']!=c.sha256(c.canonical(request['request']))
        or response['raw_response']['choices'][0]['message']['content']!=response['answer']):
        raise ValueError('指定JD原稿或调用记录已变化：'+slug)
    body=extract_jd(raw.decode('utf-8'))
    return body,{'jd_input_mode':'generated_batch','jd_run_id':run_id,
                 'jd_input_sha256':c.sha256(body),'jd_draft_sha256':c.sha256(raw),
                 'jd_output':item['output'],'jd_output_sha256':c.sha256(out.read_bytes())}


def date_ranges(text):
    return [f'{int(y):04}.{int(m):02}—{int(z):04}.{int(n):02}' for y,m,z,n in
            re.findall(r'(\d{4})[.年/-](\d{1,2})月?\s*[—–－至-]\s*(\d{4})[.年/-](\d{1,2})月?',text)]


def validate_resume_text(content,metadata):
    for title in ('教育背景','工作经历','项目经历','专业技能'):
        if title not in content: raise ValueError('简历缺少栏目：'+title)
    if metadata['resume_id'] not in content[:100]: raise ValueError('简历编号不匹配')
    if any(label in content for label in ('中等水平','低水平','普通合格','能力较低')):
        raise ValueError('简历正文泄露水平标签')
    plan=metadata['employment_plan']
    education=content.split('教育背景',1)[1].split('工作经历',1)[0]
    work=content.split('工作经历',1)[1].split('项目经历',1)[0]
    project=content.split('项目经历',1)[1].split('专业技能',1)[0]
    if date_ranges(education)!=[plan['education_period']] or plan['major'] not in education:
        raise ValueError('教育日期或专业未遵守固定履历配置')
    if sorted(date_ranges(work))!=sorted(plan['work_periods']) or '至今' in work:
        raise ValueError('工作经历日期未遵守固定履历配置')
    if date_ranges(project)!=[plan['project_period']]:
        raise ValueError('项目日期未遵守固定履历配置')
