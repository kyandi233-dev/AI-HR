"""Dispatch to the task-specific builders."""
from . import common as c
from .experiments import principles, hiring
from .material_tasks import generation, review

JOB_TASKS={'jd','resume','resume-review','baseline','abc','moral-relevance'}


def make_tasks(kind,args,occupations,settings):
    if kind not in c.TASK_TO_PROFILE: raise ValueError('未知任务：'+kind)
    if kind in JOB_TASKS and args.occupation not in occupations:
        raise ValueError('需要已登记的 --occupation：'+str(args.occupation))
    module=(principles if kind=='principles' else hiring if kind in ('baseline','abc')
            else generation if kind in ('jd','resume','moral-generate') else review)
    return module.make_tasks(kind,args,occupations,settings)
