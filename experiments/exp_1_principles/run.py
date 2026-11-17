"""实验1：定义四种顺序条件，组装独立的原则判断试次。"""
# 直接运行脚本时，将项目根目录加入模块查找路径。
if __name__=='__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))

import json
import random
from shared.common import render, new_task, sha256


def make_tasks(kind, args, occupations, config):
    if kind=='principles':
        definitions={
            'morality':'私人道德信息：候选人在工作之外的日常生活中表现出的行为及其道德品质信息。',
            'ability':'专业能力信息：候选人的相关教育、工作经历、专业技能及工作成果所提供的专业胜任力证据。'
        }
        tasks={
            'task1':'任务一：专业能力判断。根据招聘资料，判断应聘者能否完成相应岗位的专业工作。',
            'task2':'任务二：面试推荐判断。根据招聘资料，决定是否建议候选人进入下一轮面试。'
        }
        ret=[]
        for def_order in [('morality','ability'),('ability','morality')]:
            for task_order in [('task1','task2'),('task2','task1')]:
                condition=('M' if def_order[0]=='morality' else 'A') + ('12' if task_order[0]=='task1' else '21')
                schema={x:{'priority':'','weight_ability':None,'weight_morality':None,
                     'importance_ability':None,'importance_morality':None,'reason':''} for x in task_order}
                user=render('experiments/exp_1_principles/prompts/principles.txt',definitions='\n'.join(definitions[x] for x in def_order),
                             tasks='\n'.join(tasks[x] for x in task_order),
                             json_schema=json.dumps(schema,ensure_ascii=False,indent=2))
                for rep in range(1,args.repeat+1):
                    ret.append(new_task(kind,f'{condition}_T{rep:02}',user,
                                 {'condition':condition,'definition_order':def_order,'task_order':task_order,'repeat':rep},True))
        # Every round contains four separate stateless requests.
        rounds=[]
        rnd=random.Random(int(sha256(args.run_id+'|principles')[:12],16))
        for rep in range(1,args.repeat+1):
            block=[t for t in ret if t['metadata']['repeat']==rep]
            rnd.shuffle(block)
            rounds.extend(block)
        return rounds
    raise ValueError(f'Unsupported task: {kind}')


if __name__=='__main__':
    from shared.cli import task_main
    import sys
    sys.exit(task_main('principles',default_batch='principles_100.json'))
