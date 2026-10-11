#!/usr/bin/env python3
"""Detached read-only refresh, invoked only by an explicitly selected profile's use."""
import argparse
import time
from pathlib import Path
from runtime.models import NianxiangError, read_json, write_json, profile_lock
from runtime.paths import resolve_profile
from runtime.sync import sync_context, sync_status, worker_lock
from runtime.feishu_cli import FeishuAdapter

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile-dir',type=Path,required=True);parser.add_argument('--run-id',required=True)
    parser.add_argument('knowledge_ids',nargs='+');args=parser.parse_args()
    try:
        selected=args.profile_dir.expanduser().absolute()
        profile=resolve_profile(Path(__file__).resolve().parents[1],selected.parent.parent,selected.name)
        if profile!=selected:raise NianxiangError('profile_mismatch','worker path must select an existing profile')
        with worker_lock(profile):
            for attempt in range(20):
                try:
                    with profile_lock(profile), profile_lock(profile,".context-cache.lock",blocking=True):
                        state=sync_status(profile)
                        if state.get('run_id')!=args.run_id:return 1
                        state['status']='running';write_json(profile/'context-sync.json',state)
                    break
                except NianxiangError as exc:
                    if exc.code!='busy' or attempt==19:raise
                    time.sleep(0.05)
            result=sync_context(profile,args.knowledge_ids,FeishuAdapter(read_json(profile/'local-config.json')),args.run_id)
            return 0 if result['status']=='synced' else 1
    except (NianxiangError,OSError,ValueError):return 1

if __name__=='__main__':raise SystemExit(main())
