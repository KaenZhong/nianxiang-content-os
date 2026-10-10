"""Read-only discovery followed by path-bound, consented private-root initialization."""
from __future__ import annotations
import os
from pathlib import Path
import uuid
from .models import NianxiangError, read_json, write_json, digest, file_digest, now
from .paths import resolve_data_root

MARKER='data-root.json'

def canonical_root(skill_root,path):
    absolute=Path(path).expanduser().absolute()
    root=resolve_data_root(skill_root,absolute)
    if root!=absolute:
        raise NianxiangError('invalid_private_root','private root must not redirect')
    return root

def _valid_marker(value,root):
    return (isinstance(value,dict) and value.get('schema_version')==1
            and value.get('product')=='nianxiang-content-os'
            and value.get('data_root')==str(root)
            and value.get('environment') in ('local','cloud')
            and value.get('persistence') in ('local-user-directory','persistent-volume')
            and (value.get('environment')!='cloud' or value.get('persistence')=='persistent-volume')
            and isinstance(value.get('evidence'),str) and bool(value['evidence'].strip())
            and isinstance(value.get('consent'),str) and bool(value['consent'].strip()))

def _inspect(skill_root,path):
    root=canonical_root(skill_root,path)
    info={'path':str(root),'kind':'absent','profiles':0,'snapshot':None}
    if not root.exists():return info
    if not root.is_dir():info['kind']='conflict';return info
    if hasattr(os,'getuid') and root.stat().st_uid!=os.getuid():
        info['kind']='conflict';return info
    names=sorted(p.name for p in root.iterdir())
    stamps={'entries':names,'device':root.stat().st_dev,'inode':root.stat().st_ino}
    marker=root/MARKER
    if marker.exists() or marker.is_symlink():
        try:
            if not _valid_marker(read_json(marker),root):raise ValueError()
            stamps['marker']=file_digest(marker);info['kind']='initialized'
        except (NianxiangError,OSError,ValueError):info['kind']='conflict'
    elif not names:info['kind']='empty'
    elif names==['profiles'] and (root/'profiles').is_dir() and not (root/'profiles').is_symlink():
        info['kind']='legacy'
    else:info['kind']='conflict'
    profiles=root/'profiles'
    if profiles.exists() or profiles.is_symlink():
        if not profiles.is_dir() or profiles.is_symlink():info['kind']='conflict'
        else:
            for p in sorted(profiles.iterdir()):
                try:
                    if p.is_symlink() or not p.is_dir() or str(uuid.UUID(p.name))!=p.name:raise ValueError()
                    state=read_json(p/'state.json')
                    if not isinstance(state,dict) or state.get('profile_id')!=p.name or state.get('data_layout_version')!=1 or not state.get('account_id') or not state.get('space_id'):raise ValueError()
                    stamps[p.name]=file_digest(p/'state.json');info['profiles']+=1
                except (NianxiangError,OSError,ValueError,AttributeError):info['kind']='conflict'
    info['snapshot']=digest(stamps)
    return info

def scan_roots(skill_root,data_dir=None,known_roots=()):
    """Scan only configured/default/user-specified locations, never the whole home."""
    paths=[]
    if data_dir is not None:paths.append(data_dir)
    if os.environ.get('NIANXIANG_HOME'):paths.append(os.environ['NIANXIANG_HOME'])
    paths.append(Path.home()/'.nianxiang')
    paths.extend(known_roots)
    candidates=[];seen=set()
    for path in paths:
        root=canonical_root(skill_root,path)
        if str(root) in seen:continue
        seen.add(str(root));candidates.append(_inspect(skill_root,root))
    existing=[x for x in candidates if x['kind'] in ('initialized','legacy')]
    return {'status':'selection_required' if len(existing)>1 else 'existing_found' if existing else 'none_found',
            'candidates':candidates,'writes':0,'remote_calls':0}

def plan_installation(skill_root,data_dir=None,known_roots=(),environment='local',persistence=None,evidence=None):
    scan=scan_roots(skill_root,data_dir,known_roots)
    existing=[x for x in scan['candidates'] if x['kind'] in ('initialized','legacy')]
    if data_dir is not None:selected=_inspect(skill_root,data_dir)
    else:
        if len(existing)>1:raise NianxiangError('directory_selection_required','select an existing root explicitly')
        preferred=scan['candidates'][0]
        if preferred['kind']=='conflict':raise NianxiangError('directory_conflict','configured directory is not a reusable private root')
        selected=existing[0] if existing else preferred
    if selected['kind']=='conflict':raise NianxiangError('directory_conflict','do not adopt unrelated or invalid data')
    if environment not in ('local','cloud'):raise NianxiangError('invalid_input','unknown runtime environment')
    root=Path(selected['path'])
    if selected['kind']=='initialized':
        marker=read_json(root/MARKER)
        if marker['environment']!=environment:
            raise NianxiangError('environment_mismatch','directory environment changed; verify its persistent location first')
        environment=marker['environment'];persistence=marker['persistence'];evidence=marker['evidence']
    else:
        persistence=persistence or ('local-user-directory' if environment=='local' else 'unknown')
        evidence=evidence or ('当前本机用户选定的包外目录；未执行重启验证' if environment=='local' else '')
        if persistence not in ('local-user-directory','persistent-volume') or not str(evidence).strip() or (environment=='cloud' and persistence!='persistent-volume'):
            raise NianxiangError('persistence_required','confirm a durable cloud location and record actual evidence')
    if not root.parent.is_dir():raise NianxiangError('parent_missing','choose an existing user directory or persistent mount')
    plan={'schema_version':1,'data_root':str(root),'observed':selected,
          'action':'reuse' if selected['kind']=='initialized' else 'create' if selected['kind']=='absent' else 'adopt',
          'environment':environment,'persistence':persistence,'evidence':evidence,
          'confirmation_required':selected['kind']!='initialized',
          'stores':['connection and authorization state','task checkpoints','pending requests','rebuildable caches'],
          'restart_tested':False,'scan':scan}
    plan['plan_id']=digest(plan)
    return plan

def apply_installation(skill_root,plan,confirmed_path,consent):
    if not isinstance(plan,dict) or plan.get('schema_version')!=1 or plan.get('plan_id')!=digest({k:v for k,v in plan.items() if k!='plan_id'}):
        raise NianxiangError('invalid_plan','installation preview is invalid')
    root=canonical_root(skill_root,plan['data_root'])
    if confirmed_path!=str(root):
        raise NianxiangError('path_confirmation_mismatch','confirm the displayed full absolute path')
    if _inspect(skill_root,root)!=plan['observed']:
        raise NianxiangError('installation_changed','directory changed since preview; scan again')
    fresh=plan_installation(skill_root,root,environment=plan['environment'],persistence=plan['persistence'],evidence=plan['evidence'])
    if fresh['observed']!=plan['observed'] or fresh['action']!=plan['action']:
        raise NianxiangError('installation_changed','directory changed since preview; scan again')
    if fresh['action']=='reuse':
        require_initialized(skill_root,root)
        _verify_io(root)
        return {'status':'reused','data_root':str(root),'profiles_preserved':fresh['observed']['profiles']}
    if not isinstance(consent,str) or not consent.strip():
        raise NianxiangError('authorization_required','record actual path confirmation before initialization')
    if fresh['action']=='create':
        try:root.mkdir(mode=0o700)
        except FileExistsError:raise NianxiangError('installation_changed','directory appeared during initialization')
    if _inspect(skill_root,root)['kind'] not in ('empty','legacy'):
        raise NianxiangError('installation_changed','directory changed during initialization')
    # Adopt only an empty directory or recognized profile layout; never alter old profiles.
    if os.name!='nt':os.chmod(root,0o700)
    marker={'schema_version':1,'product':'nianxiang-content-os','data_root':str(root),
            'environment':fresh['environment'],'persistence':fresh['persistence'],
            'evidence':fresh['evidence'],'consent':consent,'created_at':now(),
            'persistence_verification':'declared','restart_tested':False}
    # Exclusive creation prevents replacing an initialization made by another installer.
    try:
        with (root/MARKER).open('x',encoding='utf-8') as handle:
            import json
            if os.name!='nt':os.chmod(root/MARKER,0o600)
            json.dump(marker,handle,ensure_ascii=False,indent=2);handle.write('\n')
            handle.flush();os.fsync(handle.fileno())
    except FileExistsError:raise NianxiangError('installation_changed','initialization already appeared; scan again')
    checked=require_initialized(skill_root,root)
    _verify_io(root)
    return {'status':'initialized','data_root':str(root),'profiles_preserved':fresh['observed']['profiles'],
            'persistence_verification':checked['persistence_verification'],'restart_tested':False}

def _verify_io(root):
    """Verify real write/readback capability rather than inferring it from a marker."""
    import tempfile
    probe=None
    try:
        with tempfile.NamedTemporaryFile(dir=root,prefix='.nianxiang-init-check-',delete=False) as handle:
            probe=Path(handle.name);handle.write(b'nianxiang-install-readback')
            handle.flush();os.fsync(handle.fileno())
        if probe.read_bytes()!=b'nianxiang-install-readback':raise OSError('readback mismatch')
        probe.unlink();probe=None
    except OSError as exc:
        raise NianxiangError('directory_not_writable','private root read/write verification failed') from exc
    finally:
        if probe and probe.exists():
            try:probe.unlink()
            except OSError:pass

def require_initialized(skill_root,root):
    inspected=_inspect(skill_root,root)
    if inspected['kind']=='conflict':raise NianxiangError('directory_conflict','invalid private root')
    if inspected['kind']!='initialized':
        raise NianxiangError('installation_required','scan and confirm the private root during installation first')
    return read_json(Path(inspected['path'])/MARKER)
