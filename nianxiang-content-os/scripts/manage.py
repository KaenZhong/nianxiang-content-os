#!/usr/bin/env python3
"""Manage one explicitly selected private profile; never infer consent or credentials."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import sys
from runtime.models import NianxiangError,read_json,write_json,profile_lock
from runtime.paths import resolve_data_root,resolve_profile,create_profile,plan_migration,apply_migration
from runtime.installation import scan_roots,plan_installation,apply_installation,require_initialized
from runtime.feishu_cli import FeishuAdapter
from runtime.knowledge import load_context,save_change,reconcile_pending,authorize_request,profile_state,verify_account,verify_node
from runtime.bootstrap import plan_bootstrap,resume_bootstrap,authorize_bootstrap,verify_fields
from runtime.releases import build_manifest,verify_release,apply_release,rollback_release,recover_release,check_update,installation_state_path,installation_status,plan_name_migration,apply_name_migration
from runtime.personal import read_personal_context,plan_personal_migration,apply_personal_migration,export_personal_context,save_preferred_name
from runtime.tasks import create_task,update_task,resume_task
from validate_local_config import validate

SKILL_ROOT=Path(__file__).resolve().parents[1]

def emit(value):print(json.dumps(value,ensure_ascii=False,indent=2))
def consent(args):
    if not str(getattr(args,'consent',None) or '').strip():raise NianxiangError('authorization_required','record the actual user instruction with --consent')
    return args.consent

def verify_profile(profile):
    with profile_lock(profile):
        state=profile_state(profile,require_active=False)
        # A failed re-verification must revoke an earlier ready state.
        state['active']=False;write_json(profile/'state.json',state)
        config=read_json(profile/'local-config.json');validate(config)
        if config['space_id']!=state['space_id']:raise NianxiangError('space_mismatch','config and selected profile differ')
        adapter=FeishuAdapter(config);verify_account(state,adapter)
        for key in config['knowledge_map']:verify_node(state,config,{'knowledge_id':key},adapter)
        base=config['knowledge_map']['operations.base'];tables=adapter.list_tables(base)
        structure=read_json(SKILL_ROOT/'assets/templates/knowledge-structure.json')
        for spec in structure['tables']:
            table=config['base_tables'][spec['id']]
            matches=[t for t in tables if t.get('name')==spec['title']]
            if len(matches)>1:raise NianxiangError('ambiguous_table','duplicate required table title; select and resolve before activation')
            if len(matches)!=1 or matches[0].get('id')!=table['table_id'] or table['expected_title']!=spec['title']:raise NianxiangError('target_mismatch','configured table differs from source')
            verify_fields(adapter,base,matches[0],spec)
        verify_account(state,adapter)
        state['active']=True;write_json(profile/'state.json',state)
        return {'status':'ready','knowledge_mappings':12,'tables':4}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path);parser.add_argument('--profile',help='private UUID, not the lark-cli login profile')
    groups=parser.add_subparsers(dest='group',required=True)
    install=groups.add_parser('install');ins=install.add_subparsers(dest='action',required=True)
    for action in ('scan','plan'):
        p=ins.add_parser(action);p.add_argument('--known-root',type=Path,action='append',default=[])
        if action=='plan':
            p.add_argument('--environment',choices=['local','cloud'],required=True)
            p.add_argument('--persistence',choices=['local-user-directory','persistent-volume','unknown','temporary'])
            p.add_argument('--evidence');p.add_argument('--output',type=Path)
    p=ins.add_parser('apply');p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--confirmed-path',required=True);p.add_argument('--consent')
    doctor=groups.add_parser('doctor');doctor.add_argument('--offline',action='store_true')
    profile=groups.add_parser('profile');ps=profile.add_subparsers(dest='action',required=True)
    ps.add_parser('list');p=ps.add_parser('create');entry=p.add_mutually_exclusive_group(required=True);entry.add_argument('--space-id');entry.add_argument('--entry-url');p.add_argument('--consent',required=True);ps.add_parser('verify')
    migration=groups.add_parser('migration');ms=migration.add_subparsers(dest='action',required=True)
    p=ms.add_parser('plan');p.add_argument('--legacy-dir',type=Path,required=True);p.add_argument('--output',type=Path)
    p=ms.add_parser('apply');p.add_argument('--plan',type=Path,required=True);p.add_argument('--consent',required=True)
    bootstrap=groups.add_parser('bootstrap');bs=bootstrap.add_subparsers(dest='action',required=True)
    p=bs.add_parser('plan');p.add_argument('--output',type=Path)
    p=bs.add_parser('apply');p.add_argument('--plan',type=Path,required=True);p.add_argument('--consent',required=True)
    knowledge=groups.add_parser('knowledge');ks=knowledge.add_subparsers(dest='action',required=True)
    p=ks.add_parser('read');p.add_argument('knowledge_ids',nargs='+');p.add_argument('--refresh',action='store_true');p.add_argument('--show-private-content',action='store_true')
    p=ks.add_parser('save');p.add_argument('--request',type=Path,required=True);p.add_argument('--consent',required=True)
    p=ks.add_parser('reconcile');p.add_argument('--operation-id',required=True)
    ks.add_parser('pending')
    personal=groups.add_parser('personal');xs=personal.add_subparsers(dest='action',required=True)
    p=xs.add_parser('read');p.add_argument('--refresh',action='store_true');p.add_argument('--allow-stale',action='store_true');p.add_argument('--show-private-content',action='store_true')
    p=xs.add_parser('migration-plan');p.add_argument('--output',type=Path)
    p=xs.add_parser('migration-apply');p.add_argument('--plan',type=Path,required=True);p.add_argument('--consent',required=True)
    p=xs.add_parser('export');p.add_argument('--kinds',nargs='+',choices=['user','memory'],required=True)
    p=xs.add_parser('name');p.add_argument('--nickname',required=True);p.add_argument('--consent',required=True)
    task=groups.add_parser('task');ts=task.add_subparsers(dest='action',required=True)
    p=ts.add_parser('create');p.add_argument('--request',type=Path,required=True);p.add_argument('--consent',required=True)
    p=ts.add_parser('update');p.add_argument('--task-id',required=True);p.add_argument('--patch',type=Path,required=True);p.add_argument('--expected-version',type=int,required=True);p.add_argument('--consent',required=True)
    p=ts.add_parser('resume');p.add_argument('--task-id',required=True);p.add_argument('--show-private-content',action='store_true')
    release=groups.add_parser('release');rs=release.add_subparsers(dest='action',required=True)
    p=rs.add_parser('manifest');p.add_argument('--source-dir',type=Path,default=SKILL_ROOT);p.add_argument('--version',required=True)
    p=rs.add_parser('verify');p.add_argument('--archive',type=Path,required=True);p.add_argument('--manifest',type=Path)
    p=rs.add_parser('check-update');p.add_argument('--manifest',type=Path,default=SKILL_ROOT/'release-manifest.json')
    p=rs.add_parser('migrate-plan');p.add_argument('--old-root',type=Path,required=True);p.add_argument('--new-root',type=Path,required=True);p.add_argument('--output',type=Path)
    p=rs.add_parser('migrate-apply');p.add_argument('--plan',type=Path,required=True);p.add_argument('--archive',type=Path,required=True);p.add_argument('--consent',required=True)
    for action in ('apply','rollback','recover','status'):
        p=rs.add_parser(action);p.add_argument('--skill-root',type=Path,required=True)
        if action!='status':p.add_argument('--consent',required=True)
        if action=='apply':p.add_argument('--archive',type=Path,required=True)
    args=parser.parse_args()
    try:
        if args.group=='install':
            if args.action=='scan':outcome=scan_roots(SKILL_ROOT,args.data_dir,args.known_root)
            elif args.action=='plan':
                outcome=plan_installation(SKILL_ROOT,args.data_dir,args.known_root,args.environment,args.persistence,args.evidence)
                if args.output:
                    output=args.output.expanduser().absolute();selected=Path(outcome['data_root'])
                    if output==selected or selected in output.parents or output.resolve()!=output:
                        raise NianxiangError('invalid_path','preview belongs outside the proposed private directory')
                    private_output(output,outcome)
            else:outcome=apply_installation(SKILL_ROOT,read_json(args.plan),args.confirmed_path,args.consent)
            emit(outcome);return 0
        if args.group=='release':
            if args.action=='manifest':
                if installation_state_path(args.source_dir).exists():raise NianxiangError('managed_core','do not regenerate the baseline of a managed installation')
                manifest=build_manifest(args.source_dir,args.version);write_json(args.source_dir/'release-manifest.json',manifest)
                outcome={'status':'manifest_created','version':manifest['version'],'public_files':len(manifest['files'])}
            elif args.action=='verify':
                checked=verify_release(args.archive,read_json(args.manifest) if args.manifest else None)
                outcome={k:v for k,v in checked.items() if k!='manifest'}
            elif args.action=='check-update':outcome=check_update(read_json(args.manifest))
            elif args.action in ('migrate-plan','migrate-apply'):
                root=resolve_data_root(SKILL_ROOT,args.data_dir);profile=resolve_profile(SKILL_ROOT,root,args.profile)
                if args.action=='migrate-plan':
                    plan=plan_name_migration(args.old_root,args.new_root,profile)
                    if args.output and plan['status']=='preview':
                        output=Path(args.output).expanduser().absolute()
                        protected=[profile,args.old_root.absolute(),args.new_root.absolute(),installation_state_path(args.old_root).parent,installation_state_path(args.new_root).parent]
                        if output.resolve()!=output or any(output==p or p in output.parents for p in protected):raise NianxiangError('invalid_path','migration preview belongs outside cores, journals and profile')
                        private_output(output,plan)
                    outcome={k:v for k,v in plan.items() if k in ('status','message','plan_id','steps')}
                    outcome['plan_path']=str(args.output) if args.output else None
                else:
                    plan=read_json(args.plan)
                    if Path(plan.get('profile_dir','')).absolute()!=profile:raise NianxiangError('profile_mismatch','name migration preview targets another profile')
                    outcome=apply_name_migration(plan,args.archive,consent(args))
            elif args.action=='status':outcome=installation_status(args.skill_root)
            elif args.action=='apply':
                root=resolve_data_root(SKILL_ROOT,args.data_dir);profile=resolve_profile(SKILL_ROOT,root,args.profile)
                outcome=apply_release(args.archive,args.skill_root,profile,consent(args))
            else:
                action=rollback_release if args.action=='rollback' else recover_release
                outcome=action(args.skill_root,installation_state_path(args.skill_root),consent(args))
            emit(outcome)
            return 0 if outcome['status'] in ('manifest_created','verified','not_configured','unmanaged','active','aborted','updated','up_to_date','rolled_back','preview','migrated','legacy_import_required') else 1
        root=resolve_data_root(SKILL_ROOT,args.data_dir)
        if args.group=='doctor':
            report={'python':sys.version.split()[0],'lark_cli_available':bool(shutil.which('lark-cli')),'private_root_outside_skill':True,'profile_selected':bool(args.profile),'live_read_write':'not_tested','release_management':'local_import_available'}
            if args.profile:report['profile_exists']=resolve_profile(SKILL_ROOT,root,args.profile).exists()
            if not args.offline:report['current_user_verified']=bool(FeishuAdapter({'space_id':''}).get_account()['account_id'])
            emit(report);return 0
        if args.group=='profile' and args.action=='list':
            profiles=[]
            for p in sorted((root/'profiles').glob('*')) if (root/'profiles').exists() else []:
                if p.is_dir() and not p.is_symlink() and (p/'state.json').exists():
                    state=read_json(p/'state.json');profiles.append({'profile_id':state['profile_id'],'active':state.get('active',False)})
            emit({'profiles':profiles,'selection':'explicit_required'});return 0
        if args.group=='profile' and args.action=='create':
            require_initialized(SKILL_ROOT,root)
            consent(args);adapter=FeishuAdapter({'space_id':args.space_id or ''});account=adapter.get_account()
            space=args.space_id
            if args.entry_url:space=adapter.get_node({'node_token':args.entry_url}).get('space_id')
            if not space:raise NianxiangError('space_missing','entry URL did not resolve a space')
            pid=create_profile(root,account['account_id'],space);emit({'status':'created','profile_id':pid,'active':False});return 0
        profile=resolve_profile(SKILL_ROOT,root,args.profile)
        if args.group=='profile':emit(verify_profile(profile));return 0
        if args.group=='task':
            if args.action=='create':outcome=create_task(profile,read_json(args.request),consent(args))
            elif args.action=='update':outcome=update_task(profile,args.task_id,read_json(args.patch),args.expected_version,consent(args))
            else:
                outcome=resume_task(profile,args.task_id,FeishuAdapter(read_json(profile/'local-config.json')))
                if not args.show_private_content:outcome={k:v for k,v in outcome.items() if k in ('status','code','remote_writes','terminal')}
            emit(outcome);return 0 if outcome['status'] in ('created','updated','ready') else 1
        if args.group=='personal':
            adapter=FeishuAdapter(read_json(profile/'local-config.json'))
            if args.action=='read':
                outcome=read_personal_context(profile,adapter,args.refresh,args.allow_stale)
                if not args.show_private_content:outcome={k:v for k,v in outcome.items() if k in ('status','code','migration_groups')}
            elif args.action=='migration-plan':
                plan=plan_personal_migration(profile,adapter)
                if args.output and plan['status']=='preview':private_output(args.output,plan)
                outcome={k:v for k,v in plan.items() if k in ('status','code','needs_confirmation')};outcome['plan_path']=str(args.output) if args.output else None
            elif args.action=='migration-apply':
                full=apply_personal_migration(profile,read_json(args.plan),adapter,consent(args))
                outcome={k:v for k,v in full.items() if k in ('status','code','originals_retained')}
                if 'groups' in full:outcome['groups']={k:{f:v for f,v in x.items() if f in ('status','message','readback_revision')} for k,x in full['groups'].items()}
            elif args.action=='name':
                full=save_preferred_name(profile,adapter,args.nickname,consent(args));outcome={k:v for k,v in full.items() if k in ('status','code','message','readback_revision')}
            else:
                context=read_personal_context(profile,adapter,True);outcome=export_personal_context(profile,context,args.kinds)
            emit(outcome);return 0 if outcome['status'] in ('ready','empty','stale','preview','saved','exported') else 1

        if args.group=='migration':
            if args.action=='plan':
                plan=plan_migration(args.legacy_dir,profile)
                if args.output:private_output(args.output,plan)
                emit({'status':'preview','files':[{k:v for k,v in x.items() if k not in ('source','destination')} for x in plan['files']],'plan_path':str(args.output) if args.output else None})
            else:
                plan=read_json(args.plan)
                if Path(plan['profile_dir']).resolve()!=profile:raise NianxiangError('profile_mismatch','migration plan targets another profile')
                emit(apply_migration(plan,consent(args)))
            return 0
        state=profile_state(profile,require_active=False)
        if args.group=='bootstrap':
            adapter=FeishuAdapter({'space_id':state['space_id']})
            if args.action=='plan':
                structure=read_json(SKILL_ROOT/'assets/templates/knowledge-structure.json');structure.update(account_id=state['account_id'],space_id=state['space_id'])
                plan=plan_bootstrap(adapter,structure);output=args.output or profile/'bootstrap-plan.json';private_output(output,plan)
                emit({'status':'preview','items':plan['items'],'plan_path':str(output),'writes_to_feishu':0})
            else:
                plan=read_json(args.plan);outcome=resume_bootstrap(profile,plan,adapter,authorize_bootstrap(plan,consent(args)));emit(outcome)
                return 0 if outcome['status']=='ready' else 1
            return 0
        adapter=FeishuAdapter(read_json(profile/'local-config.json'))
        if args.action=='read':
            outcome=load_context(profile,args.knowledge_ids,adapter,args.refresh)
            if not args.show_private_content:
                outcome={'knowledge':{k:{f:v for f,v in item.items() if f in ('status','cached','current','stale','read_at','fact_status')} for k,item in outcome['knowledge'].items()}}
        elif args.action=='save':
            request=read_json(args.request);request['authorization']=authorize_request(profile,request,consent(args));outcome=save_change(profile,request,adapter)
        elif args.action=='reconcile':outcome=reconcile_pending(profile,args.operation_id,adapter)
        else:
            outcome={'operations':[{'operation_id':p.stem,'status':read_json(p).get('status')} for p in (profile/'pending').glob('*.json') if read_json(p).get('status')!='saved']}
        # CLI status logs never contain remote IDs, source tokens or private body.
        if 'status' in outcome:outcome={k:v for k,v in outcome.items() if k in ('status','message','readback_revision','snapshot_refresh')}
        emit(outcome)
        return 0 if outcome.get('status','saved')=='saved' else 1
    except (NianxiangError,ValueError,KeyError,OSError) as exc:
        emit({'status':'blocked','message':getattr(exc,'code','invalid_input')});return 2

def private_output(path,value):
    path=Path(path).expanduser().resolve()
    if path==SKILL_ROOT or SKILL_ROOT in path.parents:raise NianxiangError('invalid_path','private plan belongs outside the public Skill')
    write_json(path,value)

if __name__=='__main__':raise SystemExit(main())
