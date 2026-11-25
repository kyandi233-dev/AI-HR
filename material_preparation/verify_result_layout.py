"""Read-only verification of migrated calls, active drafts and review references."""
if __name__=='__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
from io import BytesIO
from pathlib import Path
import re
from zipfile import ZipFile
from openpyxl import load_workbook
from shared import common as c,material_results as mr
from material_preparation.migrate_result_layout import verify as verify_history


def compare_baseline(archive):
    names={key.split(':',1)[1]:Path(value).name for key,value in mr.mapping()['aliases'].items()}
    originals=books=cells=0
    with ZipFile(archive) as z:
        for name in z.namelist():
            if name.startswith(('material_preparation/drafts/','material_preparation/approved/','material_preparation/prompts/')):
                if (c.ROOT/name).read_bytes()!=z.read(name):raise ValueError('本次整理改动了原稿或模板：'+name)
                originals+=1
            if not name.startswith('material_preparation/review/') or not name.endswith('.xlsx'):continue
            before=load_workbook(BytesIO(z.read(name)),data_only=False)
            after=load_workbook(c.ROOT/name,data_only=False)
            try:
                if before.sheetnames!=after.sheetnames:raise ValueError('审核工作表变化：'+name)
                for old,new in zip(before,after):
                    for row in old:
                        for cell in row:
                            value=cell.value;expected=value
                            if cell.row==5 and value=='完整提示词':expected='调用输入'
                            elif value=='打开提示词':expected='打开调用输入'
                            elif isinstance(value,str) and value in names and old.cell(5,cell.column).value=='材料批次':expected=names[value]
                            if new[cell.coordinate].value!=expected:raise ValueError('审核内容变化：'+name+'/'+cell.coordinate)
                            cells+=1
                books+=1
            finally:before.close();after.close()
    print('迁移前后比对：原稿及模板',originals,'份；审核表',books,'份；单元格',cells,'个，均保留。')


def verify(baseline=None):
    verify_history();calls=outputs=links=0
    for category in ('occupation_generation','morality_generation'):
        for batch in (mr.root()/category).glob('*/'+mr.INFO):
            for p in mr.inputs(batch.parent):
                record=c.load_json(p);calls+=1
                if record.get('request_sha256') and record['request_sha256']!=c.sha256(c.canonical(record['request'])):
                    raise ValueError('输入请求指纹不一致：'+str(p))
                out=mr.output_path(p)
                if not out.exists():continue
                response=c.load_json(out);outputs+=1
                if response.get('request_sha256')!=record.get('request_sha256'):raise ValueError('输入输出不配对：'+str(p))
                choices=(response.get('raw_response') or {}).get('choices') or []
                if choices and choices[0].get('message',{}).get('content')!=response.get('answer'):
                    raise ValueError('原始回答不一致：'+str(out))
    team=c.load_json(c.ROOT/'material_preparation/config/human_review.json');drafts=0
    for kind,key in [('jd','jd_run_id'),('resume','resume_run_id')]:
        for item in mr.load_manifest(kind,team[key])['materials']:
            raw=(c.ROOT/item['draft']).read_bytes();out=c.load_json(c.ROOT/item['output'])
            if c.sha256(raw)!=item['draft_sha256'] or raw!=out['answer'].encode('utf-8'):
                raise ValueError('当前草稿不是原始回答：'+item['draft'])
            drafts+=1
    for p in (c.ROOT/'material_preparation/review').rglob('*.xlsx'):
        if p.name.startswith(('~$','.')):continue
        book=load_workbook(p,data_only=False)
        try:
            for sheet in book:
                for row in sheet:
                    for cell in row:
                        if isinstance(cell.value,str) and cell.value.upper().startswith('=HYPERLINK('):
                            if re.search(r'\[[A-Za-z]:[\\/]',cell.value) or 'file:' in cell.value.lower():
                                raise ValueError('审核表公式包含本机绝对路径或file协议：'+str(p)+'/'+cell.coordinate)
                        if not cell.hyperlink or not cell.hyperlink.target:continue
                        value=cell.hyperlink.target
                        if value.lower().startswith(('http:','https:','mailto:')):continue
                        if '\\' in value or ':' in value or value.startswith('/'):
                            raise ValueError('审核文件链接包含非跨平台路径或绝对盘符：'+str(p)+'/'+cell.coordinate+' -> '+value)
                        if not (p.parent/value).resolve().is_file():raise ValueError('审核文件链接失效：'+str(p)+'/'+cell.coordinate)
                        links+=1
        finally:book.close()
    if baseline:compare_baseline(baseline)
    print('新布局核验：调用输入',calls,'份；活动输出',outputs,'份；当前原稿',drafts,'份；有效文件链接',links,'个。')
    return 0


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',type=Path,help='可选：迁移前before.zip，逐格比较审核内容并核对模板和原稿')
    import sys
    try:sys.exit(verify(p.parse_args().baseline))
    except Exception as exc:print(c.safe_error_message(exc),file=sys.stderr);sys.exit(2)
