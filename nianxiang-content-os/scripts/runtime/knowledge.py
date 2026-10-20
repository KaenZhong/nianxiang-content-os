"""Account-bound context, exact save authorization and non-blind reconciliation."""
from __future__ import annotations
import copy
from pathlib import Path
import re
from .models import NianxiangError,digest,read_json,write_json,now,result,profile_lock
from validate_local_config import validate

OFFLINE={'offline','timeout','network_error'}

def profile_state(profile, require_active=True):
    profile=Path(profile).resolve();state=read_json(profile/'state.json')
    if state.get('data_layout_version')!=1 or state.get('schema_version')!=1 or not state.get('account_id') or not state.get('space_id'):
        raise NianxiangError('invalid_profile','identity and layout are required')
    if require_active and not state.get('active'): raise NianxiangError('profile_inactive','complete structural verification before using knowledge')
    for name in ('snapshots','pending','tasks','derived'):
        if (profile/name).resolve()!=profile/name: raise NianxiangError('invalid_path','private directory redirects')
    return state

def configuration(profile):
    config=read_json(Path(profile)/'local-config.json')
    try: validate(config)
    except (ValueError,KeyError,TypeError): raise NianxiangError('invalid_configuration','schema=5 and complete mappings are required')
    state=profile_state(profile)
    if config['space_id']!=state['space_id']:raise NianxiangError('space_mismatch','configuration belongs to a different space')
    return config

def verify_account(state,adapter):
    account=adapter.get_account()
    if account.get('identity')!='user' or account.get('account_id')!=state['account_id']:
        raise NianxiangError('account_mismatch','current verified user differs from selected profile')

def verify_node(state,config,target,adapter):
    key=target.get('knowledge_id');expected=config['knowledge_map'].get(key)
    if not expected or target.get('obj_type',expected['obj_type'])!=expected['obj_type']:
        raise NianxiangError('target_mismatch','target is outside configured knowledge')
    node=adapter.get_node(target)
    wanted={'space_id':state['space_id'],'node_token':expected['node_token'],'obj_token':expected['obj_token'],'obj_type':expected['obj_type'],'parent_node_token':expected.get('parent_node_token',''),'title':expected['expected_title']}
    if any(str(node.get(k,''))!=str(v) for k,v in wanted.items()):raise NianxiangError('target_mismatch','live node no longer matches configuration')
    return node

def load_context(profile_dir,knowledge_ids,adapter,refresh=False):
    profile=Path(profile_dir);state=profile_state(profile);config=configuration(profile);items={}
    if not knowledge_ids or not all(k in config['knowledge_map'] for k in knowledge_ids):raise NianxiangError('invalid_knowledge','choose configured knowledge IDs')
    from .sync import local_items, make_snapshot, publish_snapshots, error_versions, invalidate_sources, _assert_readable
    cached_items,_=local_items(profile,state,config,knowledge_ids);updates={};errors=error_versions(profile,state,config,knowledge_ids)
    offline=False
    try: verify_account(state,adapter)
    except NianxiangError as exc:
        if exc.code not in OFFLINE:
            invalidate_sources(profile,knowledge_ids,exc.code);raise
        offline=True
    for key in knowledge_ids:
        cached=cached_items.get(key)
        valid=bool(cached and cached.get('profile_id')==state['profile_id'] and cached.get('account_id')==state['account_id'] and cached.get('space_id')==state['space_id'] and cached.get('mapping_digest')==digest(config['knowledge_map'][key]) and cached.get('content_digest')==digest(cached.get('content')))
        try:
            if offline:raise NianxiangError('offline','identity not verifiable')
            verify_node(state,config,{'knowledge_id':key},adapter)
            # Read source every new call; revision-only lookup is not assumed available.
            current=adapter.read(key)
            expected=config['knowledge_map'][key]
            if current.get('account_id')!=state['account_id'] or current.get('space_id')!=state['space_id'] or current.get('obj_token')!=expected['obj_token']:
                raise NianxiangError('target_mismatch','source body belongs to another object')
            if current.get('revision') is None or 'content' not in current: raise NianxiangError('invalid_response','source version and body are required')
            use_cache=valid and not refresh and cached.get('revision')==current['revision'] and digest(cached['content'])==digest(current['content'])
            snap=make_snapshot(current,state,config,key,cached)
            updates[key]=snap
            items[key]={**snap,'status':'current','cached':use_cache,'current':True,'stale':False}
        except NianxiangError as exc:
            if exc.code not in OFFLINE or not valid:
                invalidate_sources(profile,[key],exc.code);raise
            _assert_readable(profile,state,config,[key])
            items[key]={**cached,'status':'stale','cached':True,'current':False,'stale':True,'message':'offline; source and account cannot currently be verified'}
    if updates:publish_snapshots(profile,updates,state,config,expected={k:digest(cached_items.get(k)) for k in updates},expected_errors={k:errors[k] for k in updates})
    return {'profile_id':state['profile_id'],'knowledge':items}

def request_signature(request):
    return digest({k:request.get(k) for k in ('operation_id','target','action','base_revision','content')})

def target_binding(profile,request):
    config=configuration(profile);target=request.get('target') or {}
    return digest({'knowledge_mapping':config['knowledge_map'].get(target.get('knowledge_id')),'table_mapping':config['base_tables'].get(target.get('table_key'))})


def authorize_request(profile,request,evidence):
    """Prepare authorization only after the caller records the user's actual instruction."""
    state=profile_state(profile)
    return {'confirmed':True,'by':'user','evidence':evidence,'operation_id':request.get('operation_id'),'request_digest':request_signature(request),'binding_digest':target_binding(profile,request),'account_id':state['account_id'],'space_id':state['space_id']}

def validate_request(profile,request):
    state=profile_state(profile);op=request.get('operation_id','')
    if not isinstance(op,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',op): raise NianxiangError('invalid_operation','stable operation_id is required')
    auth=request.get('authorization') or {}
    if auth.get('confirmed') is not True or auth.get('by')!='user' or not str(auth.get('evidence','')).strip() or auth.get('operation_id')!=op or auth.get('request_digest')!=request_signature(request) or auth.get('account_id')!=state['account_id'] or auth.get('space_id')!=state['space_id'] or auth.get('revoked') or auth.get('binding_digest')!=target_binding(profile,request):
        raise NianxiangError('authorization_required','authorization must bind the exact account, target, action and content')
    target=request.get('target');content=request.get('content')
    if not isinstance(target,dict) or not isinstance(content,dict):raise NianxiangError('invalid_request','target and patch must be objects')
    if target.get('obj_type')=='bitable':
        if request.get('action') not in ('create','update') or target.get('table_key') not in ('topic_pool','moments_works','video_works','article_works'):
            raise NianxiangError('unsupported_action','only configured channel records and topic records are supported')
        keyfield='选题键' if target['table_key']=='topic_pool' else '作品键'
        if target.get('key_field')!=keyfield or not target.get('object_key') or content.get(keyfield)!=target['object_key']:
            raise NianxiangError('invalid_object_key','business key must be explicit and unchanged')
        if request['action']=='update' and request.get('base_revision') is None:raise NianxiangError('base_revision_required','record update requires a read base revision')
    elif target.get('obj_type')=='docx':
        action=request.get('action')
        if request.get('base_revision') is None:raise NianxiangError('base_revision_required','Docx append and replacement require the latest read revision')
        if action=='append':
            if set(content)!={'text'} or not isinstance(content.get('text'),str) or not content['text'].strip():raise NianxiangError('invalid_request','append requires exact nonempty plain text')
        elif action=='replace':
            if set(content)!={'pattern','replacement'} or not isinstance(content.get('pattern'),str) or not content['pattern'] or not isinstance(content.get('replacement'),str) or not content['replacement'] or content['replacement']==content['pattern']:
                raise NianxiangError('unsupported_action','replacement requires exact nonempty old and new text')
        else:raise NianxiangError('unsupported_action','Docx supports plain text append or exact replacement')
    else:raise NianxiangError('unsupported_action','unsupported object type')
    return state

def matches_record(actual,content):
    return bool(actual and all(actual.get('content',{}).get(k)==v for k,v in content.items()))

def matches_document(actual,request,expected_digest=None):
    if not actual or not isinstance(actual.get('content'),str):return False
    patch=request['content'];body=actual['content']
    if request['action']=='append':return patch['text'] in body
    return expected_digest is not None and digest(body)==expected_digest


def _save(profile,request,adapter):
    try:
        state=validate_request(profile,request);config=configuration(profile)
    except NianxiangError as exc:return result('blocked',exc.code)
    from .sync import error_versions,invalidate_sources,mark_source_changed,CONTEXT_KEYS
    source_errors=error_versions(profile,state,config,[request['target']['knowledge_id']])
    op=request['operation_id'];journal=profile/'pending'/f'{op}.json';signature=digest({'request':request_signature(request),'binding':request['authorization']['binding_digest']})
    prior=read_json(journal) if journal.exists() else None
    if prior and prior.get('signature')!=signature:return result('conflict','operation_id was already bound to another request')
    entry=prior or {'schema_version':1,'request':copy.deepcopy(request),'signature':signature,'profile_id':state['profile_id'],'account_id':state['account_id'],'space_id':state['space_id'],'attempted':False}
    if any(entry.get(k)!=state[k] for k in ('profile_id','account_id','space_id')):return result('blocked','pending_identity_mismatch')
    def finish(status,message,remote=None):
        outcome=result(status,message,remote,remote.get('revision') if remote else None)
        entry.update(status=status,last_checked_at=now(),result=outcome)
        write_json(journal,entry)
        return outcome
    try:
        verify_account(state,adapter);verify_node(state,config,request['target'],adapter)
        target=request['target'];content=request['content'];is_record=target['obj_type']=='bitable'
        actual=adapter.lookup(target,op) if is_record else adapter.read(target['knowledge_id'])
        if is_record and matches_record(actual,content):return finish('saved','matched and read back by stable object key',actual)
        if not is_record and matches_document(actual,request,entry.get('expected_document_digest')):
            outcome=finish('saved','content read back in source',actual)
            try:
                from .sync import make_snapshot,publish_snapshots
                snap=make_snapshot(actual,state,config,target['knowledge_id'])
                publish_snapshots(profile,{target['knowledge_id']:snap},state,config,locked=True,expected_errors=source_errors)
            except (NianxiangError,OSError) as exc:
                outcome['snapshot_refresh']='deferred'
                if target['knowledge_id'] in CONTEXT_KEYS:mark_source_changed(profile,[target['knowledge_id']])
                if getattr(exc,'code',None)=='invalid_personal_source':
                    from .sync import _record
                    _record(profile,state,config,'blocked',[target['knowledge_id']],exc.code)
                write_json(journal,entry)
            return outcome
        if is_record and actual and request['action']=='update':
            original=actual.get('content',{}).get('第一版')
            if original not in (None,'') and '第一版' in content and content['第一版']!=original:
                return finish('blocked','immutable_first_draft')
        if entry['attempted']:
            return finish('uncertain','a write was attempted; no matching readback; inspect before issuing a new operation')
        if is_record and request['action']=='create' and actual:return finish('conflict','existing business key has different content')
        if request.get('base_revision') is not None and (not actual or actual.get('revision')!=request['base_revision']):return finish('conflict','base revision changed')
        if not is_record and request['action']=='replace' and actual['content'].count(content['pattern'])!=1:return finish('conflict','text pattern is missing or ambiguous')
        if not is_record and request['action']=='replace':
            entry['expected_document_digest']=digest(actual['content'].replace(content['pattern'],content['replacement'],1))
        entry.update(attempted=True,status='uncertain',attempted_at=now());write_json(journal,entry)
        if not is_record and target['knowledge_id'] in CONTEXT_KEYS:
            marked=mark_source_changed(profile,[target['knowledge_id']])
            source_errors[target['knowledge_id']]=marked['invalidation_versions'][target['knowledge_id']]
        # Crash after dispatch is uncertain, including a successful write with failed readback.
        remote=adapter.write(request)
        actual=adapter.lookup(target,op) if is_record else adapter.read(target['knowledge_id'])
        if is_record: verified=matches_record(actual,content)
        else: verified=matches_document(actual,request,entry.get('expected_document_digest'))
        if not verified:return finish('uncertain','write response did not produce a matching readback',remote)
        outcome=finish('saved','write and source readback verified',actual)
        if not is_record:
            try:
                from .sync import make_snapshot,publish_snapshots
                snap=make_snapshot(actual,state,config,target['knowledge_id'])
                publish_snapshots(profile,{target['knowledge_id']:snap},state,config,locked=True,expected_errors=source_errors)
            except (NianxiangError,OSError) as exc:
                outcome['snapshot_refresh']='deferred'
                if target['knowledge_id'] in CONTEXT_KEYS:mark_source_changed(profile,[target['knowledge_id']])
                if getattr(exc,'code',None)=='invalid_personal_source':
                    from .sync import _record
                    _record(profile,state,config,'blocked',[target['knowledge_id']],exc.code)
                write_json(journal,entry)
        return outcome
    except NianxiangError as exc:
        invalidate_sources(profile,[request['target']['knowledge_id']],exc.code)
        status=('uncertain' if entry['attempted'] else 'pending') if exc.code in OFFLINE else ('uncertain' if entry['attempted'] and exc.code in ('invalid_response','uncertain_response') else 'blocked')
        return finish(status,exc.code)

def save_change(profile_dir,request,adapter):
    profile=Path(profile_dir)
    try:
        with profile_lock(profile):return _save(profile,request,adapter)
    except NianxiangError as exc:return result('blocked',exc.code)

def reconcile_pending(profile_dir,operation_id,adapter):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',str(operation_id)):return result('blocked','invalid_operation')
    profile=Path(profile_dir);entry=read_json(profile/'pending'/f'{operation_id}.json')
    return save_change(profile,entry['request'],adapter)
