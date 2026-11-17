"""One stateless API request per trial; SDK retries disabled."""
import os
from .common import TASK_TO_PROFILE


def request_kwargs(settings,task):
    profile=settings['profiles'][TASK_TO_PROFILE[task['task']]]
    if profile['thinking']=='enabled' and 'temperature' in profile:
        raise ValueError('思考模式不可使用有效temperature。请调整配置。')
    if not isinstance(profile['model'],str) or not profile['model'].strip(): raise ValueError('model 不能为空')
    if profile['thinking'] not in ('enabled','disabled'): raise ValueError('thinking 无效')
    if type(profile['max_tokens']) is not int or profile['max_tokens']<1: raise ValueError('max_tokens 必须为正整数')
    temp=profile.get('temperature')
    if temp is not None and (type(temp) not in (int,float) or not 0<=temp<=2): raise ValueError('temperature 必须为0到2的数字')
    if len(task['messages'])!=1 or task['messages'][0]['role']!='user': raise ValueError('每次只能发送一条独立 user 消息')
    kwargs={
        'model':profile['model'], 'messages':task['messages'],
        'max_tokens':profile['max_tokens'], 'extra_body':{'thinking':{'type':profile['thinking']}},
    }
    if profile['thinking']=='disabled' and profile.get('temperature') is not None:
        kwargs['temperature']=profile['temperature']
    if task['json_mode']:
        kwargs['response_format']={'type':'json_object'}
    return kwargs


def api_request(settings,task):
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError('未安装依赖：py -m pip install -r requirements.txt') from e
    api_key=os.environ.get('DEEPSEEK_API_KEY','').strip()
    if not api_key:
        raise ValueError('未设置 DEEPSEEK_API_KEY 环境变量')
    kwargs=request_kwargs(settings,task)
    client=OpenAI(api_key=api_key,base_url=settings['api_base_url'],
                  timeout=float(settings['api_timeout_seconds']),max_retries=0)
    return client.chat.completions.create(**kwargs),kwargs
