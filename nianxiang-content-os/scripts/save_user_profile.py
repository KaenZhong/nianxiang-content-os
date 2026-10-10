#!/usr/bin/env python3
"""Save a confirmed nickname to the selected Feishu personal source, never legacy JSON."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from runtime.paths import add_profile_args,resolve_profile
from runtime.models import NianxiangError,read_json
from runtime.feishu_cli import FeishuAdapter
from runtime.personal import save_preferred_name

def main():
    parser=argparse.ArgumentParser(description=__doc__);add_profile_args(parser)
    parser.add_argument('--nickname',required=True);parser.add_argument('--consent',help='actual long-term user instruction')
    parser.add_argument('--confirm-long-term',action='store_true',help='legacy compatibility flag; evidence is still required')
    parser.add_argument('--assistant-name',default='阿响');parser.add_argument('--overwrite',action='store_true');parser.add_argument('--output',type=Path,help='legacy output is unsupported; no local authority is created')
    args=parser.parse_args()
    try:
        if args.output or args.assistant_name!='阿响':raise NianxiangError('legacy_output_unsupported','use Feishu personal knowledge, not a local persona file')
        profile=resolve_profile(Path(__file__).resolve().parents[1],args.data_dir,args.profile)
        result=save_preferred_name(profile,FeishuAdapter(read_json(profile/'local-config.json')),args.nickname,args.consent)
        print(json.dumps({k:v for k,v in result.items() if k in ('status','code','message','readback_revision')},ensure_ascii=False));return 0 if result['status']=='saved' else 2
    except NianxiangError as exc:print(json.dumps({'status':'blocked','code':exc.code}));return 2
if __name__=='__main__':raise SystemExit(main())
