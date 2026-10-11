"""Local, consented core replacement. Private profiles are never part of a release."""
from __future__ import annotations
import ast
import copy
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import unicodedata
import uuid
import zipfile
from .models import NianxiangError,digest,file_digest,read_json,write_json,profile_lock,now
from .knowledge import profile_state

PACKAGE='nianxiang-content-os'
LEGACY_PACKAGE='nianxiang-content-studio'
MANIFEST='release-manifest.json'
MAX_FILE=16*1024*1024
MAX_TOTAL=64*1024*1024
FORBIDDEN={'data-root.json','personal-context.json','context-sync.json','state.json','bootstrap-plan.json','tasks','derived','USER.md','MEMORY.md','rules.local.json','business-conventions.md','private','profiles','snapshots','pending','__pycache__','.git','.venv','node_modules','.nianxiang','.DS_Store','local-config.json','user-profile.json','local-rules.json','business-guidelines.md','strategy-snapshot.md','expression-baseline-snapshot.md','active-release.json'}
LOCAL_EXAMPLES={'local/local-config.example.json','local/user-profile.example.json'}

def _error(code,message):raise NianxiangError(code,message)
def _path(name):
    if not isinstance(name,str) or not name or '\\' in name or ':' in name or name.startswith('/'):_error('invalid_archive_path','unsupported relative release path')
    parts=name.split('/')
    for part in parts:
        if not part or part in ('.','..') or part.rstrip(' .')!=part or any(ord(c)<32 for c in part) or part.casefold() in {x.casefold() for x in FORBIDDEN} or part.casefold().startswith('.nianxiang') or part.casefold().endswith(('.pyc','.pyo')):
            _error('invalid_archive_path','private or escaping release path')
        if re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?',part):_error('invalid_archive_path','reserved platform name')
    if parts[0].casefold()=='local' and name not in LOCAL_EXAMPLES and name!='local':_error('private_release_file','only public local examples are permitted')
    return name

def _canonical(path):
    absolute=Path(path).expanduser().absolute()
    if absolute.resolve()!=absolute:_error('invalid_path','redirected installation path')
    return absolute

def _manifest(value,package=PACKAGE):
    if package not in (PACKAGE,LEGACY_PACKAGE):_error('invalid_manifest','unsupported package identity')
    if not isinstance(value,dict) or value.get('schema_version')!=1 or value.get('name')!=package or value.get('entry')!='SKILL.md':_error('invalid_manifest','release identity and entry are required')
    if not isinstance(value.get('version'),str) or not re.fullmatch(r'\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?',value['version']):_error('invalid_manifest','semantic release version is required')
    if value.get('knowledge_schema_version')!=4 or value.get('data_layout_version')!=1:_error('incompatible_release','schema=4 and layout=1 are required')
    if value.get('release_source') is not None:_error('unsupported_release_source','first release supports explicit local packages only')
    files=value.get('files')
    if not isinstance(files,dict) or not files or len(files)>2000 or 'SKILL.md' not in files or 'scripts/manage.py' not in files or MANIFEST in files:_error('invalid_manifest','complete public file map, excluding the manifest itself, is required')
    keys=set();total=0
    for name,meta in files.items():
        _path(name);key=unicodedata.normalize('NFC',name).casefold()
        if key in keys:_error('ambiguous_archive_path','case or Unicode path collision')
        keys.add(key)
        if not isinstance(meta,dict) or not re.fullmatch('[0-9a-f]{64}',str(meta.get('sha256',''))) or type(meta.get('size')) is not int or not 0<=meta['size']<=MAX_FILE:_error('invalid_manifest','file size and SHA-256 are required')
        total+=meta['size']
    if total>MAX_TOTAL:_error('release_too_large','release exceeds local size limits')
    return value

def _tree_files(root):
    files={}
    for path in root.rglob('*'):
        name=path.relative_to(root).as_posix();_path(name)
        if path.is_symlink():_error('invalid_path','release trees cannot contain symlinks')
        if path.is_dir():continue
        if not path.is_file():_error('invalid_path','release trees contain only regular files')
        if name!=MANIFEST:files[name]={'sha256':file_digest(path),'size':path.stat().st_size}
    return files

def build_manifest(root,version):
    root=_canonical(root)
    value={'schema_version':1,'name':PACKAGE,'version':version,'entry':'SKILL.md','knowledge_schema_version':4,'data_layout_version':1,'release_source':None,'files':_tree_files(root),'changes':'See CHANGELOG.md; local development candidate, not a published release.'}
    return _manifest(value)

def verify_tree(root,manifest):
    return _verify_tree(root,manifest,PACKAGE)

def _verify_tree(root,manifest,package):
    root=_canonical(root)
    _manifest(manifest,package)
    if not root.is_dir() or read_json(root/MANIFEST)!=manifest or _tree_files(root)!=manifest['files']:_error('core_modified','installed core differs from its release manifest')
    return True

def _inspect_zip(archive,manifest=None):
    if not archive.is_file() or archive.is_symlink() or archive.stat().st_size>MAX_TOTAL*2:_error('invalid_archive','use a regular, bounded local ZIP')
    with zipfile.ZipFile(archive) as z:
        infos=z.infolist()
        if len(infos)>3000:_error('release_too_large','too many archive entries')
        members={};seen=set();total=0
        for info in infos:
            raw=info.filename.rstrip('/') if info.is_dir() else info.filename
            if raw==PACKAGE and info.is_dir():continue
            _path(raw)
            if not raw.startswith(PACKAGE+'/'):_error('invalid_archive_path','ZIP must have one expected top-level directory')
            name=raw[len(PACKAGE)+1:];_path(name)
            key=unicodedata.normalize('NFC',name).casefold()
            if key in seen:_error('ambiguous_archive_path','duplicate archive entry')
            seen.add(key)
            kind=stat.S_IFMT(info.external_attr>>16)
            if kind not in (0,stat.S_IFREG,stat.S_IFDIR) or info.flag_bits&1:_error('invalid_archive','links, special and encrypted entries are unsupported')
            if info.is_dir():
                if kind not in (0,stat.S_IFDIR):_error('invalid_archive','invalid directory entry')
                continue
            if kind==stat.S_IFDIR or info.file_size>MAX_FILE:_error('invalid_archive','invalid or oversized file')
            total+=info.file_size
            if total>MAX_TOTAL:_error('release_too_large','unpacked release exceeds limit')
            body=z.read(info)
            if len(body)!=info.file_size:_error('invalid_archive','incomplete archive file')
            members[name]=body
        if MANIFEST not in members:_error('invalid_manifest','embedded release manifest is required')
        embedded=_manifest(json.loads(members[MANIFEST].decode('utf-8')))
        if manifest is not None and manifest!=embedded:_error('manifest_mismatch','supplied and embedded manifests differ')
        if set(members)!=(set(embedded['files'])|{MANIFEST}):_error('invalid_archive','unlisted or missing public files')
        import hashlib
        for name,meta in embedded['files'].items():
            if len(members[name])!=meta['size'] or hashlib.sha256(members[name]).hexdigest()!=meta['sha256']:_error('digest_mismatch','release file differs from manifest')
        return embedded,members

def verify_release(archive,manifest=None):
    try:
        embedded,_=_inspect_zip(Path(archive),manifest)
        return {'status':'verified','version':embedded['version'],'manifest':embedded,'archive_sha256':file_digest(archive),'source_trust':'user_must_verify_local_source'}
    except (NianxiangError,OSError,ValueError,zipfile.BadZipFile,RuntimeError) as exc:return {'status':'blocked','message':getattr(exc,'code','invalid_archive')}

def check_update(manifest):
    _manifest(manifest)
    return {'status':'not_configured','message':'no official release source configured; explicit local import only'}

def installation_state_path(skill_root):
    root=_canonical(skill_root)
    control=root.parent/'.nianxiang-installations'/digest({'skill_root':str(root)})[:16]
    _canonical(control)
    return control/'installation-state.json'

def health_check(root,manifest):
    return _health_check(root,manifest,PACKAGE)

def _health_check(root,manifest,package):
    """Only run for the trusted, specifically authorized local core; no network doctor."""
    try:
        _verify_tree(root,manifest,package)
        entry=(root/'SKILL.md').read_text(encoding='utf-8')
        if not entry.startswith('---\n') or not re.search(r'^name: '+re.escape(package)+r'\s*$',entry,re.M):return False
        for name in manifest['files']:
            if name.endswith('.py'):ast.parse((root/name).read_text(encoding='utf-8'))
            elif name.endswith('.json'):json.loads((root/name).read_text(encoding='utf-8'))
        run=subprocess.run([sys.executable,'-B',str(root/'scripts/manage.py'),'doctor','--offline'],cwd=root,capture_output=True,timeout=30,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
        return run.returncode==0 and json.loads(run.stdout).get('private_root_outside_skill') is True
    except (NianxiangError,OSError,ValueError,SyntaxError,subprocess.SubprocessError):return False

def move_core(source,destination):
    if destination.exists():_error('destination_conflict','core destination is occupied')
    os.rename(source,destination)

def _paths(root,profile=None):
    root=_canonical(root);state=installation_state_path(root);control=state.parent
    if profile is not None:
        profile=_canonical(profile)
        if any(a==b or a in b.parents or b in a.parents for a,b in ((root,profile),(control,profile))):_error('invalid_path','profile must be separate from core and installation records')
        profile_state(profile,require_active=False)
    return root,state,control

def _consent(evidence):
    if not isinstance(evidence,str) or not evidence.strip():_error('authorization_required','record the user instruction for this exact local import or rollback')

def _state(root,statefile,legacy=False):
    if _canonical(statefile)!=installation_state_path(root):_error('installation_mismatch','use this installation journal')
    value=read_json(statefile)
    if value.get('kind')=='name_migration':return _name_state(root,statefile,value)
    if value.get('schema_version')!=1 or value.get('skill_root')!=str(root):_error('installation_mismatch','journal belongs to another core')
    if value.get('phase') not in ('prepared','old_moved','switched','active','rolled_back','rollback_prepared','aborted','recovery_required'):_error('invalid_installation_state','unknown transaction phase')
    for key,prefix in (('backup_name','old-core-'),('stage_name','stage-'),('failed_name','failed-core-')):
        if not re.fullmatch(prefix+r'[0-9a-f-]{36}',str(value.get(key,''))):_error('invalid_installation_state','invalid managed backup path')
    package=LEGACY_PACKAGE if legacy else PACKAGE
    _manifest(value['from_manifest'],package);_manifest(value['to_manifest'],package);_manifest(value['active_manifest'],package)
    return value

def _record(statefile,state,phase,**values):
    state.update(phase=phase,last_checked_at=now(),**values);write_json(statefile,state)

def _restore(root,statefile,state):
    control=statefile.parent;backup=control/state['backup_name'];failed=control/state['failed_name']
    verify_tree(backup,state['from_manifest'])
    if root.exists():
        verify_tree(root,state['to_manifest']);move_core(root,failed)
    move_core(backup,root)
    return _finish_restore(root,statefile,state)

def _finish_restore(root,statefile,state):
    try:
        verify_tree(root,state['from_manifest'])
        if not health_check(root,state['from_manifest']):_error('health_check_failed','restored core did not pass health check')
        verify_tree(root,state['from_manifest'])
    except (NianxiangError,OSError):
        _record(statefile,state,'recovery_required',active_manifest=state['from_manifest'])
        return {'status':'recovery_required','message':'old core restored but verification failed; inspect retained files'}
    _record(statefile,state,'rolled_back',active_manifest=state['from_manifest'])
    return {'status':'rolled_back','version':state['from_manifest']['version'],'private_data':'untouched'}

def apply_release(archive,skill_root,profile_dir,consent_id):
    state=None;statefile=None;control=None
    try:
        _consent(consent_id);root,statefile,control=_paths(skill_root,profile_dir)
        old=read_json(root/MANIFEST);verify_tree(root,old)
        verified=verify_release(archive)
        if verified['status']!='verified':return verified
        # Lock and logs live beside the core, never in any private profile.
        control.mkdir(parents=True,mode=0o700,exist_ok=True)
        with profile_lock(control):
            verify_tree(root,old)
            if statefile.exists():
                prior=_state(root,statefile)
                if prior['phase'] not in ('active','rolled_back','aborted'):_error('recovery_required','finish the interrupted transaction first')
                if prior['active_manifest']!=old:_error('installation_mismatch','active core and journal differ')
                if prior.get('kind')=='name_migration':_ensure_name_audit(statefile,prior)
            if old==verified['manifest']:return {'status':'up_to_date','version':old['version'],'private_data':'untouched'}
            token=str(uuid.uuid4());stage=control/('stage-'+token);backup=control/('old-core-'+token);archive_copy=control/('package-'+token+'.zip')
            if root.parent.stat().st_dev!=control.stat().st_dev:_error('cross_filesystem','safe rename requires one filesystem')
            shutil.copyfile(archive,archive_copy);os.chmod(archive_copy,0o600)
            try:
                if file_digest(archive_copy)!=verified['archive_sha256']:_error('archive_changed','local ZIP changed during preparation')
                new,members=_inspect_zip(archive_copy,verified['manifest']);stage.mkdir(mode=0o700)
                for name,body in members.items():
                    dest=stage/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(body)
                verify_tree(stage,new)
                if not health_check(stage,new):_error('health_check_failed','staged trusted core did not pass local health check')
                verify_tree(root,old)
                state={'schema_version':1,'skill_root':str(root),'transaction_id':token,'backup_name':backup.name,'stage_name':stage.name,'failed_name':'failed-core-'+token,'from_manifest':copy.deepcopy(old),'to_manifest':copy.deepcopy(new),'active_manifest':copy.deepcopy(old),'archive_sha256':verified['archive_sha256'],'authorization_evidence':consent_id,'started_at':now()}
                _record(statefile,state,'prepared')
                try:
                    move_core(root,backup);_record(statefile,state,'old_moved')
                    move_core(stage,root);_record(statefile,state,'switched',active_manifest=new)
                    if not health_check(root,new):return _restore(root,statefile,state)
                    verify_tree(root,new);_record(statefile,state,'active',active_manifest=new)
                    return {'status':'updated','version':new['version'],'private_data':'untouched'}
                except (NianxiangError,OSError) as exc:
                    try:
                        if backup.exists():return _restore(root,statefile,state)
                        verify_tree(root,old);_record(statefile,state,'aborted',active_manifest=old)
                    except (NianxiangError,OSError):
                        _record(statefile,state,'recovery_required')
                        return {'status':'recovery_required','message':'automatic restoration failed; retain journal and backup for recovery'}
                    return {'status':'blocked','message':getattr(exc,'code','switch_failed')}
            finally:
                if archive_copy.exists():archive_copy.unlink()
    except (NianxiangError,OSError,ValueError,KeyError) as exc:
        code=getattr(exc,'code','invalid_input')
        return {'status':'conflict' if code=='core_modified' else 'blocked','message':code}

def rollback_release(skill_root,installation_state,consent_id=None):
    try:
        _consent(consent_id);root,statefile,control=_paths(skill_root)
        if _canonical(installation_state)!=statefile:_error('installation_mismatch','journal path differs')
        with profile_lock(control):
            state=_state(root,statefile)
            if state.get('kind')=='name_migration':return _rollback_name(root,statefile,state,consent_id)
            if state['phase']=='rolled_back':verify_tree(root,state['from_manifest']);return {'status':'rolled_back','version':state['from_manifest']['version'],'private_data':'untouched'}
            if state['phase']!='active':_error('recovery_required','use recovery for an interrupted transaction')
            verify_tree(root,state['to_manifest']);verify_tree(control/state['backup_name'],state['from_manifest'])
            _record(statefile,state,'rollback_prepared',authorization_evidence=consent_id)
            try:return _restore(root,statefile,state)
            except (NianxiangError,OSError):
                _record(statefile,state,'recovery_required')
                return {'status':'recovery_required','message':'rollback incomplete; retain backup and use recovery after resolving the cause'}
    except (NianxiangError,OSError,ValueError,KeyError) as exc:return {'status':'conflict' if getattr(exc,'code','')=='core_modified' else 'blocked','message':getattr(exc,'code','rollback_failed')}

def recover_release(skill_root,installation_state,consent_id=None):
    try:
        _consent(consent_id);root,statefile,control=_paths(skill_root)
        if _canonical(installation_state)!=statefile:_error('installation_mismatch','journal path differs')
        with profile_lock(control):
            state=_state(root,statefile)
            if state.get('kind')=='name_migration':return _recover_name(root,statefile,state,consent_id)
            backup=control/state['backup_name'];failed=control/state['failed_name']
            if state['phase']=='active':
                verify_tree(root,state['to_manifest'])
                return {'status':'active','version':state['to_manifest']['version'],'message':'no interrupted update to recover','private_data':'untouched'}
            if root.exists():
                try:
                    verify_tree(root,state['from_manifest'])
                    state['authorization_evidence']=consent_id
                    return _finish_restore(root,statefile,state)
                except NianxiangError as exc:
                    if exc.code!='core_modified':raise
                verify_tree(root,state['to_manifest'])
            elif failed.exists() and not backup.exists():_error('recovery_required','no verified prior backup remains')
            try:return _restore(root,statefile,state)
            except (NianxiangError,OSError):
                _record(statefile,state,'recovery_required')
                return {'status':'recovery_required','message':'recovery incomplete; inspect retained journal and core copies'}
    except (NianxiangError,OSError,ValueError,KeyError) as exc:return {'status':'conflict' if getattr(exc,'code','')=='core_modified' else 'blocked','message':getattr(exc,'code','recovery_failed')}

def installation_status(skill_root):
    try:
        root,statefile,_=_paths(skill_root)
        if not statefile.exists():
            manifest=read_json(root/MANIFEST);verify_tree(root,manifest)
            return {'status':'unmanaged','version':manifest['version'],'message':'no update transaction recorded'}
        state=_state(root,statefile)
        if state['phase'] not in ('active','rolled_back','aborted'):return {'status':'recovery_required','phase':state['phase']}
        if state.get('kind')=='name_migration':_verify_tree(root,state['active_manifest'],state['active_manifest']['name'])
        else:verify_tree(root,state['active_manifest'])
        return {'status':state['phase'],'version':state['active_manifest']['version'],'private_data':'untouched'}
    except (NianxiangError,OSError,ValueError,KeyError) as exc:return {'status':'blocked','message':getattr(exc,'code','invalid_installation')}

# Only these explicit migration paths recognize the old package identity.
def _migration_roots(old_root,new_root,profile=None):
    old,old_state,old_control=_paths(old_root,profile)
    new,new_state,new_control=_paths(new_root,profile)
    if old==new or old.parent!=new.parent:_error('invalid_path','name migration requires distinct sibling core directories')
    return old,new,old_state,new_state,old_control,new_control

def _control_safe(control):
    _canonical(control)
    if control.exists():
        if not control.is_dir():_error('invalid_path','installation records must be a directory')
        for p in control.rglob('*'):
            _canonical(p)
            if not (p.is_file() or p.is_dir()):_error('invalid_path','unsafe installation records')

def _journal_digest(path):return file_digest(path) if path.exists() else None

def _migration_failure(exc):
    code=getattr(exc,'code','invalid_input')
    return {'status':'conflict' if code in ('core_modified','destination_conflict','plan_changed','installation_mismatch') else 'blocked','message':code}

def plan_name_migration(old_root,new_root,profile_dir):
    """Read-only preview binds original core, journal and selected profile."""
    try:
        old,new,old_state,new_state,old_control,new_control=_migration_roots(old_root,new_root,profile_dir)
        if new.exists() or new_control.exists():_error('destination_conflict','new core or its journal address is occupied')
        if not old.is_dir():_error('invalid_path','old installation directory is required')
        if not (old/MANIFEST).exists():return {'status':'legacy_import_required','message':'retain unmanaged originals; use a separate verified import'}
        manifest=read_json(old/MANIFEST);_verify_tree(old,manifest,LEGACY_PACKAGE)
        if not manifest['version'].startswith('4.'):_error('incompatible_release','only managed 4.x manifests support name migration')
        _control_safe(old_control)
        if old_state.exists():
            prior=_state(old,old_state,legacy=True)
            if prior['phase'] not in ('active','rolled_back','aborted'):_error('recovery_required','finish the old transaction first')
            if prior['active_manifest']!=manifest:_error('installation_mismatch','old core and journal disagree')
        profile=_canonical(profile_dir);state=profile_state(profile,require_active=False)
        value={'schema_version':1,'status':'preview','kind':'name_migration','old_root':str(old),'new_root':str(new),'profile_dir':str(profile),'profile_id':state['profile_id'],'account_id':state['account_id'],'space_id':state['space_id'],'from_manifest':manifest,'original_manifest_sha256':file_digest(old/MANIFEST),'original_journal_sha256':_journal_digest(old_state),'steps':['verify','stage','backup_old_core','switch_new_core','move_installation_records','health_check']}
        value['plan_id']=digest(value)
        return value
    except (NianxiangError,OSError,ValueError,KeyError,TypeError) as exc:return _migration_failure(exc)

def _name_state(root,statefile,value):
    if value.get('schema_version')!=1:_error('invalid_installation_state','unsupported migration journal schema')
    old,new,old_state,new_state,old_control,new_control=_migration_roots(value['old_root'],value['new_root'])
    if root not in (old,new) or statefile not in (old_state,new_state):_error('installation_mismatch','migration journal belongs to other roots')
    if value.get('skill_root') not in (str(old),str(new)):_error('installation_mismatch','invalid migration journal root')
    if value.get('phase') not in ('prepared','old_moved','switched','active','rollback_prepared','rolled_back','recovery_required'):_error('invalid_installation_state','unknown migration phase')
    try:uuid.UUID(value['transaction_id'])
    except (ValueError,TypeError,AttributeError):_error('invalid_installation_state','invalid migration transaction ID')
    for key,prefix in (('backup_name','old-core-'),('stage_name','stage-'),('failed_name','failed-core-')):
        if value.get(key)!=prefix+value['transaction_id']:_error('invalid_installation_state','invalid migration backup address')
    _manifest(value['from_manifest'],LEGACY_PACKAGE);_manifest(value['migration_target_manifest'],PACKAGE)
    expected=value['from_manifest'] if value['phase']=='rolled_back' else value['migration_target_manifest']
    if value['to_manifest']!=expected:_error('invalid_installation_state','migration target mismatch')
    if value['active_manifest'] not in (value['from_manifest'],value['migration_target_manifest']):_error('invalid_installation_state','migration active identity mismatch')
    _control_safe(statefile.parent)
    other=new_control if statefile.parent==old_control else old_control
    if other.exists():_error('installation_mismatch','two migration journal addresses exist')
    return value

def move_installation_records(source,destination):
    _control_safe(source);_canonical(destination)
    if destination.exists():_error('destination_conflict','new journal address occupied')
    os.rename(source,destination)

def _ensure_name_audit(statefile,state):
    """Archive the validated migration before its live journal can be replaced."""
    audit=statefile.parent/('name-migration-'+state['transaction_id']+'.json')
    _canonical(audit)
    if audit.exists():
        if read_json(audit)!=state:_error('migration_audit_mismatch','migration audit and active journal disagree; retain both for inspection')
    else:write_json(audit,state)

def _name_restore(root,statefile,state):
    old,new,old_state,new_state,old_control,new_control=_migration_roots(state['old_root'],state['new_root'])
    control=statefile.parent;backup=control/state['backup_name'];failed=control/state['failed_name']
    # Verify every core before any move. Never replace a local edit or a redirected backup.
    if old.exists():_verify_tree(old,state['from_manifest'],LEGACY_PACKAGE)
    else:_verify_tree(backup,state['from_manifest'],LEGACY_PACKAGE)
    if new.exists():
        verify_tree(new,state['migration_target_manifest']);move_core(new,failed)
    if not old.exists():move_core(backup,old)
    _verify_tree(old,state['from_manifest'],LEGACY_PACKAGE)
    if not _health_check(old,state['from_manifest'],LEGACY_PACKAGE):_error('health_check_failed','restored legacy core failed local health')
    _verify_tree(old,state['from_manifest'],LEGACY_PACKAGE)
    if control!=old_control:
        move_installation_records(control,old_control);statefile=old_state
    # All standard fields stay readable by the restored OLD runtime. Retain the
    # new target separately for this runtime's explicit, repeatable recovery.
    _record(statefile,state,'rolled_back',skill_root=str(old),to_manifest=state['from_manifest'],active_manifest=state['from_manifest'])
    write_json(statefile.parent/('name-migration-'+state['transaction_id']+'.json'),state)
    return {'status':'rolled_back','version':state['from_manifest']['version'],'private_data':'untouched','restored_root':str(old)}

def _attempt_name_restore(root,statefile,state):
    try:return _name_restore(root,statefile,state)
    except (NianxiangError,OSError) as exc:
        old_state=installation_state_path(Path(state['old_root']));new_state=installation_state_path(Path(state['new_root']))
        current=old_state if old_state.exists() else new_state
        _record(current,state,'recovery_required')
        return {'status':'recovery_required','message':getattr(exc,'code','restore_failed'),'private_data':'untouched'}

def _rollback_name(root,statefile,state,consent_id):
    if state['phase']=='rolled_back':
        _verify_tree(root,state['from_manifest'],LEGACY_PACKAGE)
        return {'status':'rolled_back','version':state['from_manifest']['version'],'private_data':'untouched'}
    if state['phase']!='active':_error('recovery_required','use recovery for interrupted name migration')
    verify_tree(root,state['migration_target_manifest'])
    _verify_tree(statefile.parent/state['backup_name'],state['from_manifest'],LEGACY_PACKAGE)
    _ensure_name_audit(statefile,state)
    _record(statefile,state,'rollback_prepared',authorization_evidence=consent_id)
    return _attempt_name_restore(root,statefile,state)

def _recover_name(root,statefile,state,consent_id):
    if state['phase']=='active':
        verify_tree(root,state['migration_target_manifest'])
        _ensure_name_audit(statefile,state)
        return {'status':'active','version':state['migration_target_manifest']['version'],'private_data':'untouched'}
    state['authorization_evidence']=consent_id
    return _attempt_name_restore(root,statefile,state)

def apply_name_migration(plan,archive,consent_id):
    state=None;statefile=None;archive_copy=None
    try:
        _consent(consent_id)
        if not isinstance(plan,dict) or plan.get('status')!='preview' or plan.get('kind')!='name_migration':_error('invalid_input','an executable name migration preview is required')
        supplied={k:v for k,v in plan.items() if k!='plan_id'}
        if plan.get('plan_id')!=digest(supplied):_error('plan_changed','migration preview was edited')
        old,new,old_state,new_state,old_control,new_control=_migration_roots(plan['old_root'],plan['new_root'],plan['profile_dir'])
        current=plan_name_migration(old,new,Path(plan['profile_dir']))
        if current.get('status')!='preview':return current
        if current!=plan:_error('plan_changed','core, journal or profile changed since preview')
        verified=verify_release(archive)
        if verified['status']!='verified':return verified
        old_control.mkdir(parents=True,exist_ok=True,mode=0o700)
        with profile_lock(old_control):
            if plan_name_migration(old,new,Path(plan['profile_dir']))!=plan:_error('plan_changed','migration source changed while acquiring lock')
            token=str(uuid.uuid4());stage=old_control/('stage-'+token);backup=old_control/('old-core-'+token)
            archive_copy=old_control/('package-'+token+'.zip');shutil.copyfile(archive,archive_copy);os.chmod(archive_copy,0o600)
            if file_digest(archive_copy)!=verified['archive_sha256']:_error('archive_changed','archive changed after verification')
            target,members=_inspect_zip(archive_copy,verified['manifest']);stage.mkdir(mode=0o700)
            for name,body in members.items():
                dest=stage/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(body)
            verify_tree(stage,target)
            if not health_check(stage,target):_error('health_check_failed','staged new core failed health check')
            if plan_name_migration(old,new,Path(plan['profile_dir']))!=plan:_error('plan_changed','source changed during staging')
            if old_state.exists():write_json(old_control/('previous-state-'+token+'.json'),read_json(old_state))
            state={'schema_version':1,'kind':'name_migration','old_root':str(old),'new_root':str(new),'skill_root':str(old),'transaction_id':token,'backup_name':backup.name,'stage_name':stage.name,'failed_name':'failed-core-'+token,'from_manifest':plan['from_manifest'],'to_manifest':target,'migration_target_manifest':target,'active_manifest':plan['from_manifest'],'plan_id':plan['plan_id'],'original_manifest_sha256':plan['original_manifest_sha256'],'original_journal_sha256':plan['original_journal_sha256'],'authorization_evidence':consent_id,'archive_sha256':verified['archive_sha256'],'started_at':now()}
            statefile=old_state;_record(statefile,state,'prepared')
            try:
                move_core(old,backup);_record(statefile,state,'old_moved')
                move_core(stage,new);_record(statefile,state,'switched',active_manifest=target)
                archive_copy.unlink();archive_copy=None
                move_installation_records(old_control,new_control);statefile=new_state
                if not health_check(new,target):return _attempt_name_restore(new,statefile,state)
                verify_tree(new,target);_record(statefile,state,'active',skill_root=str(new),active_manifest=target)
                write_json(statefile.parent/('name-migration-'+token+'.json'),state)
                return {'status':'migrated','version':target['version'],'private_data':'untouched','skill_root':str(new)}
            except (NianxiangError,OSError):
                return _attempt_name_restore(old,statefile,state)
    except (NianxiangError,OSError,ValueError,KeyError,TypeError) as exc:return _migration_failure(exc)
    finally:
        if archive_copy is not None and archive_copy.exists():archive_copy.unlink()
