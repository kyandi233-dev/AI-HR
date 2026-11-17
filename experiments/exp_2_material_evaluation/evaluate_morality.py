"""实验2：独立评价故事属性，沿用既有测量指标。"""
# 直接运行脚本时，将项目根目录加入模块查找路径。
if __name__=='__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))

import random
from shared.common import list_moral_pairs, render, new_task, sha256


def make_tasks(kind, args, occupations, config):
    items=[(d['pair_id'],label,d[label])
           for d in list_moral_pairs(config.get('_materials_root'))
           for label in ['neutral','negative']]
    random.Random(int(sha256(args.run_id)[:12],16)).shuffle(items)
    return [new_task(kind,f'{pid}_{label}',
                     render('experiments/exp_2_material_evaluation/prompts/moral_check.txt',behavior_text=story),
                     {'pair_id':pid,'background_type':label},True)
            for pid,label,story in items]


if __name__=='__main__':
    from shared.cli import task_main
    import sys
    sys.exit(task_main('moral-check'))
