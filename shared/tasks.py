"""Dispatch to the task-specific builders."""
from . import common as c
from experiments.exp_1_principles.run import make_tasks as principles
from experiments.exp_3_hiring.run import make_tasks as hiring
from experiments.exp_2_material_evaluation.evaluate_morality import make_tasks as morality
from experiments.exp_2_material_evaluation.evaluate_relevance import make_tasks as relevance
from material_preparation.generate_jd import make_tasks as jd
from material_preparation.generate_resumes import make_tasks as resumes
from material_preparation.generate_morality import make_tasks as stories
from material_preparation.review_resumes import make_tasks as resume_review
from material_preparation.review_morality import make_tasks as moral_review

JOB_TASKS={'jd','resume','resume-review','baseline','abc','moral-relevance'}
BUILDERS={'principles':principles,'baseline':hiring,'abc':hiring,
          'jd':jd,'resume':resumes,'moral-generate':stories,
          'resume-review':resume_review,'moral-review':moral_review,
          'moral-check':morality,'moral-relevance':relevance}


def make_tasks(kind,args,occupations,settings):
    if kind not in c.TASK_TO_PROFILE: raise ValueError('未知任务：'+kind)
    if kind in JOB_TASKS and args.occupation not in occupations:
        raise ValueError('需要已登记的 --occupation：'+str(args.occupation))
    return BUILDERS[kind](kind,args,occupations,settings)
