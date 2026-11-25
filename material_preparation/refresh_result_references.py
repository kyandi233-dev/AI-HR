"""Retarget derived review references without rebuilding workbooks or editing opinions."""
if __name__=='__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
import json
import os
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from xml.etree import ElementTree as E
from openpyxl import load_workbook
from shared import common as c,material_results as mr
from material_preparation.review_navigation import xml,encoded,Q,REL


def aliases():
    values={}
    for key,path in mr.mapping()['aliases'].items():
        old=key.split(':',1)[1];new=Path(path).name
        if old in values and values[old]!=new:raise ValueError('旧批次名称存在歧义')
        values[old]=new
    return values


def target_for(path):
    item=mr.mapping()['files'].get(mr.old_key(path))
    if not item:return None
    target=item.get('link_path') or item.get('path')
    return c.ROOT/target if target else None


def replace_json(value,names):
    if isinstance(value,dict):return {replace_json(k,names):replace_json(v,names) for k,v in value.items()}
    if isinstance(value,list):return [replace_json(x,names) for x in value]
    if not isinstance(value,str):return value
    if value in names:return names[value]
    if value.startswith(('material_preparation/','material_preparation\\')):path=c.ROOT/value
    elif value.startswith(str(c.ROOT)):path=Path(value)
    else:return value
    target=target_for(path)
    if target is None:return value
    return str(target) if Path(value).is_absolute() else mr.relative(target)


def set_text(cell,value):
    for child in list(cell):
        if child.tag in {Q('v'),Q('is'),Q('f')}:cell.remove(child)
    cell.set('t','inlineStr');E.SubElement(E.SubElement(cell,Q('is')),Q('t')).text=value


def patch_book(path,names):
    original=path.read_bytes()
    with ZipFile(path) as z:parts={n:z.read(n) for n in z.namelist()}
    book=load_workbook(path,data_only=False)
    edits={};rewires={};before={}
    try:
        for index,sheet in enumerate(book,1):
            sheet_edits={};sheet_links={}
            for row in sheet:
                for cell in row:
                    before[(sheet.title,cell.coordinate)]=cell.value
                    if row[0].row==5 and cell.value=='完整提示词':sheet_edits[cell.coordinate]='调用输入'
                    if isinstance(cell.value,str) and cell.value in names:
                        # Only hidden batch identity columns may change, never a reviewer's note.
                        if sheet.cell(5,cell.column).value=='材料批次' and names[cell.value]!=cell.value:
                            sheet_edits[cell.coordinate]=names[cell.value]
                    if cell.hyperlink and cell.hyperlink.target:
                        value=cell.hyperlink.target
                        if value.lower().startswith(('http:','https:','mailto:')):continue
                        target=target_for((path.parent/value).resolve())
                        if target:
                            if not target.is_file():raise ValueError('新链接目标不存在：'+str(target))
                            sheet_links[cell.hyperlink.id]=os.path.relpath(target,path.parent).replace('\\','/')
                            if cell.value=='打开提示词':sheet_edits[cell.coordinate]='打开调用输入'
            if sheet_edits:edits[index]=sheet_edits
            if sheet_links:rewires[index]=sheet_links
    finally:book.close()
    if not edits and not rewires:return False
    for index,changes in edits.items():
        part=f'xl/worksheets/sheet{index}.xml';sheet=xml(parts[part]);cells={n.get('r'):n for n in sheet.iter(Q('c'))}
        for ref,value in changes.items():set_text(cells[ref],value)
        parts[part]=encoded(sheet)
    for index,links in rewires.items():
        part=f'xl/worksheets/_rels/sheet{index}.xml.rels';rels=xml(parts[part])
        for node in rels:
            if node.get('Id') in links:node.set('Target',links[node.get('Id')])
        parts[part]=encoded(rels)
    for part in list(parts):
        if part.startswith('xl/tables/') and part.endswith('.xml'):
            node=xml(parts[part]);changed=False
            for element in node.iter():
                if element.tag.endswith('tableColumn') and element.get('name')=='完整提示词':
                    element.set('name','调用输入');changed=True
            if changed:parts[part]=encoded(node)
    candidate=path.with_name('.'+path.stem+'.references.pending.xlsx')
    try:
        with ZipFile(candidate,'w',ZIP_DEFLATED) as z:
            for part,data in parts.items():z.writestr(part,data)
        checked=load_workbook(candidate,data_only=False)
        try:
            for index,sheet in enumerate(checked,1):
                for row in sheet:
                    for cell in row:
                        expected=edits.get(index,{}).get(cell.coordinate,before[(sheet.title,cell.coordinate)])
                        if cell.value!=expected:raise ValueError('审核单元格未保留：'+cell.coordinate)
        finally:checked.close()
        if path.read_bytes()!=original:raise ValueError('更新期间审核表已被修改，停止覆盖')
        candidate.replace(path)
    finally:
        if candidate.exists():candidate.unlink()
    return True


def run(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true');args=p.parse_args(argv)
    names=aliases();review=c.ROOT/'material_preparation/review'
    if not args.execute:
        print('将更新共享配置、审核表批次身份及旧调用链接；保留审核意见。');return 0
    for relative in mr.mapping().get('batches',[]):
        base=c.ROOT/relative;data=mr.info(base);changed=False
        if data.get('download_records') and data.get('task')!='onet-download':
            data['task']='onet-download';data['download']=c.load_json(c.ROOT/data['download_records'][0]);changed=True
        for inp in mr.inputs(base):
            record=c.load_json(inp);kind=record['task']
            if kind not in data.setdefault('parameters',{}):
                data['parameters'][kind]={'model':record['request']['config'],'api_base_url':record['request']['api_base_url']};changed=True
        for kind,manifest in list(data.get('generated',{}).items()):
            current=mr.load_manifest(kind,base.name)
            if current!=manifest:data['generated'][kind]=current;changed=True
        if changed:mr.write(base/mr.INFO,data)
        mr.refresh(base)
    for name in ['human_review.json','morality_generation.json']:
        path=c.ROOT/'material_preparation/config'/name
        data=c.load_json(path);new=replace_json(data,names)
        if data!=new:mr.write(path,new)
    changed=[]
    for path in review.rglob('*.xlsx'):
        if path.name.startswith(('~$','.')):continue
        if patch_book(path,names):changed.append(path)
    # These are derived export receipts; their historical copies are in the backup.
    for path in review.glob('*manifest.json'):
        data=replace_json(c.load_json(path),names)
        def refresh_hashes(obj):
            if isinstance(obj,dict):
                for key,value in list(obj.items()):
                    if isinstance(value,str) and len(value)==64 and Path(key).is_absolute() and Path(key).is_file():obj[key]=c.sha256(Path(key).read_bytes())
                    else:refresh_hashes(value)
                if obj.get('path') and Path(obj['path']).is_file() and 'sha256' in obj:obj['sha256']=c.sha256(Path(obj['path']).read_bytes())
            elif isinstance(obj,list):
                for child in obj:refresh_hashes(child)
        refresh_hashes(data)
        if 'workbook_sha256' in data:data['workbook_sha256']=c.sha256((review/'职业与材料审核.xlsx').read_bytes())
        if 'master_sha256' in data:data['master_sha256']=c.sha256((review/'职业与材料审核.xlsx').read_bytes())
        if 'config_sha256' in data:data['config_sha256']=c.sha256((c.ROOT/'material_preparation/config/human_review.json').read_bytes())
        path.write_text(c.canonical(data)+'\n',encoding='utf-8')
    print('已更新配置和',len(changed),'份审核表的派生引用；逐单元格验证审核内容保留。')
    return 0

if __name__=='__main__':
    import sys
    try:sys.exit(run())
    except Exception as exc:print(c.safe_error_message(exc),file=sys.stderr);sys.exit(2)
