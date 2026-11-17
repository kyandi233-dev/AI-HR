"""组装中性与负面私人行为的配对材料生成请求。"""
# 直接运行脚本时，将项目根目录加入模块查找路径。
if __name__=='__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from shared.common import render, new_task, FOUNDATIONS, FOUNDATION_CN


def make_tasks(kind, args, occupations, config):
    if args.foundation not in FOUNDATIONS:
        raise ValueError('请指定 --foundation care/fairness/loyalty/authority/sanctity/liberty')
    ret=[]
    for i in range(args.start_index,args.start_index+args.count):
        pid=f'{args.foundation.upper()}_{i:03}'
        user=render('material_preparation/prompts/morality.txt',foundation=FOUNDATION_CN[args.foundation],pair_id=pid)
        ret.append(new_task(kind,pid,user,
                {'pair_id':pid,'foundation':args.foundation},True))
    return ret


if __name__=='__main__':
    from shared.cli import task_main
    import sys
    sys.exit(task_main('moral-generate'))
