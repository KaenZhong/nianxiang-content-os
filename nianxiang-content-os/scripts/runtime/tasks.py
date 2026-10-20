"""Versioned task checkpoints contain references, not a second knowledge archive."""
from __future__ import annotations
import copy
from pathlib import Path
import re
import uuid
from .models import NianxiangError,read_json,write_json,profile_lock,now,file_digest
from .knowledge import profile_state,load_context,configuration,verify_account,verify_node

KINDS={'strategy','topics','creation','operations','review'}
MODES={'discussion','execution'}
TRANSITIONS={'draft':{'draft','active','waiting','abandoned'},'active':{'active','waiting','completed','abandoned'},'waiting':{'waiting','active','abandoned'},'completed':set(),'abandoned':set()}
def _revision(value):return (type(value) is int and value>=0) or (isinstance(value,str) and bool(value.strip()) and len(value)<=128)

FIELDS={'kind','mode','status','goal','context_refs','selected_items','artifact_refs','checkpoint','next_step','operation_ids'}

def _consent(value):
    if not isinstance(value,str) or not value.strip():raise NianxiangError('authorization_required','record the actual task instruction')
def _uuid(value):
    try:
        if str(uuid.UUID(value))!=value:raise ValueError()
    except (ValueError,TypeError,AttributeError):raise NianxiangError('invalid_task','canonical task UUID required')
def _path(profile,task_id):
    _uuid(task_id);path=profile/'tasks'/f'{task_id}.json'
    if path.resolve()!=path:raise NianxiangError('invalid_path','task path redirects')
    return path

def _validate(data,profile):
    config=configuration(profile)
    if data.get('kind') not in KINDS or data.get('mode') not in MODES or data.get('status') not in TRANSITIONS:raise NianxiangError('invalid_task','unknown kind, mode or status')
    for k in ('goal','checkpoint','next_step'):
        if not isinstance(data.get(k),str) or k=='goal' and not data[k].strip():raise NianxiangError('invalid_task','task goal and checkpoints must be strings')
    for k in ('context_refs','selected_items','artifact_refs','operation_ids'):
        if not isinstance(data.get(k),list):raise NianxiangError('invalid_task','references and selections must be lists')
    if not all(isinstance(x,str) and x.strip() for x in data['selected_items']):raise NianxiangError('invalid_task','only confirmed selection labels may be stored')
    if not all(isinstance(x,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}',x) for x in data['operation_ids']):raise NianxiangError('invalid_task','invalid operation reference')
    for ref in data['context_refs']:
        if not isinstance(ref,dict) or set(ref)!={'knowledge_id','obj_token','revision'} or ref['knowledge_id'] not in config['knowledge_map'] or ref['obj_token']!=config['knowledge_map'][ref['knowledge_id']]['obj_token'] or not _revision(ref['revision']):raise NianxiangError('invalid_reference','context must identify a configured source and version')
    for ref in data['artifact_refs']:
        if not isinstance(ref,dict):raise NianxiangError('invalid_reference','artifact must be an object')
        if ref.get('type')=='local':
            if set(ref)!={'type','path','sha256','authorized_root'}:raise NianxiangError('invalid_reference','local reference needs explicit scope and digest')
            path=Path(ref['path']).expanduser().absolute();root=Path(ref['authorized_root']).expanduser().absolute()
            if path.resolve()!=path or root.resolve()!=root or not root.is_dir() or root not in path.parents or not re.fullmatch(r'[a-f0-9]{64}',str(ref['sha256'])):raise NianxiangError('invalid_reference','artifact is outside its scope or redirects')
            if path==profile or profile in path.parents:raise NianxiangError('invalid_reference','private runtime data is not an artifact')
        elif ref.get('type')=='remote':
            if set(ref)!={'type','target','revision'} or not isinstance(ref['target'],dict) or not _revision(ref['revision']):raise NianxiangError('invalid_reference','remote artifact must include target and version')
            target=ref['target'];mapping=config['knowledge_map'].get(target.get('knowledge_id'))
            if not mapping or target.get('obj_type')!=mapping['obj_type']:raise NianxiangError('invalid_reference','remote artifact target is not configured')
            if target['obj_type']=='bitable' and (target.get('table_key') not in config['base_tables'] or not target.get('object_key') or target.get('key_field') not in ('选题键','作品键')):raise NianxiangError('invalid_reference','record target needs configured table and stable business key')
        elif ref.get('type')=='missing':
            if set(ref)!={'type','label'} or not isinstance(ref.get('label'),str) or not ref['label'].strip():raise NianxiangError('invalid_reference','missing material needs a label')
        else:raise NianxiangError('invalid_reference','unknown artifact reference type')

def _load(profile,task_id):
    state=profile_state(profile);data=read_json(_path(profile,task_id))
    if data.get('schema_version')!=1 or data.get('task_id')!=task_id or not isinstance(data.get('version'),int) or isinstance(data['version'],bool) or data['version']<1 or any(data.get(k)!=state[k] for k in ('profile_id','account_id','space_id')):raise NianxiangError('task_identity_mismatch','task belongs to another profile or is malformed')
    _validate(data,profile);return data

def create_task(profile_dir,request,consent_id):
    _consent(consent_id);profile=Path(profile_dir);state=profile_state(profile)
    if not isinstance(request,dict) or set(request)-FIELDS:raise NianxiangError('invalid_task','unknown task fields')
    data={'status':'draft','context_refs':[],'selected_items':[],'artifact_refs':[],'checkpoint':'','next_step':'','operation_ids':[],**copy.deepcopy(request)};_validate(data,profile)
    task_id=str(uuid.uuid4());data.update(schema_version=1,task_id=task_id,version=1,profile_id=state['profile_id'],account_id=state['account_id'],space_id=state['space_id'],updated_at=now(),authorization_evidence=consent_id)
    with profile_lock(profile):
        directory=profile/'tasks';directory.mkdir(exist_ok=True,mode=0o700);write_json(_path(profile,task_id),data)
    return {'status':'created','task_id':task_id,'version':1,'profile_id':state['profile_id']}

def update_task(profile_dir,task_id,patch,expected_version,consent_id):
    profile=Path(profile_dir)
    try:
        _consent(consent_id);profile_state(profile)
        if not isinstance(patch,dict) or not patch or set(patch)-FIELDS or not isinstance(expected_version,int) or isinstance(expected_version,bool):raise NianxiangError('invalid_patch','only mutable task fields are accepted')
        with profile_lock(profile):
            data=_load(profile,task_id)
            if data['version']!=expected_version:return {'status':'conflict','version':data['version']}
            if data['status'] in ('completed','abandoned') or patch.get('status',data['status']) not in TRANSITIONS[data['status']]:raise NianxiangError('invalid_transition','terminal tasks are read only')
            data.update(copy.deepcopy(patch));_validate(data,profile);data.update(version=expected_version+1,updated_at=now(),authorization_evidence=consent_id);write_json(_path(profile,task_id),data)
        return {'status':'updated','task_id':task_id,'version':data['version']}
    except (NianxiangError,ValueError,TypeError,KeyError) as exc:return {'status':'blocked','code':getattr(exc,'code','invalid_task')}

def resume_task(profile_dir,task_id,adapter,require_latest=False):
    profile=Path(profile_dir)
    try:
        data=_load(profile,task_id);state=profile_state(profile);config=configuration(profile);missing=[];changed=[];operations={}
        live_artifacts=any(r['type']=='remote' for r in data['artifact_refs'])
        if live_artifacts:verify_account(state,adapter)
        loaded={}
        if data['context_refs']:
            from .sync import read_context
            keys=[r['knowledge_id'] for r in data['context_refs']]
            try:
                loaded=read_context(profile,keys,adapter,require_latest=require_latest,cache_only=not require_latest)
            except NianxiangError as exc:
                if require_latest or exc.code not in ('cache_unavailable','live_source_required'):raise
                loaded=read_context(profile,keys,adapter)
            for ref in data['context_refs']:
                item=loaded['knowledge'][ref['knowledge_id']]
                if require_latest and item['stale']:raise NianxiangError('offline','latest source verification is required')
                if item['revision']!=ref['revision']:changed.append(ref['knowledge_id'])
        for ref in data['artifact_refs']:
            if ref['type']=='missing':missing.append(ref['label'])
            elif ref['type']=='local':
                path=Path(ref['path'])
                if not path.is_file():missing.append(path.name)
                elif file_digest(path)!=ref['sha256']:changed.append(path.name)
            else:
                target=ref['target'];verify_node(state,config,target,adapter)
                item=adapter.lookup(target,None) if target['obj_type']=='bitable' else adapter.read(target['knowledge_id'])
                if item and (item.get('account_id')!=state['account_id'] or item.get('space_id')!=state['space_id'] or (target['obj_type']=='docx' and item.get('obj_token')!=config['knowledge_map'][target['knowledge_id']]['obj_token']) or (target['obj_type']=='bitable' and item.get('content',{}).get(target['key_field'])!=target['object_key'])):raise NianxiangError('target_mismatch','artifact response belongs to another identity or object')
                if not item:missing.append(target.get('object_key',target['knowledge_id']))
                elif item.get('revision')!=ref['revision']:changed.append(target.get('object_key',target['knowledge_id']))
        for op in data['operation_ids']:
            path=profile/'pending'/f'{op}.json'
            if not path.exists():operations[op]='missing';changed.append(op);continue
            entry=read_json(path)
            if any(entry.get(k)!=state[k] for k in ('profile_id','account_id','space_id')):raise NianxiangError('pending_identity_mismatch','operation belongs elsewhere')
            operations[op]=entry.get('status','unknown')
            if operations[op]!='saved':changed.append(op)
        live_artifacts=any(r['type']=='remote' for r in data['artifact_refs'])
        if live_artifacts:verify_account(state,adapter)
        status='needs_input' if missing else ('needs_revalidation' if changed else 'ready')
        return {'status':status,'task':data,'missing':missing,'changed':changed,'operations':operations,'remote_writes':0,'next_step':data['next_step'],'terminal':data['status'] in ('completed','abandoned'),'context_generation':loaded.get('generation'),'sync':loaded.get('sync'),'account_verified_live':live_artifacts or require_latest}
    except (NianxiangError,ValueError,TypeError,KeyError,OSError) as exc:return {'status':'blocked','code':getattr(exc,'code','invalid_task')}
