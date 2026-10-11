import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from runtime.models import NianxiangError,digest,read_json,write_json
from runtime.paths import create_profile
from runtime.knowledge import load_context,save_change,reconcile_pending,authorize_request

class FakeFeishu:
    def __init__(self):
        self.account='account-a';self.space='space-a';self.calls=0;self.writes=0;self.offline=False;self.fail_after_write=False;self.records={}
        self.doc={'account_id':self.account,'space_id':self.space,'node_token':'node-strategy','obj_token':'doc-strategy','obj_type':'docx','parent_node_token':'positioning','title':'01｜内容经营策略','revision':1,'content':'synthetic strategy'}
    def get_account(self):
        self.calls+=1
        if self.offline: raise NianxiangError('offline','network unavailable')
        return {'account_id':self.account,'identity':'user'}
    def get_node(self,target):
        self.calls+=1
        if self.offline: raise NianxiangError('offline','network unavailable')
        return dict(self.doc) if target['knowledge_id']=='content.strategy' else {'account_id':self.account,'space_id':self.space,'node_token':'node-base','obj_token':'base-a','obj_type':'bitable','parent_node_token':'operations','title':'念响AI · 内容中台'}
    def read(self,knowledge_id):
        if self.offline: raise NianxiangError('offline','network unavailable')
        return copy.deepcopy(self.doc)
    def lookup(self,target,operation_id):
        if self.fail_after_write and self.writes: raise NianxiangError('offline','readback unavailable')
        if self.offline: raise NianxiangError('offline','network unavailable')
        return copy.deepcopy(self.records.get(target.get('object_key')))
    def write(self,request):
        self.writes+=1
        t=request['target'];obj={'account_id':self.account,'space_id':self.space,'record_id':'record-'+str(self.writes),'revision':self.writes,'target':copy.deepcopy(t),'content':copy.deepcopy(request['content'])}
        self.records[t['object_key']]=obj
        return obj

class KnowledgeRuntime(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name).resolve()
        self.profile=root/'profiles'/create_profile(root,'account-a','space-a');self.adapter=FakeFeishu()
        config=json.loads((Path(__file__).resolve().parents[1]/'local/local-config.example.json').read_text())
        config['space_id']='space-a'
        for i,(key,item) in enumerate(config['knowledge_map'].items()):
            item['node_token']='node-'+str(i);item['obj_token']='doc-'+str(i);item['parent_node_token']='parent-'+str(i)
        for key in ('content.strategy','audience.needs','ip.profile','expression.baseline'): config['knowledge_map'][key]['parent_node_token']='positioning'
        for key in ('cocreation.index','content.assets'): config['knowledge_map'][key]['parent_node_token']='assets'
        for key in ('operations.index','content.archives','content.campaigns','content.reviews'): config['knowledge_map'][key]['parent_node_token']='operations-root'
        config['knowledge_map']['content.strategy'].update(node_token='node-strategy',obj_token='doc-strategy')
        config['knowledge_map']['operations.index']['node_token']='operations'
        config['knowledge_map']['operations.base'].update(node_token='node-base',obj_token='base-a',parent_node_token='operations')
        for key,item in config['base_tables'].items():item['table_id']='table-'+key
        write_json(self.profile/'local-config.json',config)
        state=read_json(self.profile/'state.json');state['active']=True;write_json(self.profile/'state.json',state)
    def request(self):
        r={'operation_id':'operation-one','target':{'knowledge_id':'operations.base','obj_type':'bitable','table_key':'moments_works','key_field':'作品键','object_key':'nxw:synthetic:1'},'action':'create','base_revision':None,'content':{'作品键':'nxw:synthetic:1','作品标题':'测试','第一版':'合成素材生成的首稿','发表状态':'待发布','沉淀状态':'待沉淀'}}
        r['authorization']=authorize_request(self.profile,r,'用户明确保存这条测试作品')
        return r
    def test_new_session_source_change_and_stale_cache(self):
        first=load_context(self.profile,['content.strategy'],self.adapter)
        self.assertEqual(first['knowledge']['content.strategy']['status'],'current')
        second=load_context(self.profile,['content.strategy'],self.adapter)
        self.assertTrue(second['knowledge']['content.strategy']['cached'])
        self.adapter.doc.update(revision=2,content='changed source')
        self.assertEqual(load_context(self.profile,['content.strategy'],self.adapter)['knowledge']['content.strategy']['content'],'changed source')
        self.adapter.offline=True
        stale=load_context(self.profile,['content.strategy'],self.adapter)['knowledge']['content.strategy']
        self.assertEqual(stale['status'],'stale');self.assertFalse(stale['current'])
    def test_account_and_node_change_fail_closed(self):
        load_context(self.profile,['content.strategy'],self.adapter)
        self.adapter.account='account-b'
        with self.assertRaisesRegex(NianxiangError,'account_mismatch'):load_context(self.profile,['content.strategy'],self.adapter)
        self.adapter.account='account-a';self.adapter.doc['parent_node_token']='different-parent'
        with self.assertRaisesRegex(NianxiangError,'target_mismatch'):load_context(self.profile,['content.strategy'],self.adapter)
    def test_no_authorization_or_tampered_payload_makes_no_remote_calls(self):
        r=self.request();r['authorization']={}
        self.assertEqual(save_change(self.profile,r,self.adapter)['status'],'blocked');self.assertEqual(self.adapter.calls,0)
        r=self.request();r['content']['第一版']='outside authorized content'
        self.assertEqual(save_change(self.profile,r,self.adapter)['status'],'blocked');self.assertEqual(self.adapter.calls,0)
    def test_write_readback_repeat_and_operation_reuse_conflict(self):
        r=self.request();self.assertEqual(save_change(self.profile,r,self.adapter)['status'],'saved')
        self.assertEqual(save_change(self.profile,r,self.adapter)['status'],'saved');self.assertEqual(self.adapter.writes,1)
        other=self.request();other['content']['第一版']='changed';other['authorization']=authorize_request(self.profile,other,'save changed')
        self.assertEqual(save_change(self.profile,other,self.adapter)['status'],'conflict');self.assertEqual(self.adapter.writes,1)
    def test_uncertain_recovers_existing_without_duplicate_create(self):
        self.adapter.fail_after_write=True;r=self.request()
        self.assertEqual(save_change(self.profile,r,self.adapter)['status'],'uncertain')
        self.adapter.fail_after_write=False
        self.assertEqual(reconcile_pending(self.profile,r['operation_id'],self.adapter)['status'],'saved');self.assertEqual(self.adapter.writes,1)
    def test_pending_before_attempt_and_retry_same_authorization(self):
        self.adapter.offline=True;r=self.request()
        self.assertEqual(save_change(self.profile,r,self.adapter)['status'],'pending');self.assertEqual(self.adapter.writes,0)
        self.adapter.offline=False
        self.assertEqual(reconcile_pending(self.profile,r['operation_id'],self.adapter)['status'],'saved');self.assertEqual(self.adapter.writes,1)
    def test_uncertain_without_remote_match_never_blindly_replays(self):
        r=self.request();self.adapter.fail_after_write=True;save_change(self.profile,r,self.adapter)
        self.adapter.fail_after_write=False;self.adapter.records.clear()
        self.assertEqual(reconcile_pending(self.profile,r['operation_id'],self.adapter)['status'],'uncertain');self.assertEqual(self.adapter.writes,1)
    def test_existing_different_record_or_changed_base_revision_conflicts(self):
        r=self.request();self.adapter.records[r['target']['object_key']]={'revision':9,'content':{'第一版':'other'},'target':r['target']}
        self.assertEqual(save_change(self.profile,r,self.adapter)['status'],'conflict');self.assertEqual(self.adapter.writes,0)
        r['action']='update';r['base_revision']=1;r['authorization']=authorize_request(self.profile,r,'update same work')
        self.assertEqual(save_change(self.profile,r,self.adapter)['status'],'conflict');self.assertEqual(self.adapter.writes,0)
    def test_permission_error_is_blocked_not_pending(self):
        def denied(): raise NianxiangError('permission_denied','denied')
        self.adapter.get_account=denied
        self.assertEqual(save_change(self.profile,self.request(),self.adapter)['status'],'blocked')
    def test_retargeted_configuration_invalidates_pending_authorization(self):
        r=self.request();config=read_json(self.profile/'local-config.json')
        config['knowledge_map']['operations.base']['obj_token']='another-base-in-same-space'
        write_json(self.profile/'local-config.json',config)
        original=self.adapter.get_node
        def retargeted(target):
            node=original(target)
            if target['knowledge_id']=='operations.base':node['obj_token']='another-base-in-same-space'
            return node
        self.adapter.get_node=retargeted
        self.assertEqual(save_change(self.profile,r,self.adapter)['status'],'blocked');self.assertEqual(self.adapter.calls,0)

    def test_first_draft_is_immutable_on_update(self):
        r=self.request();self.assertEqual(save_change(self.profile,r,self.adapter)['status'],'saved')
        old=self.adapter.records[r['target']['object_key']]
        r.update(operation_id='new-update',action='update',base_revision=old['revision'])
        r['content']['第一版']='overwritten first draft';r['authorization']=authorize_request(self.profile,r,'update current version')
        self.assertEqual(save_change(self.profile,r,self.adapter)['status'],'blocked');self.assertEqual(self.adapter.writes,1)

    def test_initial_knowledge_append_readback_and_repeat(self):
        self.adapter.doc['content']=''
        r={'operation_id':'knowledge-initial','target':{'knowledge_id':'content.strategy','obj_type':'docx'},'action':'append','base_revision':1,'content':{'text':'已确认：面向自由职业者分享需求访谈经验。'}}
        r['authorization']=authorize_request(self.profile,r,'保存已确认的核心知识')
        def write_doc(request):
            self.adapter.writes+=1;self.adapter.doc.update(revision=2,content=request['content']['text']);return dict(self.adapter.doc)
        self.adapter.write=write_doc
        self.assertEqual(save_change(self.profile,r,self.adapter)['status'],'saved')
        self.assertEqual(save_change(self.profile,r,self.adapter)['status'],'saved');self.assertEqual(self.adapter.writes,1)
        snapshot=read_json(self.profile/'snapshots/content.strategy.json')
        self.assertEqual(snapshot['content'],r['content']['text'])

    def test_replace_including_old_text_readback_and_recovery(self):
        self.adapter.doc['content']='我的咨询面向小团队。'
        r={'operation_id':'replace-one','target':{'knowledge_id':'content.strategy','obj_type':'docx'},'action':'replace','base_revision':1,'content':{'pattern':'咨询','replacement':'咨询服务'}}
        r['authorization']=authorize_request(self.profile,r,'将咨询改为咨询服务')
        def write_doc(request):
            self.adapter.writes+=1
            self.adapter.doc.update(revision=2,content=self.adapter.doc['content'].replace('咨询','咨询服务',1))
            raise NianxiangError('timeout','successful write response lost')
        self.adapter.write=write_doc
        self.assertEqual(save_change(self.profile,r,self.adapter)['status'],'uncertain')
        self.assertEqual(self.adapter.doc['content'],'我的咨询服务面向小团队。')
        self.assertEqual(reconcile_pending(self.profile,r['operation_id'],self.adapter)['status'],'saved')
        self.assertEqual(self.adapter.writes,1)

    def test_replace_containing_pattern_is_saved_with_matching_readback(self):
        self.adapter.doc['content']='我的咨询面向小团队。'
        r={'operation_id':'replace-success','target':{'knowledge_id':'content.strategy','obj_type':'docx'},'action':'replace','base_revision':1,'content':{'pattern':'咨询','replacement':'咨询服务'}}
        r['authorization']=authorize_request(self.profile,r,'将咨询改为咨询服务')
        def write_doc(request):
            self.adapter.writes+=1;self.adapter.doc.update(revision=2,content='我的咨询服务面向小团队。')
            return dict(self.adapter.doc)
        self.adapter.write=write_doc
        self.assertEqual(save_change(self.profile,r,self.adapter)['status'],'saved')
        self.assertEqual(reconcile_pending(self.profile,r['operation_id'],self.adapter)['status'],'saved')
        self.assertEqual(self.adapter.writes,1)

    def test_replacement_elsewhere_does_not_claim_saved(self):
        self.adapter.doc.update(content='原文删除了，咨询服务仍出现在别处。',revision=2)
        r={'operation_id':'replace-other','target':{'knowledge_id':'content.strategy','obj_type':'docx'},'action':'replace','base_revision':1,'content':{'pattern':'原文','replacement':'咨询服务'}}
        r['authorization']=authorize_request(self.profile,r,'替换原文')
        self.assertEqual(save_change(self.profile,r,self.adapter)['status'],'conflict')
        self.assertEqual(self.adapter.writes,0)

    def test_foreign_snapshot_is_never_returned(self):
        load_context(self.profile,['content.strategy'],self.adapter)
        path=self.profile/'snapshots/context.json';bundle=read_json(path);bundle['knowledge']['content.strategy']['account_id']='other';write_json(path,bundle)
        self.adapter.offline=True
        with self.assertRaises(NianxiangError):load_context(self.profile,['content.strategy'],self.adapter)

if __name__=='__main__':unittest.main()
