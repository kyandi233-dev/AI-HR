"""Bind an explicitly named generated JD batch without fabricating Excel approval."""
from shared import common as c
from shared import material_results as mr
from shared.batch import validate_run_id
from material_preparation.generation_inputs import extract_jd
import re


def generated_jd(slug,run_id):
    validate_run_id(run_id)
    data=mr.load_manifest('jd',run_id)
    if data['task']!='jd' or not mr.run_matches('jd',run_id,data['run_id']):
        raise ValueError('指定批次不是JD生成记录')
    items=[item for item in data['materials'] if item['occupation']==slug]
    if len(items)!=1: raise ValueError('指定JD批次未唯一包含职业：'+slug)
    item=items[0]
    def local(name):
        p=mr.resolve_path(c.ROOT/name).resolve()
        if not p.is_relative_to(c.ROOT.resolve()): raise ValueError('JD档案路径越界')
        return p
    draft,inp,out=[local(item[k]) for k in ('draft','input','output')]
    if draft!=c.job_files(slug)['jd_draft'].resolve(): raise ValueError('JD草稿路径不匹配')
    raw=draft.read_bytes(); request=c.load_json(inp); response=c.load_json(out)
    if (c.sha256(raw)!=item['draft_sha256'] or raw.decode('utf-8')!=response.get('answer')
        or response.get('status')!='ok' or not mr.run_matches('jd',run_id,response['run_id'])
        or response['context']['occupation']!=slug or request['context']['occupation']!=slug
        or not mr.run_matches('jd',run_id,request['run_id']) or request['request_sha256']!=response['request_sha256']
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


SECTION_TITLES=('教育背景','工作经历','项目经历','专业技能')
BANNED_PLACEHOLDERS=('某某','××','某公司','某大学','某学院','某信息','某网络','某科技','XX公司','XX大学')


def section_slice(content, target):
    start=content.index(target)+len(target)
    ends=[content.index(h,start) for h in SECTION_TITLES if h!=target and content.find(h,start)!=-1]
    return content[start:min(ends)] if ends else content[start:]


def validate_resume_text(content,metadata):
    for title in SECTION_TITLES:
        if title not in content: raise ValueError('简历缺少栏目：'+title)
    if metadata['resume_id'] not in content[:100]: raise ValueError('简历编号不匹配')
    if any(label in content for label in ('中等水平','低水平','普通合格','能力较低')):
        raise ValueError('简历正文泄露水平标签')
    if any(token in content for token in BANNED_PLACEHOLDERS):
        raise ValueError('简历包含禁用模糊占位词（如某某/××）')
    plan=metadata['employment_plan']
    education=section_slice(content,'教育背景')
    work=section_slice(content,'工作经历')
    project=section_slice(content,'项目经历')
    if date_ranges(education)!=[plan['education_period']] or plan['major'] not in education:
        raise ValueError('教育日期或专业未遵守固定履历配置')
    if sorted(date_ranges(work))!=sorted(plan['work_periods']) or '至今' in work:
        raise ValueError('工作经历日期未遵守固定履历配置')
    if date_ranges(project)!=[plan['project_period']]:
        raise ValueError('项目日期未遵守固定履历配置')
