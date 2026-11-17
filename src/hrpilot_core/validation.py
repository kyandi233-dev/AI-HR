"""Validate returned data before counting it as successful."""
import json

def check_response(kind, text):
    if not text or not text.strip(): raise ValueError('空白响应')
    try: parsed=json.loads(text)
    except json.JSONDecodeError as exc: raise ValueError('JSON解析失败: '+str(exc)) from exc
    if not isinstance(parsed,dict): raise ValueError('顶层必须是JSON对象')
    def iv(d,k,lo,hi):
        v=d.get(k)
        if type(v) is not int or not lo<=v<=hi: raise ValueError(f'{k}不是{lo}–{hi}的整数: {v}')
    if kind in ('baseline','abc'):
        for k in ['education_fit','work_experience','professional_skills','accomplishments','overall_suitability']:
            iv(parsed,k,1,5)
        iv(parsed,'interview_probability',0,100)
        if not isinstance(parsed.get('reason'),str): raise ValueError('缺少reason')
    elif kind=='principles':
        for tk in ['task1','task2']:
            sub=parsed.get(tk)
            if not isinstance(sub,dict): raise ValueError(f'缺少{tk}')
            if sub.get('priority') not in ['私人道德信息','专业能力信息']:
                raise ValueError('priority无效')
            for k in ['weight_ability','weight_morality']: iv(sub,k,0,100)
            if sub['weight_ability']+sub['weight_morality']!=100: raise ValueError('权重不等于100')
            for k in ['importance_ability','importance_morality']: iv(sub,k,1,7)
            if not isinstance(sub.get('reason'),str): raise ValueError('缺少理由')
    elif kind=='moral-check':
        for k in ['moral_valence','comprehensibility','naturalness']:
            iv(parsed,k,1,7)
        v=parsed.get('moral_foundations')
        if not isinstance(v,list) or len(v)>2 or any(not isinstance(x,str) for x in v):
            raise ValueError('moral_foundations需要0–2个字符串')
    elif kind=='moral-relevance':
        iv(parsed,'direct_professional_relevance',1,7)
    elif kind=='moral-generate':
        for k in ['pair_id','foundation','neutral','negative']:
            if not isinstance(parsed.get(k),str) or len(parsed[k].strip())<3:
                raise ValueError(f'缺少{k}')
    elif kind=='resume-review':
        iv(parsed,'naturalness',1,7);iv(parsed,'professional_plausibility',1,7)
    return parsed
