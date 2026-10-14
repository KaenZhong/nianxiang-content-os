"""External private roots, explicit account profiles and previewed copy migration."""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import uuid
from .models import NianxiangError, read_json, write_json, file_digest

LEGACY_FILES=('local-config.json','user-profile.json','content-strategy-snapshot.md','expression-baseline-snapshot.md','rules.local.json','business-conventions.md')

def resolve_data_root(skill_root, data_dir=None):
    skill=Path(skill_root).expanduser().resolve()
    root=Path(data_dir if data_dir is not None else os.environ.get('NIANXIANG_HOME',Path.home()/'.nianxiang')).expanduser().resolve()
    if root==skill or skill in root.parents or root in skill.parents:
        raise NianxiangError('invalid_private_root','private data must be separate from the Skill directory')
    return root

def resolve_profile(skill_root, data_dir=None, profile_id=None):
    root=resolve_data_root(skill_root,data_dir)
    if not profile_id: raise NianxiangError('selection_required','choose --profile explicitly')
    try:
        if str(uuid.UUID(profile_id))!=profile_id: raise ValueError()
    except (ValueError,TypeError,AttributeError): raise NianxiangError('invalid_profile','profile must be a canonical UUID')
    path=root/'profiles'/profile_id
    if path.resolve()!=path: raise NianxiangError('invalid_profile','profile path must not redirect')
    if not path.is_dir() or not (path/'state.json').exists(): raise NianxiangError('profile_missing','selected profile does not exist')
    state=read_json(path/'state.json')
    if state.get('profile_id')!=profile_id or state.get('data_layout_version')!=1 or not state.get('account_id') or not state.get('space_id'):
        raise NianxiangError('invalid_profile','profile identity or layout is invalid')
    for subdir in ('snapshots','pending','tasks','derived'):
        target=path/subdir
        if target.resolve()!=target: raise NianxiangError('invalid_profile','profile subdirectory redirects')
    return path

def create_profile(root, account_id, space_id):
    if not account_id or not space_id: raise NianxiangError('identity_required','account and space are required')
    root=Path(root).expanduser().resolve();pid=str(uuid.uuid4());profile=root/'profiles'/pid
    if (root/'profiles').is_symlink(): raise NianxiangError('invalid_private_root','profiles must not redirect')
    profile.mkdir(parents=True,mode=0o700)
    for name in ('snapshots','pending'): (profile/name).mkdir(mode=0o700)
    write_json(profile/'state.json',{'schema_version':1,'data_layout_version':1,'profile_id':pid,'account_id':account_id,'space_id':space_id,'active':False})
    return pid

def default_private_file(skill_root,name,args):
    return resolve_profile(skill_root,getattr(args,'data_dir',None),getattr(args,'profile',None))/name

def add_profile_args(parser):
    parser.add_argument('--data-dir',type=Path,help='external private root; defaults to NIANXIANG_HOME or ~/.nianxiang')
    parser.add_argument('--profile',help='explicit account profile UUID')

def plan_migration(legacy_dir,profile_dir):
    legacy=Path(legacy_dir).expanduser().resolve();profile=Path(profile_dir).expanduser().resolve()
    if legacy==profile or legacy in profile.parents or profile in legacy.parents: raise NianxiangError('invalid_migration','source and target must be separate')
    state=read_json(profile/'state.json');files=[]
    for name in LEGACY_FILES:
        source=legacy/name;dest=profile/name
        if source.is_symlink() or dest.is_symlink(): raise NianxiangError('invalid_migration','migration must not use symlinks')
        if source.is_file(): files.append({'name':name,'source':str(source),'destination':str(dest),'source_sha256':file_digest(source),'destination_sha256':file_digest(dest) if dest.exists() else None})
    return {'schema_version':1,'profile_id':state['profile_id'],'profile_dir':str(profile),'legacy_dir':str(legacy),'files':files}

def apply_migration(plan,consent_id):
    if not str(consent_id or '').strip(): raise NianxiangError('authorization_required','copy migration requires explicit consent')
    legacy=Path(plan['legacy_dir']).resolve();profile=Path(plan['profile_dir']).resolve()
    fresh=plan_migration(legacy,profile)
    if fresh['profile_id']!=plan.get('profile_id') or {(x['name'],x['source_sha256']) for x in fresh['files']}!={(x['name'],x['source_sha256']) for x in plan['files']}:
        raise NianxiangError('migration_changed','source changed after preview')
    for item in fresh['files']:
        if item['destination_sha256'] not in (None,item['source_sha256']): raise NianxiangError('migration_conflict','target differs; nothing has been copied')
    config_item=next((x for x in fresh['files'] if x['name']=='local-config.json'),None)
    if config_item:
        config=read_json(config_item['source']);state=read_json(profile/'state.json')
        from validate_local_config import validate
        try:validate(config)
        except (ValueError,KeyError,TypeError):raise NianxiangError('invalid_configuration','legacy configuration is not compatible schema=5')
        if config.get('space_id')!=state['space_id']:raise NianxiangError('space_mismatch','legacy config belongs to another space; nothing copied')
    # Full preflight above; each copy uses exclusive creation to avoid racing overwrites.
    for item in fresh['files']:
        source=Path(item['source']);dest=Path(item['destination'])
        if dest.exists(): continue
        try:
            with source.open('rb') as src, dest.open('xb') as out:
                os.chmod(dest,0o600);shutil.copyfileobj(src,out);out.flush();os.fsync(out.fileno())
        except FileExistsError: raise NianxiangError('migration_conflict','destination appeared during copy; re-preview')
        if file_digest(dest)!=item['source_sha256']: raise NianxiangError('migration_changed','copy integrity failed; re-preview')
    state=read_json(profile/'state.json');state.update({'legacy_snapshot_status':'requires_source_verification','migration_consent':consent_id})
    write_json(profile/'state.json',state)
    return {'status':'migrated','copied_files':len(fresh['files']),'originals_retained':True,'source_verification_required':True}
