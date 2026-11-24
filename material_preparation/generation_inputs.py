"""Lossless JSON input and strict, non-rewriting JD extraction."""
import json
from pathlib import Path
from shared import common as c
from material_preparation.onet_data import source_identity, directory_name


def read_occupation_data(slug):
    registry=c.load_json(c.occupations_file())
    info=registry[slug]
    paths=c.job_files(slug)
    identity=source_identity(paths['source'])
    raw=paths['structured'].read_bytes()
    data=json.loads(raw.decode('utf-8'))
    if data['registry']['onet_code']!=info['onet_code']:
        raise ValueError('职业编码与结构化资料不一致：'+slug)
    if data['source']['stored_html_sha256']!=identity['stored_html_sha256']:
        raise ValueError('结构化资料与原始网页不一致：'+slug)
    if not data.get('has_detail_sections'):
        raise ValueError('缺少详细职业资料：'+slug)
    # All keys, values, list order and source strings survive serialization.
    text=json.dumps(data,ensure_ascii=False,separators=(',',':'))
    return text, {'material_directory':directory_name(info),
                  'onet_code':info['onet_code'],
                  'structured_sha256':c.sha256(raw),
                  'source_html_sha256':identity['stored_html_sha256'],
                  'input_json_sha256':c.sha256(text)}


def project_jd_modules(data, modules):
    """Select entire modules, omit technical fields and exact duplicate displays only."""
    if len(modules)!=len(set(modules)):
        raise ValueError('JD 模块配置重复')
    selected={}; source_indexes={}
    for index,section in enumerate(data['sections']):
        sid=section['id']
        if sid in modules:
            if sid in selected: raise ValueError('来源栏目重复：'+sid)
            selected[sid]=section; source_indexes[sid]=index
    missing=set(modules)-set(selected)
    if missing: raise ValueError('来源缺少 JD 模块：'+', '.join(sorted(missing)))
    sections=[]; trace=[]
    for sid in modules:
        source=selected[sid]
        records=[]; mapping=[]
        for index,record in enumerate(source['records']):
            item={key:value for key,value in record.items() if key not in ('fields','links','source_key','text')}
            fields=[]
            equal_fields=[]
            for field in record.get('fields',[]):
                # Unknown fields survive, to avoid silently discarding future data.
                field=dict(field)
                if field.get('text_original')==field.get('value'):
                    field.pop('text_original',None)
                    equal_fields.append(field.get('name'))
                fields.append(field)
            if fields: item['fields']=fields
            originals=[f.get('text_original',f.get('value','')) for f in record.get('fields',[])]
            display=record.get('text','')
            if display and (not fields or display!=' '.join(originals)):
                item['text']=display
            # This is field cleanup, never a semantic merge of separate records.
            records.append(item)
            mapping.append({'input_record':index,'source_record':index,'source_order':record.get('order'),
                            'identical_text_original_omitted':equal_fields,
                            'duplicate_row_text_omitted':bool(display and 'text' not in item)})
        module={key:source[key] for key in ('id','title','record_count') if key in source}
        module['records']=records
        # Keep full section prose as a conservative fallback. Overview's records
        # contain navigation and do not cover the occupation description.
        if 'source_text' in source: module['source_text']=source['source_text']
        sections.append(module)
        trace.append({'module':sid,'source_section':source_indexes[sid],
                      'input_records':len(records),'source_records':len(source['records']),
                      'record_mapping':mapping,'source_text_retained':'source_text' in source})
    return {'occupation_name':data['registry']['onet_name'],
            'onet_code':data['registry']['onet_code'],'sections':sections},trace


def read_jd_occupation_data(slug):
    full,provenance=read_occupation_data(slug)
    path=c.ROOT/'material_preparation/config/jd_input_modules.json'
    config=c.load_json(path)
    projected,trace=project_jd_modules(json.loads(full),config['modules'])
    text=json.dumps(projected,ensure_ascii=False,separators=(',',':'))
    provenance.update(input_json_sha256=c.sha256(text),
                      jd_prompt_sha256=c.sha256((c.ROOT/'material_preparation/prompts/jd.txt').read_bytes()),
                      input_projection={'version':config['version'],
                                        'config_sha256':c.sha256(path.read_bytes()),
                                        'code_sha256':c.sha256(Path(__file__).read_bytes()),
                                        'full_json_characters':len(full),'input_json_characters':len(text),
                                        'excluded_modules':[s['id'] for s in json.loads(full)['sections'] if s['id'] not in config['modules']],
                                        'modules':trace})
    return text,provenance


MARKERS=('【依据记录开始】','【依据记录结束】','【岗位公告开始】','【岗位公告结束】')


def extract_jd(content):
    if any(content.count(m)!=1 for m in MARKERS):
        raise ValueError('JD 边界缺失或重复，保留原稿，停止提取')
    positions=[content.index(m) for m in MARKERS]
    if positions!=sorted(positions):
        raise ValueError('JD 边界顺序错误')
    a,b,d,e=positions
    if (content[:a]+content[b+len(MARKERS[1]):d]+content[e+len(MARKERS[3]):]).strip():
        raise ValueError('JD 区块外存在额外文字，停止提取')
    if not content[a+len(MARKERS[0]):b].strip():
        raise ValueError('依据记录为空')
    body=content[d+len(MARKERS[2]):e]
    if not body.strip() or any(title not in body for title in ('职位名称','岗位简介','工作职责','任职要求')):
        raise ValueError('岗位公告为空或缺少必要栏目')
    return body  # No strip, newline conversion, polishing or rewriting.


def review_flags(body):
    """Locate terms needing human review; never reject or rewrite the source."""
    requirements=body.split('任职要求',1)[-1]
    words=('诚信','合作','共情','沟通','谈判','协调','表达能力','注重细节','工作风格')
    return ['任职要求含“'+word+'”，请按提示词的排除规则人工核查，尚未判定通过。'
            for word in words if word in requirements]
