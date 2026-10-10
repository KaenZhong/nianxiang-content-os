#!/usr/bin/env python3
"""Verify public paths; optionally compare private deployment values without logging them."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import sys
from runtime.models import NianxiangError
from runtime.releases import build_manifest

PRIVATE_PATHS=tuple(Path('local')/n for n in ('local-config.json','user-profile.json','content-strategy-snapshot.md','expression-baseline-snapshot.md','rules.local.json','creative-skill-routes.md','native-skill-registry.md','companion-skill-registry.md','business-conventions.md'))
PUBLIC_EXAMPLES=(Path('local/local-config.example.json'),Path('local/user-profile.example.json'))
def collect_secrets(value,key=''):
    values=set()
    if isinstance(value,dict):
        for k,v in value.items():values.update(collect_secrets(v,k))
    elif isinstance(value,list):
        for v in value:values.update(collect_secrets(v,key))
    elif isinstance(value,str) and ('token' in key.lower() or key.lower()=='space_id' or key.lower().endswith('_url')) and len(value)>=8:values.add(value)
    return values

def main():
    root=Path(__file__).resolve().parents[1];p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package-dir',type=Path,default=root);p.add_argument('--private-source',type=Path,help='optional external maintainer directory containing local/local-config.json; values are never output')
    args=p.parse_args();package=args.package_dir.expanduser().resolve()
    try:
        build_manifest(package,'0.0.0')
        for item in PUBLIC_EXAMPLES:
            if not (package/item).is_file():raise NianxiangError('missing_example','public examples required')
        ignore=set((package/'.gitignore').read_text().splitlines())
        if any('/'+x.as_posix() not in ignore for x in PRIVATE_PATHS):raise NianxiangError('missing_exclusion','legacy private paths must remain ignored')
        if args.private_source:
            config=args.private_source/'local/local-config.json'
            secrets=collect_secrets(json.loads(config.read_text()))
            for f in package.rglob('*'):
                if f.is_file() and any(s.encode() in f.read_bytes() for s in secrets):raise NianxiangError('private_value_found','private deployment data found; omit it before release')
        print('OK: public-release exclusion checks passed')
        print('Private deployment comparison: '+('passed' if args.private_source else 'not requested; path checks only'))
        return 0
    except (NianxiangError,OSError,ValueError) as exc:print('FAIL: '+getattr(exc,'code','invalid_package'),file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
