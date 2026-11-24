"""Export independent reviewer workbooks; never write the master or original materials."""
if __name__=='__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from datetime import datetime,date
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from shared import common as c
from shared.batch import validate_run_id
from material_preparation.run_material_generation import is_selected
from material_preparation.review_material_links import read_review,external_links
from material_preparation.resume_inputs import generated_jd
from material_preparation.review_navigation import xml,encoded,Q
from material_preparation.reviewer_config import safe_name

OCCUPATION_HEADERS=['材料编号','职业','O*NET编码','材料类型','材料文件','职业资料',
                    '审核结论','问题类型','问题说明','审核日期','材料批次','原稿SHA256']
MORITY_HEADERS=['材料编号','道德主题','配对材料文件','审核结论','问题类型','问题说明','审核日期','材料版本','原稿SHA256']
MANUAL=['审核结论','问题类型','问题说明','审核日期']
FIRST_ROW=6
TECHNICAL={'材料批次','材料版本','原稿SHA256'}


def occupation_items(master,config):
    _,rows,_=read_review(master);registry=c.load_json(c.occupations_file())
    by_code={info['onet_code']:slug for slug,info in registry.items()}
    selected={row['O*NET Code'] for row in rows if is_selected(row.get('是否选用'))}
    base=c.ROOT/'material_preparation/results/material_generation'
    jd_manifest=c.load_json(base/config['jd_run_id']/'generated_manifest.json')
    resumes=c.load_json(base/config['resume_run_id']/'generated_manifest.json')
    if jd_manifest['task']!='jd' or resumes['task']!='resume':raise ValueError('材料批次类型不匹配')
    jd_items={item['occupation']:item for item in jd_manifest['materials']}
    output=[]
    def read_generated(item,run_id):
        path=(c.ROOT/item['draft']).resolve();record=(c.ROOT/item['output']).resolve()
        if not path.is_relative_to((c.ROOT/'material_preparation/drafts/occupations').resolve()):raise ValueError('材料路径越界')
        raw=path.read_bytes();response=c.load_json(record)
        if (c.sha256(raw)!=item['draft_sha256'] or response.get('status')!='ok'
            or response.get('run_id')!=run_id or response.get('answer')!=raw.decode('utf-8')
            or response['raw_response']['choices'][0]['message']['content']!=response['answer']):
            raise ValueError('原稿或成功生成记录不匹配')
        return path,raw
    for code in sorted(selected):
        slug=by_code.get(code)
        if slug not in jd_items:continue
        generated_jd(slug,config['jd_run_id'])
        jd,raw_jd=read_generated(jd_items[slug],config['jd_run_id'])
        source=c.job_files(slug)['source']/'职业资料.xlsx'
        info=registry[slug]
        output.append({'材料编号':code+'_JD','职业':info['onet_name'],'O*NET编码':code,'材料类型':'JD',
                       '材料批次':config['jd_run_id'],'原稿SHA256':c.sha256(raw_jd),
                       '_links':{'材料文件':str(jd),'职业资料':str(source)}})
        for item in sorted([x for x in resumes['materials'] if x['occupation']==slug],key=lambda x:x['task_id']):
            raw_path,raw=read_generated(item,config['resume_run_id'])
            output.append({'材料编号':code+'_'+item['task_id'],'职业':info['onet_name'],'O*NET编码':code,'材料类型':'简历',
                           '材料批次':config['resume_run_id'],'原稿SHA256':c.sha256(raw),
                           '_links':{'材料文件':str(raw_path),'职业资料':str(source)}})
    return output


def morality_items(config):
    output=[];seen=set()
    for pair_id in config['morality_pairs']:
        if not isinstance(pair_id,str) or not re.fullmatch(r'[A-Z]+_\d{3,}',pair_id) or pair_id in seen:
            raise ValueError('道德配对编号无效或重复')
        seen.add(pair_id);path=c.ROOT/'material_preparation/drafts/morality'/(pair_id+'.json')
        data=c.load_json(path)
        if data.get('pair_id')!=pair_id or data.get('foundation') not in c.FOUNDATIONS:
            raise ValueError('道德材料编号或主题无效')
        if any(not isinstance(data.get(key),str) or not data[key].strip() for key in ('neutral','negative')):
            raise ValueError('道德材料未生成完整中性/负面正文')
        sha=c.sha256(path.read_bytes())
        output.append({'材料编号':pair_id,'道德主题':c.FOUNDATION_CN[data['foundation']],
                       '材料版本':sha[:12],'原稿SHA256':sha,'_links':{'配对材料文件':str(path)}})
    return output


def identity(row):
    return (row['材料编号'],row.get('材料批次',row.get('材料版本')),row.get('原稿SHA256'))


def preserve_reviews(path,headers,items):
    previous={}
    if path.exists():
        w=load_workbook(path,read_only=False,data_only=False)
        try:
            if w.sheetnames!=['材料审核']:raise ValueError('已有个人表包含其他页，停止覆盖')
            s=w.active
            old_headers=[cell.value for cell in s[5]]
            migrated=[name for name in old_headers if name not in {'对应JD','审核文本SHA256'}]
            if old_headers!=headers and not (headers==OCCUPATION_HEADERS and migrated==headers):
                raise ValueError('已有个人表的列已修改，停止覆盖')
            for cells in s.iter_rows(min_row=FIRST_ROW):
                row=dict(zip(old_headers,[cell.value for cell in cells]))
                if not row.get('材料编号'):continue
                key=identity(row)
                if key in previous:raise ValueError('个人表材料重复')
                if any(cell.comment for cell in cells):raise ValueError('个人表含批注，停止覆盖以免遗漏')
                previous[key]={name:row.get(name) for name in MANUAL}
        finally:w.close()
    current={identity(row) for row in items}
    if len(current)!=len(items):raise ValueError('导出材料身份重复')
    for key,values in previous.items():
        if key not in current and any(value is not None for value in values.values()):
            raise ValueError('已审核的材料被取消选择或已换版；停止覆盖：'+str(key[0]))
    rows=[];links=[]
    for number,item in enumerate(items,FIRST_ROW):
        row={**item,**previous.get(identity(item),{})}
        for column,target in item['_links'].items():
            if not Path(target).is_file():raise ValueError('链接目标不存在：'+target)
            row[column]='打开'+('材料' if column in ('材料文件','配对材料文件') else column)
            links.append({'cell':get_column_letter(headers.index(column)+1)+str(number),'target':target})
        values=[]
        for name in headers:
            value=row.get(name)
            values.append({'date':value.isoformat()} if isinstance(value,(datetime,date)) else value)
        rows.append(values)
    return rows,links


def validate(path,payload):
    with ZipFile(path) as z:
        links=xml(z.read('xl/worksheets/sheet1.xml')).find(Q('hyperlinks'))
        if links is not None and not len(links):raise ValueError('空链接节点不兼容Excel')
    w=load_workbook(path,read_only=False,data_only=False)
    try:
        if w.sheetnames!=['材料审核']:raise ValueError('个人表页数错误')
        s=w.active
        if [cell.value for cell in s[5]]!=payload['headers']:raise ValueError('个人表表头错误')
        if payload.get('reviewer'):
            expected_title=payload['reviewer']+' · '+('职业材料审核' if payload['group']=='occupation' else '道德材料审核')
            if s['A2'].value!=expected_title:raise ValueError('个人表审核员标题需要更新')
        actual_ids=[s.cell(r,1).value for r in range(FIRST_ROW,s.max_row+1) if s.cell(r,1).value]
        if actual_ids!=[row[0] for row in payload['rows']]:raise ValueError('个人表材料范围不匹配')
        for n,name in enumerate(payload['headers'],1):
            if name in TECHNICAL and not s.column_dimensions[get_column_letter(n)].hidden:raise ValueError('版本记录列尚未隐藏')
        for r,expected in enumerate(payload['rows'],FIRST_ROW):
            for col,value in enumerate(expected,1):
                actual=s.cell(r,col).value
                if isinstance(value,dict) and 'date' in value:
                    if not isinstance(actual,(date,datetime)) or actual.isoformat()[:10]!=value['date'][:10]:raise ValueError('审核日期未保留')
                elif actual!=value:raise ValueError('个人表材料或审核值未保留')
        for link in payload['links']:
            actual=s[link['cell']].hyperlink
            if not actual or (Path(payload['review']).parent/actual.target).resolve()!=Path(link['target']).resolve():
                raise ValueError('个人表链接错误')
    finally:w.close()


def finish_workbook(source,target,spec):
    external_links(source,target,spec)
    with ZipFile(target) as z:parts={name:z.read(name) for name in z.namelist()}
    s=xml(parts['xl/worksheets/sheet1.xml']);cols=s.find(Q('cols'))
    for col in cols:
        if all(spec['headers'][n-1] in TECHNICAL for n in range(int(col.get('min')),int(col.get('max'))+1)):
            col.set('hidden','1')
    parts['xl/worksheets/sheet1.xml']=encoded(s)
    with ZipFile(target,'w',ZIP_DEFLATED) as z:
        for name,raw in parts.items():z.writestr(name,raw)


def run(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,default=c.ROOT/'material_preparation/config/human_review.json')
    p.add_argument('--master',type=Path,default=c.ROOT/'material_preparation/review/职业与材料审核.xlsx')
    p.add_argument('--execute',action='store_true')
    base=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node'
    p.add_argument('--node',type=Path,default=base/'bin/node.exe');p.add_argument('--node-modules',type=Path,default=base/'node_modules')
    args=p.parse_args(argv);config=c.load_json(args.config)
    from material_preparation.reviewer_config import load_team,reviewer_file
    config=load_team(config)
    for key in ('jd_run_id','resume_run_id'):validate_run_id(config[key])
    master=args.master.resolve();master_sha=c.sha256(master.read_bytes())
    groups={'occupation':(OCCUPATION_HEADERS,occupation_items(master,config)),
            'mority':(MORITY_HEADERS,morality_items(config))}
    if (master.parent/'morality_review_manifest.json').exists():
        groups.pop('mority')  # The source-grounded pool owns these review files; do not overwrite it.
    specs=[];protected={str(master):master_sha,str(args.config.resolve()):c.sha256(args.config.read_bytes())};personal_before={}
    for group,(headers,items) in groups.items():
        for row in items:
            for target in row['_links'].values():protected[target]=c.sha256(Path(target).read_bytes())
        for reviewer in config['reviewers']:
            target=reviewer_file(config,group,reviewer,master.parent/group)
            personal_before[str(target)]=c.sha256(target.read_bytes()) if target.exists() else None
            rows,links=preserve_reviews(target,headers,items)
            specs.append({'group':group,'reviewer':reviewer,'review':str(target),'headers':headers,'rows':rows,'links':links})
        print(group,': 每人',len(items),'项；',len(config['reviewers']),'份独立Excel')
    if not args.execute:print('仅预览；总表、正文和个人表均未写入。');return 0
    current=set()
    for spec in specs:
        if Path(spec['review']).exists():
            try:validate(Path(spec['review']),spec);current.add(spec['review'])
            except ValueError:pass
    if len(current)==len(specs):
        print('个人表的材料范围、链接及版本均相同；保留各人文件和已填审核内容，不重写Excel。');return 0
    work=Path(tempfile.mkdtemp(prefix='ai_hr_individual_reviews_'))
    subprocess.run(['cmd','/c','mklink','/J',str(work/'node_modules'),str(args.node_modules.resolve())],check=True,capture_output=True)
    builder=Path(__file__).with_suffix('.mjs');shutil.copy2(builder,work/builder.name)
    inp=work/'inputs.json';inp.write_text(json.dumps(specs,ensure_ascii=False),encoding='utf-8')
    result=subprocess.run([str(args.node),str(work/builder.name),str(inp),str(work)],capture_output=True,text=True,encoding='utf-8',errors='replace')
    if result.returncode:raise ValueError('个人表生成失败：'+result.stderr[-1800:])
    staged=[]
    for number,spec in enumerate(specs):
        candidate=work/(str(number)+'.xlsx')
        finish_workbook(work/(str(number)+'.authored.xlsx'),candidate,spec)
        validate(candidate,spec)
        if spec['review'] not in current:staged.append((Path(spec['review']),candidate))
    for path,sha in protected.items():
        if c.sha256(Path(path).read_bytes())!=sha:raise ValueError('制作期间总表或材料变化，停止写入')
    for path,sha in personal_before.items():
        target=Path(path);actual=c.sha256(target.read_bytes()) if target.exists() else None
        if actual!=sha:raise ValueError('制作期间个人审核表已被修改，停止覆盖：'+str(target))
    for target,candidate in staged:
        target.parent.mkdir(parents=True,exist_ok=True)
        temp=target.with_name('.'+target.stem+'.pending.xlsx');shutil.copyfile(candidate,temp);temp.replace(target)
    if c.sha256(master.read_bytes())!=master_sha:raise ValueError('总表发生变化')
    receipt={'master_sha256':master_sha,'config_sha256':c.sha256(args.config.read_bytes()),'script_sha256':c.sha256(Path(__file__).read_bytes()),
             'builder_sha256':c.sha256(builder.read_bytes()),'exported_utc':c.now(),'preview_directory':str(work),
             'source_files':protected,'files':[{'path':spec['review'],'sha256':c.sha256(Path(spec['review']).read_bytes()),'rows':len(spec['rows'])}
                                               for spec in specs]}
    (master.parent/'individual_review_manifest.json').write_text(c.canonical(receipt)+'\n',encoding='utf-8')
    print('已生成',len(specs),'份个人审核表；原总表与材料未改动。预览：',work)
    return 0


if __name__=='__main__':
    import sys
    try:sys.exit(run())
    except Exception as e:print(c.safe_error_message(e),file=sys.stderr);sys.exit(2)
