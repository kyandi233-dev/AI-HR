"""Copy approved materials into an experiment and verify their frozen versions."""
import shutil
import tempfile
from pathlib import Path
from . import common as c
from .batch import validate_run_id
from .storage import write_json

EXPERIMENTS={
    'exp_2_material_evaluation':'moral-check',
    'exp_3_hiring':'abc',
}


def snapshot_path(experiment,version):
    if experiment not in EXPERIMENTS: raise ValueError('仅实验2、3使用具体材料版本')
    if not version: raise ValueError('请指定 --materials-version；先运行本实验的 snapshot_materials.py 保存固定材料')
    validate_run_id(version)
    return c.task_folder(EXPERIMENTS[experiment])/'materials'/version


def verify_directory(folder):
    path=folder/'manifest.json'
    if not path.is_file(): raise ValueError('缺少材料版本记录：'+str(path))
    manifest=c.load_json(path)
    files=manifest['files']
    patterns=['occupations/*/jd.txt','occupations/*/resumes/R*.txt',
              'occupations/*/onet/profile.txt','morality/*.json']
    actual={p.relative_to(folder).as_posix() for pattern in patterns for p in folder.glob(pattern) if p.is_file()}
    if not files or actual!=set(files): raise ValueError('材料版本的文件清单发生变化，请建立新版本')
    for name,digest in files.items():
        source=(folder/name).resolve()
        if not source.is_relative_to(folder.resolve()) or c.sha256(source.read_bytes())!=digest:
            raise ValueError('材料版本内容发生变化，请建立新版本：'+name)
    return manifest


def verified_snapshot(task,version):
    experiment=Path(c.TASK_FOLDERS[task]).name
    folder=snapshot_path(experiment,version)
    manifest=verify_directory(folder)
    if manifest['version']!=version or manifest['experiment']!=experiment:
        raise ValueError('材料版本与所属实验不一致')
    identity={'version':version,'experiment':experiment,
              'sha256':c.sha256(c.canonical(manifest['files']))}
    return folder,identity


def plan_snapshot(experiment,version,occupations,include_morality=False,
                  source_experiment=None,source_version=None):
    target=snapshot_path(experiment,version)
    if target.exists(): raise ValueError('材料版本已存在，不覆盖：'+str(target))
    if bool(source_experiment)!=bool(source_version):
        raise ValueError('--from-experiment 与 --from-version 需要一起指定')
    source=(snapshot_path(source_experiment,source_version) if source_experiment
            else c.ROOT/'material_preparation/approved')
    if source_experiment: verify_directory(source)
    if not occupations and not include_morality: raise ValueError('请选择职业或指定 --include-morality')
    if len(set(occupations))!=len(occupations): raise ValueError('职业列表重复')
    registry=c.load_json(c.occupations_file()) if occupations else {}
    files={}
    for slug in occupations:
        if slug not in registry: raise ValueError('未知职业：'+slug)
        paths=c.job_files(slug,source)
        c.load_text(paths['jd'])
        c.list_resumes(slug,materials_root=source)
        selected=[paths['jd'],*paths['resumes'].glob('R*.txt')]
        if paths['profile'].is_file(): selected.append(paths['profile'])
        for path in selected:
            if not path.resolve().is_relative_to(source.resolve()): raise ValueError('材料路径越界')
            files[path.relative_to(source).as_posix()]=c.sha256(path.read_bytes())
    if include_morality:
        c.list_moral_pairs(source)
        for path in sorted((source/'morality').glob('*.json')):
            if not path.resolve().is_relative_to(source.resolve()): raise ValueError('材料路径越界')
            files[path.relative_to(source).as_posix()]=c.sha256(path.read_bytes())
    return source,target,files


def create_snapshot(experiment,version,occupations,include_morality=False,
                    source_experiment=None,source_version=None,execute=False):
    source,target,files=plan_snapshot(experiment,version,occupations,include_morality,
                                    source_experiment,source_version)
    if not execute:
        print('预览：固定',len(files),'个材料文件到',target.relative_to(c.ROOT))
        print('未复制文件；确认后添加 --execute。此操作不调用模型。')
        return target
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.snapshot-',dir=target.parent) as staging:
        stage=Path(staging)/'materials'; stage.mkdir()
        for name,digest in files.items():
            dest=stage/name; dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source/name,dest)
            if c.sha256(dest.read_bytes())!=digest: raise ValueError('复制期间材料变化：'+name)
        manifest={'version':version,'experiment':experiment,'created_utc':c.now(),
                  'source':source.relative_to(c.ROOT).as_posix(),
                  'occupations':occupations,'files':dict(sorted(files.items()))}
        write_json(stage/'manifest.json',manifest,exclusive=True)
        verify_directory(stage)
        # A rename on Windows fails if another process has already created this version.
        stage.rename(target)
    print('已固定',len(files),'个材料文件：',target.relative_to(c.ROOT))
    return target


def snapshot_main(experiment):
    import argparse
    import sys
    parser=argparse.ArgumentParser(description='将批准材料固定到本实验目录；默认预览，不调用模型')
    parser.add_argument('--version',required=True)
    parser.add_argument('--occupations',nargs='+',default=[])
    parser.add_argument('--include-morality',action='store_true')
    parser.add_argument('--from-experiment',choices=list(EXPERIMENTS))
    parser.add_argument('--from-version')
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    try:
        create_snapshot(experiment,args.version,args.occupations,args.include_morality,
                        args.from_experiment,args.from_version,args.execute)
        return 0
    except Exception as exc:
        print('失败：'+str(exc),file=sys.stderr)
        return 2
