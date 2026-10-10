"""Shared result states and private, atomic persistence."""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

SAVE_STATUSES = frozenset({'saved','pending','uncertain','conflict','blocked'})
class NianxiangError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code=code
        super().__init__(f'{code}: {message}')

def now(): return datetime.now(timezone.utc).isoformat()
def digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def file_digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read_json(path):
    try:
        if Path(path).is_symlink(): raise NianxiangError('invalid_path','private files must not be symlinks')
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError) as exc: raise NianxiangError('invalid_private_file','cannot read private JSON') from exc

def write_json(path, value):
    path=Path(path)
    if path.is_symlink(): raise NianxiangError('invalid_path','refusing symlink private file')
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,delete=False,prefix='.nianxiang-') as handle:
            temporary=Path(handle.name)
            os.chmod(temporary,0o600)
            json.dump(value,handle,ensure_ascii=False,indent=2);handle.write('\n');handle.flush();os.fsync(handle.fileno())
        os.replace(temporary,path)
    finally:
        if temporary and temporary.exists(): temporary.unlink()

@contextmanager
def profile_lock(profile):
    """Advisory single-machine lock, released by OS on crash; no distributed guarantee."""
    path=Path(profile)/'.runtime.lock'
    if path.is_symlink(): raise NianxiangError('invalid_path','lock must not be a symlink')
    with path.open('a+b') as handle:
        os.chmod(path,0o600)
        try:
            if os.name=='nt':
                import msvcrt
                if path.stat().st_size==0: handle.write(b'0');handle.flush()
                handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc: raise NianxiangError('busy','another process is managing this profile') from exc
        try: yield
        finally:
            if os.name=='nt': handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else: fcntl.flock(handle.fileno(),fcntl.LOCK_UN)

def result(status, message='', remote_object=None, readback_revision=None):
    if status not in SAVE_STATUSES: raise NianxiangError('invalid_result','unsupported save status')
    return {'status':status,'message':message,'remote_object':remote_object,'readback_revision':readback_revision}
