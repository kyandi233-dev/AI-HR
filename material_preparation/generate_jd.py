"""读取约定的完整职业模块，组装 JD 请求。"""
# 直接运行脚本时，将项目根目录加入模块查找路径。
if __name__=='__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from shared.common import render, new_task
from material_preparation.generation_inputs import read_jd_occupation_data


def make_tasks(kind, args, occupations, config):
    data, provenance=read_jd_occupation_data(args.occupation)
    user=render('material_preparation/prompts/jd.txt',occupation_name=occupations[args.occupation]['onet_name'],
           onet_code=occupations[args.occupation]['onet_code'],
           occupation_data_json=data)
    return [new_task(kind,'JD01',user,{'occupation':args.occupation,**provenance},False)]


if __name__=='__main__':
    from shared.cli import task_main
    import sys
    sys.exit(task_main('jd'))
