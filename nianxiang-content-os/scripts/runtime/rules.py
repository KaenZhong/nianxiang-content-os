"""Select scoped private rules without promoting inferred ideas to confirmed facts."""
from __future__ import annotations
from .models import NianxiangError

def select_confirmed_rules(data,task):
    if not isinstance(data,dict) or data.get('schema_version')!=1 or not isinstance(data.get('rules'),list):raise NianxiangError('invalid_rules','rule schema_version=1 and rules list required')
    result=[];seen=set()
    for rule in data['rules']:
        if not isinstance(rule,dict) or not rule.get('id') or rule['id'] in seen or not str(rule.get('instruction','')).strip():raise NianxiangError('invalid_rules','unique rule ID and instruction required')
        seen.add(rule['id'])
        for scope in ('channels','surfaces','materials'):
            values=rule.get(scope)
            if not isinstance(values,list) or not values or not all(isinstance(v,str) and v for v in values):raise NianxiangError('invalid_rules','nonempty scope lists required')
        status=rule.get('status');basis=rule.get('basis')
        if status not in ('active','trial','paused','retired') or basis not in ('user_explicit','user_confirmed','cross_work','agent_inference'):raise NianxiangError('invalid_rules','unknown status or basis')
        if status in ('paused','retired') or status=='trial' and not task.get('include_trial'):continue
        confirmed=basis in ('user_explicit','user_confirmed','cross_work') and bool(rule.get('source'))
        if status=='active' and not confirmed:continue
        relevant=all('*' in rule[k] or task.get(t,'general' if t=='material' else None) in rule[k] for k,t in (('channels','channel'),('surfaces','surface'),('materials','material')))
        if relevant:result.append({**rule,'confirmed':confirmed,'scope':rule.get('scope',{'channels':rule['channels'],'surfaces':rule['surfaces'],'materials':rule['materials']})})
    result.sort(key=lambda r:(r['status']!='active',not r['confirmed'],r['id']))
    limit=task.get('limit',4)
    if not isinstance(limit,int) or not 1<=limit<=8:raise NianxiangError('invalid_rules','limit must be 1 to 8')
    return result[:limit]
