"""Delete explicitly rejected legacy exports and keep only the current readable layout."""
if __name__ == '__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import argparse
from pathlib import Path
from shared import common as c
from material_preparation.onet_data import read_registry,source_folder

LEGACY_CSV = {'模块目录.csv','条目明细.csv','页面链接.csv','原文段落.csv','职业汇总.csv','Tasks.csv'}


def cleanup(execute=False):
    prep = (c.ROOT/'material_preparation').resolve()
    review = prep/'review'
    folders = [review]+[source_folder(info).resolve() for info in read_registry().values()]
    deletes, empty_dirs, moves = [], [], []
    for folder in folders:
        folder.relative_to(prep)
        new = folder/'review_csv'
        old = folder/'csv'
        if new.exists():
            if old.exists():
                files = list(old.iterdir())
                if any(not p.is_file() or p.name not in LEGACY_CSV for p in files):
                    raise ValueError(f'Unexpected files in legacy CSV directory: {old}')
                deletes.extend(files)
                empty_dirs.append(old)
            if folder == review:
                files = list(new.iterdir())
                if [p.name for p in files] != ['职业汇总.csv']:
                    raise ValueError('Unexpected files in summary review_csv')
                if (review/'职业汇总.csv').exists():
                    raise ValueError('Current root summary CSV already exists; do not overwrite')
                moves.append((new/'职业汇总.csv',review/'职业汇总.csv'))
                empty_dirs.append(new)
            else:
                moves.append((new,old))
        backup = folder/'backups'
        if backup.exists():
            files = list(backup.iterdir())
            if any(not p.is_file() or p.suffix.lower()!='.xlsx' for p in files):
                raise ValueError(f'Unexpected files in workbook backups: {backup}')
            deletes.extend(files)
            empty_dirs.append(backup)
    current_manifest = review/'review_layout_manifest.json'
    if current_manifest.exists():
        if (review/'export_manifest.json').exists():
            deletes.append(review/'export_manifest.json')
        moves.append((current_manifest,review/'export_manifest.json'))
    # Every final absolute target is checked before any deletion/move; no recursive operations.
    for path in deletes+empty_dirs+[p for pair in moves for p in pair]:
        path.resolve().relative_to(prep)
    print(f'旧导出/备份文件={len(deletes)}；目录迁移={len(moves)}；执行={execute}')
    if not execute:
        return
    for path in deletes:
        path.unlink()
    # Remove old destination CSV dirs before moving the new ones into their place.
    for path in empty_dirs:
        if path.name in ['csv','backups']:
            path.rmdir()
    for origin,target in moves:
        origin.rename(target)
    for path in empty_dirs:
        if path.name=='review_csv':
            path.rmdir()
    print('只保留新版导出。原始网页、结构化JSON、prompt和实验记录未删除。')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    cleanup(parser.parse_args().execute)
