"""One stateless API request per trial; SDK retries disabled."""
from .common import TASK_TO_PROFILE, load_api_key
from types import SimpleNamespace


def assemble_stream(chunks):
    content=''.join(choice.get('delta',{}).get('content') or ''
                    for chunk in chunks for choice in chunk.get('choices',[]) if choice.get('index',0)==0)
    finishes=[choice['finish_reason'] for chunk in chunks for choice in chunk.get('choices',[])
              if choice.get('index',0)==0 and choice.get('finish_reason')]
    last=chunks[-1] if chunks else {}
    usage=next((chunk['usage'] for chunk in reversed(chunks) if chunk.get('usage')),None)
    raw={'id':last.get('id'),'model':last.get('model'),'system_fingerprint':last.get('system_fingerprint'),
         'usage':usage,'response_assembled_from_stream':True,'stream_chunks':chunks,
         'choices':[{'index':0,'finish_reason':finishes[-1] if finishes else None,
                     'message':{'role':'assistant','content':content}}]}
    return SimpleNamespace(id=raw['id'],model=raw['model'],system_fingerprint=raw['system_fingerprint'],
                           choices=[SimpleNamespace(finish_reason=raw['choices'][0]['finish_reason'],
                                                    message=SimpleNamespace(content=content))],
                           model_dump=lambda **kw:raw)


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
    api_key=load_api_key()
    if not api_key:
        raise ValueError('请在项目根目录 .env 中填写 DEEPSEEK_API_KEY，或在当前终端设置同名环境变量')
    kwargs=request_kwargs(settings,task)
    with OpenAI(api_key=api_key,base_url=settings['api_base_url'],
                timeout=float(settings['api_timeout_seconds']),max_retries=0) as client:
        if settings.get('_stream'):
            kwargs.update(stream=True,stream_options={'include_usage':True})
            chunks=[]
            try:
                for chunk in client.chat.completions.create(**kwargs):
                    chunks.append(chunk.model_dump(mode='json'))
            except Exception as error:
                error.partial_response=assemble_stream(chunks)
                raise
            return assemble_stream(chunks),kwargs
        return client.chat.completions.create(**kwargs),kwargs
