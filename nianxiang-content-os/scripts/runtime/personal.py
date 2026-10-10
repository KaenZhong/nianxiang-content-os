"""One Feishu authority for collaboration and private rules; derived views are disposable."""
from __future__ import annotations
import copy
from datetime import datetime
import json
from pathlib import Path
from .models import NianxiangError,read_json,write_json,digest,file_digest,now,profile_lock
from .knowledge import load_context,profile_state,configuration,save_change,authorize_request,verify_account
from .rules import select_confirmed_rules

SOURCES={'collaboration':('ip.profile','NIANXIANG_COLLABORATION_V1='),'rules':('methodology.current','NIANXIANG_PERSONAL_RULES_V1=')}
LEGACY={'collaboration':('user-profile.json',),'rules':('rules.local.json','local-rules.json')}
CONVENTIONS=('business-conventions.md','business-guidelines.md')
STATUSES={'active','trial','paused','retired'}
BASES={'user_explicit','user_confirmed','cross_work','agent_inference'}
CONFIRMED=BASES-{'agent_inference'}

def invalid():raise NianxiangError('invalid_personal_source','personal source is malformed or ambiguous')
def evidence(item):
    if not isinstance(item,dict) or item.get('status') not in STATUSES or item.get('basis') not in BASES:invalid()
    if not isinstance(item.get('source'),str) or not item['source'].strip():invalid()
    if 'confirmed_at' not in item:invalid()
    stamp=item['confirmed_at']
    if stamp is not None:
        try:
            if not isinstance(stamp,str) or 'T' not in stamp:invalid()
            datetime.fromisoformat(stamp.replace('Z','+00:00'))
        except ValueError:invalid()
def scope(item):
    if not isinstance(item,dict) or set(item)!={'channels','surfaces','materials'}:invalid()
    for vals in item.values():
        if not isinstance(vals,list) or not vals or not all(isinstance(x,str) and x.strip() for x in vals):invalid()
def validate_personal(data,kind):
    if not isinstance(data,dict) or type(data.get('schema_version')) is not int or data.get('schema_version')!=1:invalid()
    if kind=='collaboration':
        if set(data)!={'schema_version','preferred_name','preferred_name_evidence','preferences','boundaries'}:invalid()
        name=data['preferred_name']
        if name is not None:
            if not isinstance(name,str) or not name.strip() or len(name)>40 or '\n' in name or '\r' in name:invalid()
            evidence(data['preferred_name_evidence'])
        elif data['preferred_name_evidence'] is not None:invalid()
        seen=set()
        for group in ('preferences','boundaries'):
            if not isinstance(data[group],list):invalid()
            for item in data[group]:
                evidence(item);scope(item.get('scope'))
                if not isinstance(item.get('id'),str) or not item['id'] or item['id'] in seen or not isinstance(item.get('instruction'),str) or not item['instruction'].strip():invalid()
                seen.add(item['id'])
    elif kind=='rules':
        if set(data)!={'schema_version','rules'} or not isinstance(data['rules'],list):invalid()
        for item in data['rules']:
            evidence(item)
            if 'scope' in item:
                scope(item['scope'])
                if any(item['scope'][k]!=item.get(k) for k in ('channels','surfaces','materials')):invalid()
        try:select_confirmed_rules(data,{})
        except (NianxiangError,TypeError):invalid()
    else:invalid()
    return copy.deepcopy(data)

def parse_personal_source(content,kind):
    if kind not in SOURCES or not isinstance(content,str):invalid()
    prefix=SOURCES[kind][1];lines=[s for s in content.splitlines() if prefix in s]
    if not lines:return {'status':'empty'}
    if len(lines)!=1 or not lines[0].startswith(prefix) or lines[0].count(prefix)!=1:invalid()
    def unique_pairs(pairs):
        out={}
        for k,v in pairs:
            if k in out:invalid()
            out[k]=v
        return out
    try:data=json.loads(lines[0][len(prefix):],object_pairs_hook=unique_pairs)
    except (ValueError,TypeError):invalid()
    return validate_personal(data,kind)

def _legacy_pending(profile,state,kind):
    return state.get('long_term_sources_status',{}).get(kind)!='feishu_active' and any((profile/x).exists() for x in LEGACY[kind]+(CONVENTIONS if kind=='rules' else ()))

def _binding(item):
    return {k:item[k] for k in ('profile_id','account_id','space_id','knowledge_id','obj_token','revision','read_at')} | {'body_digest':digest(item['content']),'parser_version':1,'mapping_digest':item['mapping_digest']}

def read_personal_context(profile_dir,adapter,refresh=False,allow_stale=False):
    profile=Path(profile_dir)
    try:
        state=profile_state(profile);loaded=load_context(profile,[x[0] for x in SOURCES.values()],adapter,refresh)
        coll={};rules={'schema_version':1,'rules':[]};bindings={};pending=[];stale=False;established=False
        for kind,(key,prefix) in SOURCES.items():
            item=loaded['knowledge'][key]
            if digest(item['content'])!=item.get('content_digest'):raise NianxiangError('invalid_cache','snapshot integrity failed')
            stale=stale or item['stale']
            if item['stale'] and not allow_stale:raise NianxiangError('stale_not_allowed','explicit offline cache opt-in required')
            data=parse_personal_source(item['content'],kind);bindings[kind]=_binding(item)
            if data.get('status')=='empty':
                if _legacy_pending(profile,state,kind):pending.append(kind)
            else:
                established=True
                if kind=='collaboration':coll=data
                else:rules=data
        ctx={'status':'migration_required' if pending else ('stale' if stale else ('ready' if established else 'empty')),'collaboration':coll,'rules':rules,'source_bindings':bindings,'migration_groups':pending,'profile_id':state['profile_id'],'generated_at':now()}
        # A projection is never accepted as an input to reading authority.
        write_json(profile/'derived/personal-context.json',ctx)
        return ctx
    except (NianxiangError,ValueError,KeyError,TypeError) as exc:
        return {'status':'blocked','code':getattr(exc,'code','invalid_personal_source')}

def _legacy_files(profile):
    names=set(CONVENTIONS)
    for vals in LEGACY.values():names.update(vals)
    return {name:file_digest(profile/name) for name in sorted(names) if (profile/name).exists()}

def _legacy_payload(profile,kind,hashes):
    if kind=='collaboration':
        if 'user-profile.json' not in hashes:return None
        old=read_json(profile/'user-profile.json')
        if not isinstance(old,dict):invalid()
        if old.get('consent_confirmed') is not True:raise NianxiangError('legacy_confirmation_required','nickname lacks confirmation')
        ev={'status':'active','basis':'user_explicit','source':'legacy:user-profile.json:'+hashes['user-profile.json'],'confirmed_at':None}
        return validate_personal({'schema_version':1,'preferred_name':old.get('preferred_name'),'preferred_name_evidence':ev,'preferences':[],'boundaries':[]},kind)
    present=[n for n in LEGACY[kind] if n in hashes]
    if not present:return None
    payloads=[read_json(profile/n) for n in present]
    if any(x!=payloads[0] for x in payloads):raise NianxiangError('legacy_conflict','legacy aliases differ')
    data=copy.deepcopy(payloads[0])
    if not isinstance(data,dict) or not isinstance(data.get('rules'),list):invalid()
    for item in data['rules']:
        if not isinstance(item,dict):invalid()
        item.setdefault('confirmed_at',None)
    return validate_personal(data,kind)

def _line(kind,data):return SOURCES[kind][1]+json.dumps(data,ensure_ascii=False,separators=(',',':'),sort_keys=True)
def _request(profile,kind,data,item,operation_id):
    prefix=SOURCES[kind][1];body=item['content'];new=_line(kind,data);lines=[s for s in body.splitlines() if s.startswith(prefix)]
    return {'operation_id':operation_id,'target':{'knowledge_id':SOURCES[kind][0],'obj_type':'docx'},'action':'replace' if lines else 'append','base_revision':item['revision'],'content':{'pattern':lines[0],'replacement':new} if lines else {'text':new}}

def plan_personal_migration(profile_dir,adapter):
    profile=Path(profile_dir)
    try:
        state=profile_state(profile);hashes=_legacy_files(profile);loaded=load_context(profile,[x[0] for x in SOURCES.values()],adapter,True)
        plan={'schema_version':1,'profile_id':state['profile_id'],'account_id':state['account_id'],'space_id':state['space_id'],'legacy_hashes':hashes,'groups':{},'needs_confirmation':[n for n in CONVENTIONS if n in hashes]}
        for kind in SOURCES:
            data=_legacy_payload(profile,kind,hashes)
            if data is None:continue
            item=loaded['knowledge'][SOURCES[kind][0]]
            if item['stale']:raise NianxiangError('offline','migration preview needs current sources')
            current=parse_personal_source(item['content'],kind)
            if current.get('status')!='empty' and current!=data:raise NianxiangError('legacy_conflict','remote personal source differs; review before merging')
            op='personal-'+digest({'profile':state['profile_id'],'kind':kind,'hashes':hashes,'binding':_binding(item),'data':data})[:40]
            plan['groups'][kind]={'data':data,'binding':_binding(item),'request':None if current==data else _request(profile,kind,data,item,op)}
        plan['plan_id']=digest(plan);plan['status']='preview';return plan
    except NianxiangError as exc:return {'status':'conflict' if exc.code=='legacy_conflict' else 'blocked','code':exc.code}

def _verified_personal_save(outcome,adapter,kind,data,state,obj_token):
    if outcome['status']!='saved':return outcome
    try:
        actual=adapter.read(SOURCES[kind][0])
        if actual.get('account_id')!=state['account_id'] or actual.get('space_id')!=state['space_id'] or actual.get('obj_token')!=obj_token or parse_personal_source(actual['content'],kind)!=data:raise NianxiangError('invalid_personal_source','readback is not the unique intended personal source')
        return outcome
    except (NianxiangError,KeyError,TypeError) as exc:
        code=getattr(exc,'code','invalid_response')
        return {'status':'uncertain' if code in ('offline','timeout','network_error') else 'blocked','code':code}

def apply_personal_migration(profile_dir,plan,adapter,consent_id):
    profile=Path(profile_dir)
    try:
        if not isinstance(consent_id,str) or not consent_id.strip():raise NianxiangError('authorization_required','exact preview must be authorized')
        state=profile_state(profile);verify_account(state,adapter)
        if plan.get('status')!='preview' or plan.get('needs_confirmation'):raise NianxiangError('confirmation_required','unclassified conventions need user review')
        expected=digest({k:v for k,v in plan.items() if k not in ('plan_id','status')})
        if expected!=plan.get('plan_id') or any(plan.get(k)!=state[k] for k in ('profile_id','account_id','space_id')):raise NianxiangError('invalid_plan','preview changed or belongs elsewhere')
        if _legacy_files(profile)!=plan['legacy_hashes']:return {'status':'conflict','code':'legacy_changed'}
        loaded=load_context(profile,[SOURCES[k][0] for k in plan['groups']],adapter,True)
        # Preflight all not-attempted groups before any writes; attempted groups are reconciled by their same operation.
        for kind,group in plan['groups'].items():
            if group['data']!=_legacy_payload(profile,kind,plan['legacy_hashes']):raise NianxiangError('invalid_plan','payload differs from legacy evidence')
            item=loaded['knowledge'][SOURCES[kind][0]];request=group['request'];prior=None
            if request and (profile/'pending'/f"{request['operation_id']}.json").exists():prior=read_json(profile/'pending'/f"{request['operation_id']}.json")
            if item['stale']:raise NianxiangError('offline','current source required')
            current_binding=_binding(item)
            if any(current_binding[k]!=group['binding'].get(k) for k in ('profile_id','account_id','space_id','knowledge_id','obj_token','mapping_digest','parser_version')):return {'status':'conflict','code':'source_binding_changed'}
            if not prior and (item['revision']!=group['binding']['revision'] or digest(item['content'])!=group['binding']['body_digest']):return {'status':'conflict','code':'source_changed'}
            if request and not prior and request!=_request(profile,kind,group['data'],item,request['operation_id']):raise NianxiangError('invalid_plan','request differs from preview')
            parse_personal_source(item['content'],kind)
        outcomes={}
        for kind,group in plan['groups'].items():
            request=copy.deepcopy(group['request'])
            if request:
                request['authorization']=authorize_request(profile,request,consent_id);outcome=save_change(profile,request,adapter)
            else:outcome={'status':'saved','message':'existing source matches preview'}
            outcome=_verified_personal_save(outcome,adapter,kind,group['data'],state,group['binding']['obj_token'])
            outcomes[kind]=outcome
            with profile_lock(profile):
                current_state=profile_state(profile);statuses=current_state.setdefault('long_term_sources_status',{});statuses[kind]='feishu_active' if outcome['status']=='saved' else 'legacy_pending';write_json(profile/'state.json',current_state)
        final='saved' if all(x['status']=='saved' for x in outcomes.values()) else next(x['status'] for x in outcomes.values() if x['status']!='saved')
        return {'status':final,'groups':outcomes,'originals_retained':True}
    except (NianxiangError,KeyError,TypeError) as exc:return {'status':'blocked','code':getattr(exc,'code','invalid_plan')}

def _validate_context(profile,context):
    state=profile_state(profile);config=configuration(profile)
    if context.get('status') not in ('ready','empty') or context.get('profile_id')!=state['profile_id']:raise NianxiangError('invalid_projection','current context is required')
    for kind,(key,_) in SOURCES.items():
        snap=read_json(profile/'snapshots'/f'{key}.json');bind=context['source_bindings'][kind]
        if any(snap.get(k)!=state[k] for k in ('profile_id','account_id','space_id')) or digest(config['knowledge_map'][key])!=snap.get('mapping_digest') or digest(snap['content'])!=snap.get('content_digest') or _binding(snap)!=bind:raise NianxiangError('invalid_projection','source binding changed')
        data=parse_personal_source(snap['content'],kind)
        wanted={} if kind=='collaboration' else {'schema_version':1,'rules':[]}
        if context[kind]!=(wanted if data.get('status')=='empty' else data):raise NianxiangError('invalid_projection','projection differs from source')

def export_personal_context(profile_dir,context,kinds):
    profile=Path(profile_dir)
    try:
        if not kinds or any(k not in ('user','memory') for k in kinds):raise NianxiangError('invalid_export','only user and memory summaries supported')
        _validate_context(profile,context);directory=profile/'derived';directory.mkdir(exist_ok=True,mode=0o700);outputs=[]
        provenance=json.dumps(context['source_bindings'],ensure_ascii=False,sort_keys=True)
        for kind in set(kinds):
            lines=['# 派生摘要（只读，可重建）','生成：'+context['generated_at'],'来源与版本：'+provenance,'']
            if kind=='user':
                coll=context['collaboration'];ev=coll.get('preferred_name_evidence') or {}
                if ev.get('status')=='active' and ev.get('basis') in CONFIRMED:lines.append('称呼：'+coll['preferred_name'])
                for group in ('preferences','boundaries'):
                    lines += [x['instruction']+'；范围：'+json.dumps(x['scope'],ensure_ascii=False) for x in coll.get(group,[]) if x['status']=='active' and x['basis'] in CONFIRMED]
            else:
                lines += [r['instruction']+'；范围：'+json.dumps({k:r[k] for k in ('channels','surfaces','materials')},ensure_ascii=False) for r in context['rules']['rules'] if r['status']=='active' and r['basis'] in CONFIRMED]
                lines += ['知识入口：'+', '.join(config_key for config_key in configuration(profile)['knowledge_map'])]
            path=directory/('USER.md' if kind=='user' else 'MEMORY.md')
            if path.is_symlink():raise NianxiangError('invalid_path','summary redirects')
            # Reuse private atomic persistence for text via a same-directory tempfile.
            from tempfile import NamedTemporaryFile
            import os
            with NamedTemporaryFile('w',encoding='utf-8',dir=directory,delete=False) as f:
                os.chmod(f.name,0o600);f.write('\n'.join(lines)+'\n');f.flush();os.fsync(f.fileno());tmp=Path(f.name)
            try:os.replace(tmp,path)
            finally:
                if tmp.exists():tmp.unlink()
            outputs.append(path.name)
        return {'status':'exported','files':sorted(outputs),'source_written':False}
    except (NianxiangError,KeyError,TypeError) as exc:return {'status':'blocked','code':getattr(exc,'code','invalid_projection')}

def save_preferred_name(profile_dir,adapter,nickname,consent_id):
    profile=Path(profile_dir)
    try:
        if not isinstance(consent_id,str) or not consent_id.strip():raise NianxiangError('authorization_required','long-term nickname change needs explicit evidence')
        ctx=read_personal_context(profile,adapter,True)
        if ctx['status'] not in ('ready','empty'):raise NianxiangError('migration_required' if ctx['status']=='migration_required' else ctx.get('code','source_unavailable'),'current personal source required')
        data=copy.deepcopy(ctx['collaboration']) or {'schema_version':1,'preferred_name':None,'preferred_name_evidence':None,'preferences':[],'boundaries':[]}
        if data.get('preferred_name')==nickname and (data.get('preferred_name_evidence') or {}).get('basis') in CONFIRMED and (data.get('preferred_name_evidence') or {}).get('status')=='active':return {'status':'saved','message':'nickname already confirmed'}
        data['preferred_name']=nickname;data['preferred_name_evidence']={'status':'active','basis':'user_explicit','source':consent_id,'confirmed_at':now()};validate_personal(data,'collaboration')
        item=read_json(profile/'snapshots/ip.profile.json');op='nickname-'+digest({'profile':ctx['profile_id'],'nickname':nickname,'revision':item['revision'],'consent':consent_id})[:40]
        req=_request(profile,'collaboration',data,item,op);req['authorization']=authorize_request(profile,req,consent_id)
        outcome=save_change(profile,req,adapter)
        return _verified_personal_save(outcome,adapter,'collaboration',data,profile_state(profile),item['obj_token'])
    except NianxiangError as exc:return {'status':'blocked','code':exc.code}
