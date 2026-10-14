"""Local-first context and use-triggered detached refresh; no timers or remote writes."""
from __future__ import annotations
import copy
from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from .models import NianxiangError, digest, read_json, write_json, now, profile_lock
from .knowledge import profile_state, configuration, verify_account, verify_node, OFFLINE

CONTEXT_KEYS=('content.strategy','audience.needs','ip.profile','expression.baseline','methodology.current','content.assets','content.methods')
INTERVAL=86400
RUN_LEASE=1800


def _epoch(stamp):
    try:
        value=datetime.fromisoformat(stamp.replace('Z','+00:00'))
        return value.timestamp() if value.tzinfo else 0
    except (ValueError,TypeError,AttributeError):return 0


def _binding(state,config):
    return digest({k:state[k] for k in ('profile_id','account_id','space_id')} | {'mapping':config['knowledge_map']})


def valid_snapshot(item,state,config,key):
    expected=config['knowledge_map'][key]
    return bool(isinstance(item,dict) and all(item.get(k)==state[k] for k in ('profile_id','account_id','space_id'))
                and item.get('knowledge_id')==key and item.get('obj_token')==expected['obj_token']
                and item.get('mapping_digest')==digest(expected) and item.get('revision') is not None
                and 'content' in item and item.get('content_digest')==digest(item['content']))


def _bundle(profile,state,config):
    path=profile/'snapshots/context.json'
    if not path.exists():return {'schema_version':1,'generation':0,'knowledge':{}}
    value=read_json(path)
    if not isinstance(value,dict) or value.get('schema_version')!=1 or not isinstance(value.get('knowledge'),dict) or type(value.get('generation')) is not int:
        raise NianxiangError('invalid_cache','invalid context bundle')
    if value.get('binding')!=_binding(state,config):return {'schema_version':1,'generation':0,'knowledge':{}}
    return value


def local_items(profile,state,config,keys,tolerate_invalid=False):
    bundle=_bundle(profile,state,config);items={}
    for key in keys:
        if key not in config['knowledge_map']:raise NianxiangError('invalid_knowledge','choose configured knowledge IDs')
        item=bundle['knowledge'].get(key)
        if item is None:
            path=profile/'snapshots'/f'{key}.json'
            item=read_json(path) if path.exists() else None
        if item is not None and not valid_snapshot(item,state,config,key):
            if tolerate_invalid:continue
            raise NianxiangError('invalid_cache','foreign or damaged source snapshot')
        if item is not None:items[key]=copy.deepcopy(item)
    return items,bundle['generation']


def make_snapshot(current,state,config,key,previous=None):
    expected=config['knowledge_map'][key]
    if (current.get('account_id')!=state['account_id'] or current.get('space_id')!=state['space_id']
        or current.get('obj_token')!=expected['obj_token']):
        raise NianxiangError('target_mismatch','source belongs to another identity or object')
    if current.get('revision') is None or 'content' not in current:raise NianxiangError('invalid_response','version and body are required')
    # Validate machine sections before the source becomes usable for personalization.
    if key in ('ip.profile','content.methods'):
        from .personal import parse_personal_source
        parse_personal_source(current['content'],'collaboration' if key=='ip.profile' else 'rules')
    same=bool(previous and previous['revision']==current['revision'] and previous['content_digest']==digest(current['content']))
    stamp=now()
    return {**copy.deepcopy(current),'profile_id':state['profile_id'],'knowledge_id':key,
            'mapping_digest':digest(expected),'source':'feishu','content_digest':digest(current['content']),
            'read_at':previous['read_at'] if same else stamp,'checked_at':stamp,
            'body_synced_at':previous.get('body_synced_at',previous['read_at']) if same else stamp,
            'fact_status':'source_material_not_automatically_confirmed'}


def publish_snapshots(profile,items,state,config,locked=False,expected=None,expected_errors=None,cache_locked=False):
    """Publish one authoritative bundle atomically. Mirrors serve legacy readers only."""
    if not locked:
        with profile_lock(profile):return publish_snapshots(profile,items,state,config,True,expected,expected_errors)
    if not cache_locked:
        with profile_lock(profile,'.context-cache.lock',blocking=True):
            return publish_snapshots(profile,items,state,config,True,expected,expected_errors,True)
    if expected_errors is not None and error_versions(profile,state,config,items)!=expected_errors:
        raise NianxiangError('cache_changed','a source error was observed during refresh')
    live_state=profile_state(profile);live_config=configuration(profile)
    if _binding(state,config)!=_binding(live_state,live_config):raise NianxiangError('binding_changed','profile changed during refresh')
    latest,generation=local_items(profile,state,config,list(items),tolerate_invalid=True)
    if expected is not None and any(digest(latest.get(k))!=expected[k] for k in items):
        raise NianxiangError('cache_changed','a newer local result was published during refresh')
    bundle=_bundle(profile,state,config);merged=copy.deepcopy(bundle['knowledge']);merged.update(items)
    value={'schema_version':1,'binding':_binding(state,config),'generation':generation+1,'published_at':now(),'knowledge':merged}
    write_json(profile/'snapshots/context.json',value)
    # An interrupted mirror update never invalidates the already-atomic bundle.
    for key,item in items.items():write_json(profile/'snapshots'/f'{key}.json',item)
    status=sync_status(profile)
    if status.get('binding')==_binding(state,config) and status.get('invalidations'):
        status['invalidations']={k:v for k,v in status['invalidations'].items() if k not in items}
        status['invalidation_versions']={k:v for k,v in status.get('invalidation_versions',{}).items() if k not in items}
        write_json(profile/'context-sync.json',status)
    return value['generation']


def sync_status(profile):
    path=Path(profile)/'context-sync.json'
    return read_json(path) if path.exists() else {'status':'never_synced'}


def error_versions(profile,state,config,keys):
    status=sync_status(profile)
    values=status.get('invalidation_versions',{}) if status.get('binding')==_binding(state,config) else {}
    return {key:values.get(key) for key in keys}


def invalidate_sources(profile,keys,code):
    if code not in ('account_mismatch','identity_unverified','permission_denied','target_mismatch','invalid_personal_source','invalid_response'):return
    state=profile_state(profile);config=configuration(profile)
    _record(profile,state,config,'blocked',keys,code)


def _record(profile,state,config,status,keys,code=None,run_id=None,cache_locked=False):
    if not cache_locked:
        with profile_lock(profile,".context-cache.lock",blocking=True):
            return _record(profile,state,config,status,keys,code,run_id,True)
    # No body, token, exception payload or credentials in the synchronization journal.
    previous=sync_status(profile)
    failures=previous.get('failures',0)+1 if status=='deferred' else 0
    value={'schema_version':1,'binding':_binding(state,config),'status':status,'finished_at':now(),
           'knowledge_ids':list(keys),'code':code,'failures':failures,
           'retry_at':time.time()+min(3600,60*2**min(failures,6)) if status=='deferred' else 0,
           'run_id':run_id}
    invalidations=copy.deepcopy(previous.get('invalidations',{})) if previous.get('binding')==_binding(state,config) else {}
    versions=copy.deepcopy(previous.get('invalidation_versions',{})) if previous.get('binding')==_binding(state,config) else {}
    if status=='blocked':
        affected=list(config['knowledge_map']) if code in ('account_mismatch','identity_unverified','permission_denied') else list(keys)
        invalidations.update({key:code for key in affected})
        versions.update({key:str(uuid.uuid4()) for key in affected})
    value['invalidations']=invalidations;value['invalidation_versions']=versions
    write_json(profile/'context-sync.json',value)
    return value


def _assert_readable(profile,state,config,keys):
    status=sync_status(profile)
    if status.get('binding')==_binding(state,config):
        for key in keys:
            if key in status.get('invalidations',{}):
                raise NianxiangError(status['invalidations'][key],'known source error requires successful re-verification')


def sync_context(profile_dir,keys,adapter,run_id=None):
    profile=Path(profile_dir);state=profile_state(profile);config=configuration(profile)
    keys=list(dict.fromkeys(keys));failed_key=None
    if not keys or any(k not in config['knowledge_map'] for k in keys):raise NianxiangError('invalid_knowledge','choose configured knowledge IDs')
    try:
        # Capture local CAS tokens before any remote call; never replace newer write-through.
        cached,_=local_items(profile,state,config,keys,tolerate_invalid=True);baseline={k:digest(cached.get(k)) for k in keys};errors=error_versions(profile,state,config,keys)
        verify_account(state,adapter);items={};changed=[];full_reads=[]
        for key in keys:
            failed_key=key
            node=verify_node(state,config,{'knowledge_id':key},adapter);previous=cached.get(key)
            metadata=None
            if previous and node['obj_type']=='docx' and hasattr(adapter,'get_revision'):
                metadata=adapter.get_revision(key)
                if metadata.get('document_id')!=node['obj_token'] or metadata.get('revision') is None:
                    raise NianxiangError('target_mismatch','metadata does not match the source')
            if metadata and metadata['revision']==previous['revision']:
                # Reparse validated personal sources; check time does not change body time.
                current={**previous,'revision':metadata['revision']}
            else:
                current=adapter.read(key);full_reads.append(key)
                if metadata and isinstance(metadata['revision'],int) and isinstance(current.get('revision'),int) and current['revision']<metadata['revision']:
                    raise NianxiangError('invalid_response','body response predates the checked revision')
            items[key]=make_snapshot(current,state,config,key,previous)
            if not previous or items[key]['content_digest']!=previous['content_digest'] or items[key]['revision']!=previous['revision']:changed.append(key)
        verify_account(state,adapter)
        with profile_lock(profile):
            generation=publish_snapshots(profile,items,state,config,locked=True,expected=baseline,expected_errors=errors)
            _record(profile,state,config,'synced',keys,run_id=run_id)
        return {'status':'synced','changed':changed,'full_reads':full_reads,'generation':generation}
    except (NianxiangError,OSError,ValueError,TypeError,KeyError) as exc:
        code=getattr(exc,'code','invalid_response')
        status='deferred' if code in OFFLINE|{'busy','cache_changed','binding_changed'} else 'blocked'
        if _binding(state,config)==_binding(profile_state(profile),configuration(profile)):
            _record(profile,state,config,status,keys if code!='invalid_personal_source' else [failed_key],code,run_id)
        return {'status':status,'code':code,'changed':[]}


def read_context(profile_dir,keys,adapter=None,require_latest=False,cache_only=False,launcher=None):
    """Return a pinned local copy. Refresh age is never a foreground network gate."""
    profile=Path(profile_dir);state=profile_state(profile);config=configuration(profile)
    keys=list(dict.fromkeys(keys))
    if not keys:raise NianxiangError('invalid_knowledge','choose configured knowledge IDs')
    if require_latest and cache_only:raise NianxiangError('invalid_mode','latest and cache-only are exclusive')
    if any(k not in CONTEXT_KEYS for k in keys):
        if cache_only:raise NianxiangError('live_source_required','operational objects are read live')
        from .knowledge import load_context
        contexts=[k for k in keys if k in CONTEXT_KEYS];live_keys=[k for k in keys if k not in CONTEXT_KEYS]
        local=read_context(profile,contexts,adapter,require_latest=require_latest,launcher=launcher) if contexts else {'knowledge':{},'generation':None,'sync':{'status':'not_requested'}}
        live=load_context(profile,live_keys,adapter,refresh=True)
        if any(item['stale'] for item in live['knowledge'].values()):
            raise NianxiangError('offline','operational sources require live verification')
        return {'profile_id':state['profile_id'],'knowledge':{**local['knowledge'],**live['knowledge']},'generation':local['generation'],'sync':local['sync']}
    _assert_readable(profile,state,config,keys) if not require_latest else None
    items,generation=local_items(profile,state,config,keys,tolerate_invalid=require_latest)
    initial=len(items)!=len(keys)
    if require_latest or initial:
        if cache_only or adapter is None:raise NianxiangError('cache_unavailable','no trusted local copy; initialize or supply current material')
        synced=sync_context(profile,keys,adapter)
        if synced['status']!='synced':raise NianxiangError(synced.get('code','source_unavailable'),'required source refresh failed')
        items,generation=local_items(profile,state,config,keys)
        current=True;activity=synced
    else:
        current=False;activity={'status':'not_due'}
        due=any(time.time()-_epoch(x.get('checked_at',x.get('read_at')))>=INTERVAL for x in items.values())
        if due and not cache_only:
            # Capture local data above before spawning; worker completion cannot swap this response.
            activity=(launcher or request_sync)(profile,list(CONTEXT_KEYS))
    for key,item in items.items():
        expired=time.time()-_epoch(item.get('checked_at',item.get('read_at')))>=INTERVAL
        items[key]={**item,'status':'current' if current else 'local','cached':not current,'current':current,
                    'stale':expired,'generation':generation,'account_verified_live':current}
    return {'profile_id':state['profile_id'],'knowledge':items,'generation':generation,'sync':activity}


def request_sync(profile_dir,keys):
    profile=Path(profile_dir);state=profile_state(profile);config=configuration(profile);run_id=str(uuid.uuid4())
    try:
        with profile_lock(profile), profile_lock(profile,'.context-cache.lock',blocking=True):
            status=sync_status(profile)
            if status.get('binding')==_binding(state,config):
                if status.get('status') in ('starting','running') and time.time()-status.get('started_at',0)<RUN_LEASE:return {'status':'running'}
                if status.get('retry_at',0)>time.time():return {'status':'backoff','code':status.get('code')}
            write_json(profile/'context-sync.json',{'schema_version':1,'binding':_binding(state,config),
                       'status':'starting','started_at':time.time(),'run_id':run_id,'knowledge_ids':list(keys),'invalidations':status.get('invalidations',{}) if status.get('binding')==_binding(state,config) else {},'invalidation_versions':status.get('invalidation_versions',{}) if status.get('binding')==_binding(state,config) else {}})
            command=[sys.executable,'-B',str(Path(__file__).resolve().parents[1]/'sync_worker.py'),
                     '--profile-dir',str(profile),'--run-id',run_id,*keys]
            kwargs={'stdin':subprocess.DEVNULL,'stdout':subprocess.DEVNULL,'stderr':subprocess.DEVNULL,'close_fds':True}
            if os.name=='nt':kwargs['creationflags']=subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.DETACHED_PROCESS
            else:kwargs['start_new_session']=True
            try:process=subprocess.Popen(command,**kwargs)
            except OSError:
                _record(profile,state,config,'deferred',keys,'background_unavailable',run_id,cache_locked=True)
                return {'status':'unavailable','code':'background_unavailable'}
            return {'status':'started','pid':process.pid}
    except NianxiangError as exc:return {'status':'deferred','code':exc.code}


@contextmanager
def worker_lock(profile):
    """Separate OS lock; remote fetches never hold the foreground profile lock."""
    path=Path(profile)/'.context-sync.lock'
    if path.is_symlink():raise NianxiangError('invalid_path','worker lock redirects')
    with path.open('a+b') as handle:
        os.chmod(path,0o600)
        try:
            if os.name=='nt':
                import msvcrt
                handle.write(b'0');handle.flush();handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:raise NianxiangError('busy','a synchronization worker already runs') from exc
        try:yield
        finally:
            if os.name=='nt':handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
