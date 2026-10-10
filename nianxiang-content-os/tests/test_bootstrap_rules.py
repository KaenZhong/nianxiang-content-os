import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from runtime.bootstrap import plan_bootstrap,resume_bootstrap,authorize_bootstrap
from runtime.rules import select_confirmed_rules
from runtime.paths import create_profile
from runtime.models import NianxiangError,read_json

class SkeletonFeishu:
    def __init__(self):
        self.account='account-a';self.space='space-a';self.nodes=[];self.tables=[];self.writes=0;self.lose_response=False;self.fail_tables=False
    def get_account(self):return {'identity':'user','account_id':self.account}
    def list_nodes(self,parent):return copy.deepcopy([n for n in self.nodes if n['parent_node_token']==((parent or {}).get('node_token',''))])
    def list_tables(self,base):return copy.deepcopy(self.tables)
    def list_fields(self,base,table):return copy.deepcopy(table['fields'])
    def get_node(self,target):return copy.deepcopy(next(n for n in self.nodes if n['node_token']==target['node_token']))
    def write(self,request):
        self.writes+=1;t=request['target']
        if request['action']=='create_table':
            if self.fail_tables:raise NianxiangError('permission_denied','table create denied')
            obj={'id':'table-'+str(self.writes),'name':t['title'],'fields':copy.deepcopy(request['content']['fields'])};self.tables.append(obj)
        else:
            obj={**t,'node_token':'node-'+str(self.writes),'obj_token':'object-'+str(self.writes)};self.nodes.append(obj)
        if self.lose_response:self.lose_response=False;raise NianxiangError('timeout','created but response lost')
        return copy.deepcopy(obj)

class Bootstrap(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=Path(self.temp.name).resolve()
        self.profile=root/'profiles'/create_profile(root,'account-a','space-a');self.adapter=SkeletonFeishu()
        self.structure=json.loads((Path(__file__).resolve().parents[1]/'assets/templates/knowledge-structure.json').read_text())
        self.structure.update(account_id='account-a',space_id='space-a')
    def plan(self):return plan_bootstrap(self.adapter,self.structure)
    def run_plan(self,plan=None):
        plan=plan or self.plan()
        return resume_bootstrap(self.profile,plan,self.adapter,authorize_bootstrap(plan,'用户授权在合成空间建立兼容骨架'))
    def test_new_library_uses_os_home_title(self):
        self.assertEqual(self.run_plan()['status'],'ready')
        home=next(n for n in self.adapter.nodes if n['parent_node_token']=='')
        self.assertEqual(home['title'],'首页｜念响AI · 内容OS')
    def test_existing_studio_home_reused_without_duplicate_creation(self):
        self.structure['nodes'][0].update(title='首页｜念响AI · 内容OS',legacy_titles=['首页｜念响AI · 内容工坊'])
        self.adapter.nodes=[{'space_id':'space-a','parent_node_token':'','title':'首页｜念响AI · 内容工坊','obj_type':'docx','node_token':'old-home','obj_token':'old-home-doc'}]
        self.assertEqual(self.plan()['items'][0]['status'],'reuse')
        self.assertEqual(self.run_plan()['status'],'ready')
        homes=[n for n in self.adapter.nodes if n['parent_node_token']=='' and n['title'] in ('首页｜念响AI · 内容OS','首页｜念响AI · 内容工坊')]
        self.assertEqual(len(homes),1);self.assertEqual(homes[0]['node_token'],'old-home')
    def test_old_and_new_home_together_require_explicit_resolution(self):
        self.structure['nodes'][0].update(title='首页｜念响AI · 内容OS',legacy_titles=['首页｜念响AI · 内容工坊'])
        self.adapter.nodes=[{'space_id':'space-a','parent_node_token':'','title':title,'obj_type':'docx','node_token':str(i),'obj_token':'doc-'+str(i)} for i,title in enumerate(['首页｜念响AI · 内容OS','首页｜念响AI · 内容工坊'])]
        with self.assertRaisesRegex(NianxiangError,'ambiguous_node'):self.plan()
        self.assertEqual(self.adapter.writes,0)

    def test_preview_without_authorization_does_not_write(self):
        plan=self.plan();self.assertEqual(self.adapter.writes,0)
        self.assertEqual(resume_bootstrap(self.profile,plan,self.adapter,{})['status'],'blocked');self.assertEqual(self.adapter.writes,0)
    def test_empty_then_half_built_only_missing_objects_and_active_config(self):
        result=self.run_plan();self.assertEqual(result['status'],'ready')
        config=json.loads((self.profile/'local-config.json').read_text())
        self.assertEqual(len(config['knowledge_map']),12);self.assertEqual(len(config['base_tables']),4);self.assertTrue(read_json(self.profile/'state.json')['active'])
        writes=self.adapter.writes;self.assertEqual(self.run_plan()['status'],'ready');self.assertEqual(self.adapter.writes,writes)
    def test_duplicate_title_is_conflict_without_writes(self):
        self.run_plan();node=copy.deepcopy(self.adapter.nodes[0]);node['node_token']='duplicate';node['obj_token']='duplicate-object';self.adapter.nodes.append(node)
        writes=self.adapter.writes
        with self.assertRaisesRegex(NianxiangError,'ambiguous_node'):self.plan()
        self.assertEqual(self.adapter.writes,writes)
    def test_creation_timeout_rechecks_before_retry(self):
        self.adapter.lose_response=True;plan=self.plan()
        self.assertEqual(self.run_plan(plan)['status'],'uncertain');self.assertFalse(read_json(self.profile/'state.json')['active'])
        result=self.run_plan(plan);self.assertEqual(result['status'],'ready')
        titles=[(n['parent_node_token'],n['title']) for n in self.adapter.nodes];self.assertEqual(len(titles),len(set(titles)))
    def test_missing_tables_never_enable_config(self):
        self.adapter.fail_tables=True
        self.assertEqual(self.run_plan()['status'],'blocked');self.assertFalse(read_json(self.profile/'state.json')['active']);self.assertFalse((self.profile/'local-config.json').exists())
    def test_changed_scope_or_account_requires_new_authorization(self):
        plan=self.plan();auth=authorize_bootstrap(plan,'build')
        modified=copy.deepcopy(plan);modified['structure']['nodes'][0]['title']='changed'
        self.assertEqual(resume_bootstrap(self.profile,modified,self.adapter,auth)['status'],'blocked');self.assertEqual(self.adapter.writes,0)
        self.adapter.account='account-b';self.assertEqual(resume_bootstrap(self.profile,plan,self.adapter,auth)['status'],'blocked');self.assertEqual(self.adapter.writes,0)
    def test_wrong_topic_link_cannot_activate(self):
        self.run_plan()
        for field in self.adapter.tables[1]['fields']:
            if field['name']=='关联选题':field['link_table']='unrelated-table'
        self.assertEqual(self.run_plan()['status'],'blocked');self.assertFalse(read_json(self.profile/'state.json')['active'])

    def test_existing_profile_verification_checks_fields_before_activation(self):
        from manage import verify_profile
        from runtime.models import write_json
        self.run_plan();config=read_json(self.profile/'local-config.json')
        original=self.adapter.get_node
        self.adapter.get_node=lambda target:original({'node_token':config['knowledge_map'][target['knowledge_id']]['node_token']})
        with patch('manage.FeishuAdapter',return_value=self.adapter):
            self.assertEqual(verify_profile(self.profile)['status'],'ready')
            for damage in ('missing_field','missing_option','wrong_topic_link'):
                with self.subTest(damage=damage):
                    saved=copy.deepcopy(self.adapter.tables)
                    if damage=='missing_field':self.adapter.tables[0]['fields']=[]
                    elif damage=='missing_option':
                        next(f for f in self.adapter.tables[1]['fields'] if f['type']=='select')['options']=[]
                    else:
                        next(f for f in self.adapter.tables[1]['fields'] if f['name']=='关联选题')['link_table']='wrong-table'
                    with self.assertRaisesRegex(NianxiangError,'field_conflict'):verify_profile(self.profile)
                    self.assertFalse(read_json(self.profile/'state.json')['active'])
                    self.adapter.tables=saved
                    state=read_json(self.profile/'state.json');state['active']=True;write_json(self.profile/'state.json',state)

    def test_existing_profile_duplicate_topic_pool_never_activates(self):
        from manage import verify_profile
        self.run_plan();config=read_json(self.profile/'local-config.json');original=self.adapter.get_node
        self.adapter.get_node=lambda target:original({'node_token':config['knowledge_map'][target['knowledge_id']]['node_token']})
        duplicate=copy.deepcopy(self.adapter.tables[0]);duplicate['id']='another-topic-pool'
        self.adapter.tables.append(duplicate)
        next(f for f in self.adapter.tables[1]['fields'] if f['name']=='关联选题')['link_table']=duplicate['id']
        with patch('manage.FeishuAdapter',return_value=self.adapter):
            with self.assertRaisesRegex(NianxiangError,'ambiguous_table'):verify_profile(self.profile)
        self.assertFalse(read_json(self.profile/'state.json')['active'])

    def test_existing_schema_missing_field_never_active(self):
        self.run_plan();self.adapter.tables[0]['fields']=[]
        state=read_json(self.profile/'state.json');state['active']=False
        from runtime.models import write_json
        write_json(self.profile/'state.json',state)
        self.assertEqual(self.run_plan()['status'],'blocked');self.assertFalse(read_json(self.profile/'state.json')['active'])

class Rules(unittest.TestCase):
    def rule(self,**kw):
        return dict(id='r1',instruction='使用具体事实',channels=['moments'],surfaces=['body'],materials=['general'],scope='channel',status='active',basis='user_confirmed',source='confirmed work: synthetic',**kw)
    def test_only_confirmed_relevant_active_rules_apply(self):
        inferred=self.rule();inferred.update(id='r2',basis='agent_inference')
        paused=self.rule();paused.update(id='r3',status='paused')
        other=self.rule();other.update(id='r4',channels=['short_video'])
        data={'schema_version':1,'rules':[self.rule(),inferred,paused,other]}
        selected=select_confirmed_rules(data,{'channel':'moments','surface':'body','material':'general'})
        self.assertEqual([r['id'] for r in selected],['r1'])
    def test_missing_source_does_not_become_confirmed(self):
        rule=self.rule();rule.pop('source')
        self.assertEqual(select_confirmed_rules({'schema_version':1,'rules':[rule]},{'channel':'moments','surface':'body','material':'general'}),[])
    def test_trial_requires_opt_in_and_inferred_trial_is_labelled(self):
        rule=self.rule();rule.update(status='trial',basis='agent_inference')
        task={'channel':'moments','surface':'body','material':'general'}
        self.assertEqual(select_confirmed_rules({'schema_version':1,'rules':[rule]},task),[])
        selected=select_confirmed_rules({'schema_version':1,'rules':[rule]},{**task,'include_trial':True})
        self.assertFalse(selected[0]['confirmed'])

if __name__=='__main__':unittest.main()
