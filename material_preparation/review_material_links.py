"""Create paired file links and inclusion columns in the existing one-sheet review file."""
if __name__=='__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import argparse
import csv
import json
import os
import shutil
import subprocess
import tempfile
from datetime import date,datetime
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from xml.etree import ElementTree as E
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from shared import common as c
from shared import material_results as mr
from shared.batch import validate_run_id
from material_preparation.review_schema import HEADERS,LINK_COLUMNS,approval_value
from material_preparation.review_navigation import xml,encoded,Q,REL,PKG
from material_preparation.resume_inputs import generated_jd
from material_preparation.occupation_review_layout import workbook_jump_formula

OLD_LINKS={'JD原稿','中等1（R01）','中等2（R02）','低1（R03）','低2（R04）'}


def read_review(path):
    w=load_workbook(path,read_only=False,data_only=False)
    try:
        if set(w.sheetnames)-{'职业汇总','简历审核','JD原文'}:
            raise ValueError('发现其他工作表，停止重建以免丢失用户内容')
        s=w['职业汇总']; headers=[cell.value for cell in s[1]]; rows=[]; seen=set()
        for cells in s.iter_rows(min_row=2):
            row=dict(zip(headers,[cell.value for cell in cells])); code=row.get('O*NET Code')
            if not code: continue
            if code in seen: raise ValueError('职业编码重复')
            seen.add(code)
            if any(cell.comment for cell in cells): raise ValueError('发现单元格批注，停止重建以免遗漏')
            rows.append(row)
        extra=[name for name in headers if name and name not in HEADERS and name not in OLD_LINKS
               and name not in {'人工分类','简历1','简历2','简历3','简历4'}]
        return headers,rows,extra
    finally:w.close()


def model(review,run_id,jd_run_id):
    _,old_rows,extra=read_review(review)
    headers=HEADERS+extra; registry=c.load_json(c.occupations_file())
    by_code={info['onet_code']:slug for slug,info in registry.items()}
    manifest=mr.load_manifest('resume',run_id)
    if manifest['task']!='resume': raise ValueError('指定批次不是简历')
    generated={}; sources={}
    for item in manifest['materials']:
        slug=item['occupation']; rid=item['task_id']; key=(slug,rid)
        if key in generated: raise ValueError('生成记录重复')
        raw_path=(c.ROOT/item['draft']).resolve()
        if raw_path!=(c.job_files(slug)['drafts']/(rid+'.txt')).resolve(): raise ValueError('草稿路径不匹配')
        raw=raw_path.read_bytes(); out_path=(c.ROOT/item['output']).resolve(); response=c.load_json(out_path)
        if (c.sha256(raw)!=item['draft_sha256'] or raw.decode('utf-8')!=response.get('answer')
            or response.get('status')!='ok' or not mr.run_matches('resume',run_id,response.get('run_id'))
            or response['raw_response']['choices'][0]['message']['content']!=response['answer']):
            raise ValueError('简历原文或响应记录变化')
        generated[key]={'target':str(raw_path),'sha256':c.sha256(raw)}
        for path in [raw_path,out_path,c.ROOT/item['input']]:sources[str(path)]=c.sha256(path.read_bytes())
    rows=[]; links=[]; removed={}
    for row_number,old in enumerate(old_rows,2):
        code=old['O*NET Code']; slug=by_code.get(code)
        row={key:old.get(key) for key in headers}
        if slug and '职业资料文件' in headers:
            wb_target=c.job_files(slug)['source']/'职业资料.xlsx'
            if wb_target.is_file():
                row['职业资料文件']=workbook_jump_formula(wb_target,review)
        for material in ['JD']+[f'简历{i}' for i in range(1,5)]:row[material+'是否纳入']=approval_value(old,material)
        if old.get('人工分类') is not None:removed[code]=old['人工分类']
        for key in LINK_COLUMNS:row[key]=None
        if any(job==slug for job,_ in generated):
            generated_jd(slug,jd_run_id)
            jd=c.job_files(slug)['jd_draft']; sources[str(jd)]=c.sha256(jd.read_bytes());row['JD']='打开JD原稿'
            links.append({'cell':get_column_letter(headers.index('JD')+1)+str(row_number),'target':str(jd)})
            for number,column in enumerate(LINK_COLUMNS[1:],1):
                item=generated.get((slug,f'R{number:02}'))
                if item is None:continue
                row[column]='打开简历'+str(number)
                links.append({'cell':get_column_letter(headers.index(column)+1)+str(row_number),'target':item['target']})
        for key in headers:
            if isinstance(row.get(key),(datetime,date)):row[key]={'date':row[key].isoformat()}
        rows.append([row.get(key) for key in headers])
    return {'headers':headers,'rows':rows,'links':links,'sources':sources,
            'removed_classifications':removed,'review':str(review),'run_id':run_id,'jd_run_id':jd_run_id}


def external_links(book_path,target,payload):
    with ZipFile(book_path) as z:parts={n:z.read(n) for n in z.namelist()}
    sheet=xml(parts['xl/worksheets/sheet1.xml']);links=sheet.find(Q('hyperlinks'))
    if links is None and payload['links']:
        links=E.Element(Q('hyperlinks'))
        following={'printOptions','pageMargins','pageSetup','headerFooter','rowBreaks','colBreaks','drawing','legacyDrawing','tableParts','extLst'}
        index=next((i for i,x in enumerate(sheet) if x.tag.rsplit('}',1)[-1] in following),len(sheet));sheet.insert(index,links)
    rel_path='xl/worksheets/_rels/sheet1.xml.rels'
    rels=xml(parts[rel_path]) if rel_path in parts else E.Element('{'+PKG+'}Relationships')
    for n,item in enumerate(payload['links'],1):
        rid='materialLink'+str(n)
        address=os.path.relpath(item['target'],start=Path(payload['review']).parent).replace('\\','/')
        E.SubElement(links,Q('hyperlink'),{'ref':item['cell'],'{'+REL+'}id':rid})
        E.SubElement(rels,'{'+PKG+'}Relationship',{'Id':rid,'Type':REL+'/hyperlink','Target':address,'TargetMode':'External'})
    sheet.find(Q('sheetViews'))[0].set('zoomScale','90')
    for rule in sheet.iter(Q('dataValidation')):rule.set('allowBlank','1')
    parts['xl/worksheets/sheet1.xml']=encoded(sheet);parts[rel_path]=encoded(rels)
    with ZipFile(target,'w',ZIP_DEFLATED) as z:
        for name,raw in parts.items():z.writestr(name,raw)


def validate(path,payload):
    w=load_workbook(path,read_only=False,data_only=False)
    try:
        if w.sheetnames!=['职业汇总']:raise ValueError('总表不应再嵌入正文页')
        s=w.active
        if [cell.value for cell in s[1]]!=payload['headers']:raise ValueError('表头不匹配')
        for row_no,row in enumerate(payload['rows'],2):
            for col_no,expected in enumerate(row,1):
                actual=s.cell(row_no,col_no).value
                if isinstance(expected,dict) and 'date' in expected:
                    if not isinstance(actual,(datetime,date)) or actual.isoformat()[:10]!=expected['date'][:10]:raise ValueError('审核日期变化')
                elif actual!=expected:raise ValueError(f'现有数据或审核值变化：{row_no},{col_no}')
        for item in payload['links']:
            link=s[item['cell']].hyperlink
            if not link or not link.target:raise ValueError('文件链接丢失')
            if '\\' in link.target or ':' in link.target or link.target.startswith('/'):
                raise ValueError('文件链接必须为正斜杠相对路径：'+link.target)
            if (Path(payload['review']).parent/link.target).resolve()!=Path(item['target']).resolve():raise ValueError('文件链接目标不匹配')
    finally:w.close()
    for name,sha in payload['sources'].items():
        if c.sha256(Path(name).read_bytes())!=sha:raise ValueError('原始输出或调用档案变化')


def retarget_links(review,payload):
    """Patch native file links and portable workbook jump formulas, retaining all review inputs."""
    before=c.sha256(review.read_bytes())
    with ZipFile(review) as z:parts={name:z.read(name) for name in z.namelist()}
    sheet=xml(parts['xl/worksheets/sheet1.xml']);links=sheet.find(Q('hyperlinks'))
    cells={node.get('r'):node for node in sheet.iter(Q('c'))}
    for row_no,row in enumerate(payload['rows'],2):
        for col_no,value in enumerate(row,1):
            if not isinstance(value,str) or not value.startswith('=HYPERLINK('):continue
            ref=get_column_letter(col_no)+str(row_no)
            cell=cells.get(ref)
            if cell is None:continue
            for child in list(cell):
                if child.tag in {Q('f'),Q('v'),Q('is')}:cell.remove(child)
            cell.set('t','str')
            E.SubElement(cell,Q('f')).text=value[1:]
            E.SubElement(cell,Q('v')).text='打开职业资料'
    rel_path='xl/worksheets/_rels/sheet1.xml.rels';rels=xml(parts[rel_path])
    by_cell={link.get('ref'):link for link in links} if links is not None else {}
    ids={rel.get('Id') for rel in rels}
    for n,item in enumerate(payload['links'],1):
        node=by_cell.get(item['cell'])
        if node is None:raise ValueError('原表材料链接缺失，停止局部更新：'+item['cell'])
        rid='draftMaterial'+str(n)
        while rid in ids:rid+='x'
        ids.add(rid);node.attrib.pop('location',None);node.set('{'+REL+'}id',rid)
        E.SubElement(rels,'{'+PKG+'}Relationship',{'Id':rid,'Type':REL+'/hyperlink',
            'Target':os.path.relpath(item['target'],start=review.parent).replace('\\','/'),'TargetMode':'External'})
    used={node.get('{'+REL+'}id') for node in sheet.iter() if node.get('{'+REL+'}id')}
    for rel in list(rels):
        if rel.get('Type')==REL+'/hyperlink':
            if rel.get('Id') not in used:rels.remove(rel)
            elif rel.get('Target') and not rel.get('Target').lower().startswith(('http:','https:','mailto:')):
                rel.set('Target',rel.get('Target').replace('\\','/'))
    parts['xl/worksheets/sheet1.xml']=encoded(sheet);parts[rel_path]=encoded(rels)
    candidate=review.with_name('.draft_links_pending.xlsx')
    with ZipFile(candidate,'w',ZIP_DEFLATED) as z:
        for name,raw in parts.items():z.writestr(name,raw)
    validate(candidate,payload)
    if c.sha256(review.read_bytes())!=before:raise ValueError('修改链接期间原表发生变化')
    candidate.replace(review)


def write_receipt(review,args,payload,work=None):
    receipt={'layout_version':4,'run_id':args.run_id,'jd_run_id':args.jd_run_id,'updated_utc':c.now(),
             'sources':payload['sources'],'links':payload['links'],'removed_classifications':payload['removed_classifications'],
             'material_source':'drafts_original','workbook_sha256':c.sha256(review.read_bytes()),
             'script_sha256':c.sha256(Path(__file__).read_bytes())}
    if work:receipt['preview_directory']=str(work)
    (review.parent/'review_navigation_manifest.json').write_text(c.canonical(receipt)+'\n',encoding='utf-8')
    export=review.parent/'export_manifest.json'
    if export.exists():
        state=c.load_json(export);state['workbook_sha256']=receipt['workbook_sha256']
        state['material_source']='drafts_original';state['links_updated_utc']=receipt['updated_utc']
        export.write_text(c.canonical(state)+'\n',encoding='utf-8')


def run(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-id',required=True);p.add_argument('--jd-run-id',required=True)
    p.add_argument('--review',type=Path,default=c.ROOT/'material_preparation/review/职业与材料审核.xlsx')
    p.add_argument('--execute',action='store_true');p.add_argument('--verify-only',action='store_true')
    p.add_argument('--links-only',action='store_true',help='仅修正现有文件链接，保留所有单元格和审核数据')
    base=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node'
    p.add_argument('--node',type=Path,default=base/'bin/node.exe');p.add_argument('--node-modules',type=Path,default=base/'node_modules')
    args=p.parse_args(argv);validate_run_id(args.run_id);validate_run_id(args.jd_run_id)
    review=args.review.resolve();before=c.sha256(review.read_bytes());payload=model(review,args.run_id,args.jd_run_id)
    if args.verify_only:
        validate(review,payload)
        print('核验通过：职业',len(payload['rows']),'个；文件链接',len(payload['links']),'个；原始输出未改动。');return 0
    print('单页职业汇总：',len(payload['rows']),'行；JD及四份简历各配是否纳入，移除人工分类和表内正文。')
    if not args.execute:print('仅预览。');return 0
    if args.links_only:
        retarget_links(review,payload);write_receipt(review,args,payload)
        print('仅更新材料链接：全部指向drafts原稿；表格内容和审核意见未变。');return 0
    work=Path(tempfile.mkdtemp(prefix='ai_hr_file_review_'))
    subprocess.run(['cmd','/c','mklink','/J',str(work/'node_modules'),str(args.node_modules.resolve())],check=True,capture_output=True)
    builder=Path(__file__).with_name('review_navigation.mjs');shutil.copy2(builder,work/builder.name)
    inp=work/'inputs.json';inp.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
    result=subprocess.run([str(args.node),str(work/builder.name),str(inp),str(work)],capture_output=True,text=True,encoding='utf-8',errors='replace')
    if result.returncode:raise ValueError('表格生成失败：'+result.stderr[-1800:])
    print(result.stdout[-1800:])
    candidate=work/'职业与材料审核.xlsx';external_links(work/'authored.xlsx',candidate,payload);validate(candidate,payload)
    if c.sha256(review.read_bytes())!=before:raise ValueError('制作期间总表发生变化，停止覆盖')
    staging=review.with_name('.navigation_pending.xlsx');shutil.copyfile(candidate,staging);staging.replace(review)
    with (review.parent/'职业汇总.csv').open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.writer(file);writer.writerow(payload['headers']);writer.writerows(payload['rows'])
    write_receipt(review,args,payload,work)
    print('已更新原表与CSV；全部材料链接指向drafts原稿，不复制或改写正文。预览：',work)
    return 0


if __name__=='__main__':
    import sys
    try:sys.exit(run())
    except Exception as e:print(c.safe_error_message(e),file=sys.stderr);sys.exit(2)
