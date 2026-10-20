import copy
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from personal_support import Fixture, collaboration
from runtime.models import NianxiangError, read_json, write_json
from runtime.knowledge import load_context, save_change, authorize_request
from runtime.personal import read_personal_context
try:
    from runtime.sync import read_context, sync_context, request_sync
except ImportError:
    read_context=sync_context=request_sync=None

class ContextSync(Fixture, unittest.TestCase):
    def seed(self, keys=('content.strategy',)):
        load_context(self.profile,list(keys),self.adapter,True)
    def test_new_task_checks_even_recent_cache_and_returns_changed_source(self):
        self.seed();self.adapter.docs['content.strategy'].update(revision=2,content='new rule')
        out=read_context(self.profile,['content.strategy'],self.adapter)
        self.assertEqual(out['knowledge']['content.strategy']['content'],'new rule')
        self.assertTrue(out['knowledge']['content.strategy']['current'])

    def test_default_read_reuses_unchanged_body_after_metadata_check(self):
        self.seed();calls=[]
        def revision(key):
            calls.append(key);return {'document_id':self.adapter.docs[key]['obj_token'],'revision':1}
        self.adapter.get_revision=revision
        self.adapter.read=lambda key:self.fail('unchanged body downloaded')
        out=read_context(self.profile,['content.strategy'],self.adapter)
        self.assertEqual(calls,['content.strategy'])
        self.assertTrue(out['knowledge']['content.strategy']['current'])

    def test_network_fallback_is_explicit_and_never_satisfies_refresh(self):
        self.seed();self.adapter.offline=True
        out=read_context(self.profile,['content.strategy'],self.adapter)
        self.assertEqual(out['sync']['status'],'deferred')
        self.assertFalse(out['knowledge']['content.strategy']['current'])
        self.assertEqual(out['knowledge']['content.strategy']['status'],'offline_fallback')
        with self.assertRaisesRegex(NianxiangError,'offline'):
            read_context(self.profile,['content.strategy'],self.adapter,require_latest=True)

    def test_external_change_invalidation_blocks_offline_old_copy(self):
        from runtime.sync import mark_source_changed
        self.seed();mark_source_changed(self.profile,['content.strategy'])
        self.adapter.offline=True
        with self.assertRaisesRegex(NianxiangError,'source_changed'):
            read_context(self.profile,['content.strategy'],self.adapter)
        self.adapter.offline=False
        self.adapter.docs['content.strategy'].update(revision=2,content='new')
        self.assertTrue(read_context(self.profile,['content.strategy'],self.adapter)['knowledge']['content.strategy']['current'])

    def test_partial_new_revision_cannot_fall_back_to_older_known_copy(self):
        self.seed(('content.strategy','audience.needs'))
        self.adapter.get_revision=lambda key:{'document_id':self.adapter.docs[key]['obj_token'],'revision':2}
        original=self.adapter.read
        def read(key):
            if key=='audience.needs':raise NianxiangError('offline','network interrupted')
            return original(key)
        self.adapter.docs['content.strategy'].update(revision=2,content='new')
        self.adapter.read=read
        with self.assertRaisesRegex(NianxiangError,'source_changed'):
            read_context(self.profile,['content.strategy','audience.needs'],self.adapter)

    def test_saved_remote_with_failed_cache_publish_stays_invalidated(self):
        self.seed()
        req={'operation_id':'cache-failure','target':{'knowledge_id':'content.strategy','obj_type':'docx'},'action':'append','base_revision':1,'content':{'text':'saved change'}}
        req['authorization']=authorize_request(self.profile,req,'save this test change')
        with patch('runtime.sync.publish_snapshots',side_effect=NianxiangError('cache_changed','racing cache')):
            out=save_change(self.profile,req,self.adapter)
        self.assertEqual(out['status'],'saved')
        self.assertEqual(out['snapshot_refresh'],'deferred')
        self.assertEqual(read_json(self.profile/'pending/cache-failure.json')['result']['snapshot_refresh'],'deferred')
        with self.assertRaisesRegex(NianxiangError,'source_changed'):
            read_context(self.profile,['content.strategy'],cache_only=True)
        self.assertEqual(self.adapter.writes,1)
    def test_warm_read_does_not_contact_remote(self):
        self.seed();self.adapter.get_account=lambda: self.fail('foreground contacted remote')
        self.assertIsNotNone(read_context, 'cache-first context service is missing')
        out=read_context(self.profile,['content.strategy'],self.adapter,cache_only=True)
        self.assertEqual(out['knowledge']['content.strategy']['content'],'synthetic content.strategy')
        self.assertFalse(out['knowledge']['content.strategy']['current'])
    def test_expired_cache_is_checked_in_foreground_without_worker(self):
        self.seed(); path=self.profile/'snapshots/context.json';bundle=read_json(path);old=bundle['knowledge']['content.strategy']
        old['read_at']=old['checked_at']=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat();write_json(path,bundle)
        self.assertIsNotNone(read_context)
        launches=[]
        def launch(profile,keys):
            launches.append(keys);sync_context(profile,keys,self.adapter)
            return {'status':'started'}
        self.adapter.docs['content.strategy'].update(revision=2,content='new')
        out=read_context(self.profile,['content.strategy'],self.adapter,launcher=launch)
        self.assertEqual(out['knowledge']['content.strategy']['revision'],2)
        self.assertEqual(len(launches),0)
        self.assertEqual(read_context(self.profile,['content.strategy'],cache_only=True)['knowledge']['content.strategy']['revision'],2)
    def test_metadata_unchanged_skips_body_download(self):
        self.seed(); self.assertIsNotNone(sync_context)
        self.adapter.get_revision=lambda key:{'document_id':self.adapter.docs[key]['obj_token'],'revision':1}
        self.adapter.read=lambda key:self.fail('unchanged document body downloaded')
        out=sync_context(self.profile,['content.strategy'],self.adapter)
        self.assertEqual(out['status'],'synced')
        self.assertEqual(out['changed'],[])
    def test_failed_bundle_does_not_publish_partial_results(self):
        self.seed(('content.strategy','audience.needs'));self.assertIsNotNone(sync_context)
        self.adapter.docs['content.strategy'].update(revision=2,content='new')
        read=self.adapter.read
        def failing(key):
            if key=='audience.needs':raise NianxiangError('offline','unavailable')
            return read(key)
        self.adapter.read=failing
        self.assertEqual(sync_context(self.profile,['content.strategy','audience.needs'],self.adapter)['status'],'deferred')
        self.assertEqual(read_json(self.profile/'snapshots/context.json')['knowledge']['content.strategy']['revision'],1)
        with self.assertRaisesRegex(NianxiangError,'source_changed'):
            read_context(self.profile,['content.strategy'],cache_only=True)
    def test_known_account_mismatch_blocks_cached_personalization(self):
        self.seed();self.assertIsNotNone(sync_context);self.adapter.account='another'
        self.assertEqual(sync_context(self.profile,['content.strategy'],self.adapter)['status'],'blocked')
        with self.assertRaisesRegex(NianxiangError,'account_mismatch'):
            read_context(self.profile,['content.strategy'],cache_only=True)
    def test_foreign_or_corrupt_cache_is_not_reused(self):
        self.seed();self.assertIsNotNone(read_context)
        path=self.profile/'snapshots/context.json';bundle=read_json(path);bundle['knowledge']['content.strategy']['content']='tampered';write_json(path,bundle)
        with self.assertRaises(NianxiangError):read_context(self.profile,['content.strategy'],cache_only=True)
    def test_background_does_not_regress_successful_write(self):
        self.seed();self.assertIsNotNone(sync_context)
        actual_read=self.adapter.read; done=[]
        def racing(key):
            older=actual_read(key)
            if not done:
                done.append(True)
                req={'operation_id':'race-save','target':{'knowledge_id':key,'obj_type':'docx'},'action':'append','base_revision':1,'content':{'text':'saved change'}}
                req['authorization']=authorize_request(self.profile,req,'save this exact test change')
                self.adapter.read=actual_read
                self.assertEqual(save_change(self.profile,req,self.adapter)['status'],'saved')
                self.adapter.read=racing
            return older
        self.adapter.read=racing
        sync_context(self.profile,['content.strategy'],self.adapter)
        self.assertEqual(read_context(self.profile,['content.strategy'],cache_only=True)['knowledge']['content.strategy']['revision'],2)
    def test_personal_explicit_cache_only_makes_no_remote_calls(self):
        import json
        self.adapter.docs['ip.profile']['content']='NIANXIANG_COLLABORATION_V1='+json.dumps(collaboration())
        self.seed(('ip.profile','content.methods'))
        self.adapter.get_account=lambda:self.fail('personal default contacted remote')
        out=read_personal_context(self.profile,self.adapter,cache_only=True)
        self.assertEqual(out['collaboration']['preferred_name'],'测试作者')
    def test_launcher_deduplicates_and_is_detached(self):
        self.assertIsNotNone(request_sync)
        with patch('runtime.sync.subprocess.Popen') as popen:
            popen.return_value.pid=123
            first=request_sync(self.profile,['content.strategy'])
            second=request_sync(self.profile,['content.strategy'])
            self.assertEqual(first['status'],'started');self.assertEqual(second['status'],'running')
            self.assertEqual(popen.call_count,1)
            self.assertTrue(popen.call_args.kwargs.get('start_new_session'))
            self.assertNotIn('shell',popen.call_args.kwargs)

    def test_detached_worker_publishes_after_foreground_return(self):
        import json, os, subprocess, time
        from runtime.sync import CONTEXT_KEYS
        self.seed(CONTEXT_KEYS)
        cache=self.profile/'snapshots/context.json';bundle=read_json(cache)
        for item in bundle['knowledge'].values():item['checked_at']='2020-01-01T00:00:00+00:00'
        write_json(cache,bundle)
        self.adapter.docs['content.strategy'].update(revision=2,content='worker changed source')
        root=Path(self.tmp.name).resolve();source=root/'synthetic-docs.json';write_json(source,self.adapter.docs)
        executable=root/'lark-cli'
        executable.write_text('#!'+sys.executable+'\n'+
            "import json,sys,time\n"+
            "docs=json.load(open("+repr(str(source))+"))\n"+
            "args=sys.argv[1:];time.sleep(0.08)\n"+
            "if args[:2]==['auth','status']:\n print(json.dumps({'verified':True,'identities':{'user':{'verified':True,'openId':'account-a'}}}))\n"+
            "else:\n"+
            " if args[:2]==['wiki','+node-get']:\n  token=args[args.index('--node-token')+1].split('/')[-1];data={'node':next(d for d in docs.values() if d['node_token']==token)}\n"+
            " elif args[:2]==['api','GET']:\n  token=args[2].split('/')[-1];d=next(d for d in docs.values() if d['obj_token']==token);data={'document':{'document_id':token,'revision_id':d['revision']}}\n"+
            " elif args[:2]==['docs','+fetch']:\n  token=args[args.index('--doc')+1];d=next(d for d in docs.values() if d['obj_token']==token);data={'document':{'document_id':token,'revision_id':d['revision'],'content':d['content']}}\n"+
            " else:raise RuntimeError('unexpected write or command')\n"+
            " print(json.dumps({'ok':True,'identity':'user','data':data}))\n")
        executable.chmod(0o700);processes=[];real_popen=subprocess.Popen
        def capture(*args,**kwargs):
            child=real_popen(*args,**kwargs);processes.append(child);return child
        with patch.dict(os.environ,{'PATH':str(root)+os.pathsep+os.environ['PATH']}), patch('runtime.sync.subprocess.Popen',side_effect=capture):
            started=time.monotonic();out=read_context(self.profile,['content.strategy'],self.adapter,cache_only=True)
            launched=request_sync(self.profile,list(CONTEXT_KEYS))
            self.assertLess(time.monotonic()-started,0.8)
            self.assertEqual(out['knowledge']['content.strategy']['revision'],1)
            self.assertEqual(launched['status'],'started')
        child=processes[0]
        try:self.assertEqual(child.wait(timeout=12),0)
        finally:
            if child.poll() is None:child.kill();child.wait(timeout=2)
        result=read_context(self.profile,['content.strategy'],cache_only=True)
        self.assertEqual(result['knowledge']['content.strategy']['revision'],2)

    def test_known_invalid_source_remains_blocked_while_retry_is_starting(self):
        self.seed();self.adapter.account='other'
        sync_context(self.profile,['content.strategy'],self.adapter)
        with patch('runtime.sync.subprocess.Popen') as popen:
            popen.return_value.pid=123;request_sync(self.profile,['content.strategy'])
        with self.assertRaisesRegex(NianxiangError,'account_mismatch'):
            read_context(self.profile,['content.strategy'],cache_only=True)

    def test_explicit_refresh_can_repair_corrupted_snapshot(self):
        self.seed();path=self.profile/'snapshots/context.json';bundle=read_json(path)
        bundle['knowledge']['content.strategy']['content']='corrupted';write_json(path,bundle)
        out=read_context(self.profile,['content.strategy'],self.adapter,require_latest=True)
        self.assertTrue(out['knowledge']['content.strategy']['current'])

    def test_task_resume_with_warm_local_context_makes_no_remote_calls(self):
        from runtime.tasks import create_task,resume_task
        self.seed();doc=self.adapter.docs['content.strategy']
        task=create_task(self.profile,{'kind':'topics','mode':'discussion','goal':'topics',
            'context_refs':[{'knowledge_id':'content.strategy','obj_token':doc['obj_token'],'revision':1}]},'track this test task')
        self.adapter.get_account=lambda:self.fail('warm task resume contacted remote')
        self.assertEqual(resume_task(self.profile,task['task_id'],self.adapter)['status'],'ready')

    def test_live_read_and_save_account_errors_invalidate_warm_cache(self):
        for action in ('read','save'):
            self.setUp();self.seed();self.adapter.account='another'
            if action=='read':
                with self.assertRaises(NianxiangError):load_context(self.profile,['content.strategy'],self.adapter,True)
            else:
                req={'operation_id':'invalid-user','target':{'knowledge_id':'content.strategy','obj_type':'docx'},'action':'append','base_revision':1,'content':{'text':'text'}}
                req['authorization']=authorize_request(self.profile,req,'save this test patch')
                self.assertEqual(save_change(self.profile,req,self.adapter)['status'],'blocked')
            with self.assertRaisesRegex(NianxiangError,'account_mismatch'):
                read_context(self.profile,['content.strategy'],cache_only=True)

    def test_refreshing_strategy_does_not_unblock_denied_expression(self):
        self.seed(('content.strategy','expression.baseline'));original=self.adapter.get_node
        def denied(target):
            if target['knowledge_id']=='expression.baseline':raise NianxiangError('permission_denied','denied')
            return original(target)
        self.adapter.get_node=denied
        self.assertEqual(sync_context(self.profile,['expression.baseline'],self.adapter)['status'],'blocked')
        self.assertEqual(sync_context(self.profile,['content.strategy'],self.adapter)['status'],'synced')
        with self.assertRaisesRegex(NianxiangError,'permission_denied'):
            read_context(self.profile,['expression.baseline'],cache_only=True)

    def test_sync_records_identity_error_during_save_lock_contention(self):
        from runtime.models import profile_lock
        self.seed();self.adapter.account='another'
        with profile_lock(self.profile):
            self.assertEqual(sync_context(self.profile,['content.strategy'],self.adapter)['status'],'blocked')
        with self.assertRaisesRegex(NianxiangError,'account_mismatch'):
            read_context(self.profile,['content.strategy'],cache_only=True)

    def test_newly_observed_error_prevents_an_older_refresh_publishing(self):
        from runtime.sync import invalidate_sources
        self.seed();original=self.adapter.read
        def newly_invalid(key):
            out=original(key);invalidate_sources(self.profile,[key],'target_mismatch');return out
        self.adapter.read=newly_invalid
        self.assertEqual(sync_context(self.profile,['content.strategy'],self.adapter)['status'],'deferred')
        with self.assertRaisesRegex(NianxiangError,'target_mismatch'):
            read_context(self.profile,['content.strategy'],cache_only=True)

    def test_mixed_read_preserves_local_mode_and_requires_live_operational_source(self):
        self.seed(('content.strategy','content.archives'))
        self.adapter.offline=True
        with self.assertRaisesRegex(NianxiangError,'offline'):
            read_context(self.profile,['content.strategy','content.archives'],self.adapter,require_latest=True)
        with self.assertRaisesRegex(NianxiangError,'offline'):
            read_context(self.profile,['content.strategy','content.archives'],self.adapter)

    def test_mixed_read_cannot_bypass_known_invalid_context(self):
        self.seed(('content.strategy','content.archives'));self.adapter.account='another'
        sync_context(self.profile,['content.strategy'],self.adapter);self.adapter.offline=True
        with self.assertRaisesRegex(NianxiangError,'account_mismatch'):
            read_context(self.profile,['content.strategy','content.archives'],self.adapter)
