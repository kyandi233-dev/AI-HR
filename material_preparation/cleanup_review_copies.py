"""Retire only recorded review copies after every live workbook links to original drafts."""
if __name__=='__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import argparse
import os
from pathlib import Path
from openpyxl import load_workbook
from shared import common as c
from material_preparation.review_material_links import run as update_master
from material_preparation.export_individual_reviews import run as update_individuals


def check_scope(root):
    expected=(c.ROOT/'material_preparation/review/resumes').absolute()
    if root.absolute()!=expected or root.resolve()!=expected.resolve():raise ValueError('清理目标不符')
    if not root.resolve().is_relative_to(c.ROOT.resolve()):raise ValueError('清理目录越出工作区')
    if root.is_symlink() or getattr(os.path,'isjunction',lambda p:False)(root):raise ValueError('不清理符号链接或联接目录')
    for directory in root.rglob('*'):
        if directory.is_symlink() or getattr(os.path,'isjunction',lambda p:False)(directory):raise ValueError('目录含联接或符号链接')


def plan_copies(review,receipt):
    root=review/'resumes';check_scope(root)
    items=receipt['files'];actual={p.resolve() for p in root.rglob('*') if p.is_file()}
    allowed=set()
    for item in items:
        target=Path(item['target']).resolve();raw=Path(item['raw']).resolve()
        if not target.is_relative_to(root.resolve()) or not raw.is_relative_to((c.ROOT/'material_preparation/drafts/occupations').resolve()):
            raise ValueError('副本或原稿路径越界')
        allowed.add(target)
        if not raw.is_file() or c.sha256(raw.read_bytes())!=item['raw_sha256']:raise ValueError('原稿已变化，停止清理')
        if target.exists() and c.sha256(target.read_bytes())!=item['sha256']:raise ValueError('副本已被人工修改，停止清理')
    if actual-allowed:raise ValueError('清理目录含未登记文件，停止')
    return root,items


def assert_no_live_copy_links(review):
    root=(review/'resumes').resolve()
    for path in review.rglob('*.xlsx'):
        if path.name.startswith(('~$','.')):continue
        book=load_workbook(path,read_only=False,data_only=False)
        try:
            for sheet in book:
                for row in sheet:
                    for cell in row:
                        link=cell.hyperlink
                        if link and link.target and not link.target.lower().startswith(('http:','https:','mailto:')):
                            resolved=(path.parent/link.target).resolve()
                            if resolved.is_relative_to(root):raise ValueError('仍有链接依赖副本：'+str(path))
        finally:book.close()


def run(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execute',action='store_true')
    args=parser.parse_args(argv);review=c.ROOT/'material_preparation/review'
    root=review/'resumes';receipt_path=review/'review_copy_cleanup.json'
    if not root.exists():
        assert_no_live_copy_links(review);print('review/resumes已不存在；当前审核表不依赖副本。');return 0
    config=c.load_json(c.ROOT/'material_preparation/config/human_review.json')
    if receipt_path.exists():receipt=c.load_json(receipt_path)
    else:
        navigation=c.load_json(review/'review_navigation_manifest.json')
        files=navigation.get('display_files')
        if not files:raise ValueError('缺少副本生成记录，不能自动删除')
        receipt={'status':'planned','files':[{**item,'raw_sha256':c.sha256(Path(item['raw']).read_bytes())} for item in files]}
    _,items=plan_copies(review,receipt)
    print('将删除已核验的审核副本：',len(items),'份；目标：',root.resolve())
    if not args.execute:print('仅预览，未写入或删除。');return 0
    receipt['status']='planned';receipt_path.write_text(c.canonical(receipt)+'\n',encoding='utf-8')
    update_master(['--run-id',config['resume_run_id'],'--jd-run-id',config['jd_run_id'],'--execute','--links-only'])
    update_individuals(['--execute'])
    assert_no_live_copy_links(review)
    root,items=plan_copies(review,receipt)
    receipt['status']='links_updated';receipt_path.write_text(c.canonical(receipt)+'\n',encoding='utf-8')
    # No recursive removal: every file is bounded above and checked against its recorded hash.
    for item in items:
        target=Path(item['target'])
        if target.exists():target.unlink()
    for directory in sorted([p for p in root.rglob('*') if p.is_dir()],key=lambda p:len(p.parts),reverse=True):directory.rmdir()
    root.rmdir()
    receipt['status']='complete';receipt['deleted_utc']=c.now();receipt_path.write_text(c.canonical(receipt)+'\n',encoding='utf-8')
    print('已删除',len(items),'份额外副本；所有审核链接改用drafts原稿；原稿及调用档案保留。')
    return 0


if __name__=='__main__':
    import sys
    try:sys.exit(run())
    except Exception as error:print(c.safe_error_message(error),file=sys.stderr);sys.exit(2)
