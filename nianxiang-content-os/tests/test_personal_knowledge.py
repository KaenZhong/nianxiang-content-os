import copy,json,unittest
from personal_support import Fixture,rule,collaboration
from runtime.models import NianxiangError,read_json,write_json
from runtime.personal import parse_personal_source,read_personal_context,plan_personal_migration,apply_personal_migration,export_personal_context,save_preferred_name

class PersonalKnowledge(Fixture,unittest.TestCase):
    def source(self,kind,data):
        key='ip.profile' if kind=='collaboration' else 'content.methods'
        prefix='NIANXIANG_COLLABORATION_V1=' if kind=='collaboration' else 'NIANXIANG_PERSONAL_RULES_V1='
        self.adapter.docs[key]['content']=prefix+json.dumps(data,ensure_ascii=False,separators=(',',':'))
    def seed(self):
        self.source('collaboration',collaboration());self.source('rules',{'schema_version':1,'rules':[rule()]})
    def legacy(self):
        write_json(self.profile/'user-profile.json',{'schema_version':1,'preferred_name':'旧称呼','consent_confirmed':True,'consent_date':'2026-09-01'})
        write_json(self.profile/'rules.local.json',{'schema_version':1,'rules':[rule()]})
    def test_rules_are_read_from_methods_child_not_navigation(self):
        config=read_json(self.profile/'local-config.json')
        if 'content.methods' not in config['knowledge_map']:
            parent=config['knowledge_map']['methodology.current']
            config['knowledge_map']['content.methods']={'expected_title':'01｜创作方法与规则','node_token':'node-methods','obj_token':'doc-methods','obj_type':'docx','parent_node_token':parent['node_token'],'access':'read_write'}
            config['schema_version']=5
            config['write_targets']['sync_candidate_knowledge_ids'].append('content.methods')
            write_json(self.profile/'local-config.json',config)
            from personal_support import PersonalFake
            self.adapter=PersonalFake(self.profile)
        self.source('collaboration',collaboration())
        self.adapter.docs['methodology.current']['content']='导航，不维护规则正文'
        self.adapter.docs['content.methods']['content']='NIANXIANG_PERSONAL_RULES_V1='+json.dumps({'schema_version':1,'rules':[rule()]},ensure_ascii=False,separators=(',',':'))
        result=read_personal_context(self.profile,self.adapter,refresh=True)
        self.assertEqual(result['status'],'ready')
        self.assertEqual(result['rules']['rules'][0]['id'],'r-one')
        self.assertEqual(result['source_bindings']['rules']['knowledge_id'],'content.methods')

    def test_source_validation(self):
        self.seed();body=self.adapter.docs['content.methods']['content']
        self.assertEqual(len(parse_personal_source(body,'rules')['rules']),1)
        for content in [body+'\n'+body,body.replace('user_explicit','unknown'),body.replace('"source":"synthetic:user-request"','"source":null'),body+'junk']:
            with self.assertRaisesRegex(NianxiangError,'invalid_personal_source'):parse_personal_source(content,'rules')
        with self.assertRaises(NianxiangError):parse_personal_source(body,'unknown')
    def test_duplicate_source_blocks_without_cache_fallback(self):
        self.seed();self.assertEqual(read_personal_context(self.profile,self.adapter)['status'],'ready')
        self.adapter.docs['content.methods']['content']+='\n'+self.adapter.docs['content.methods']['content']
        outcome=read_personal_context(self.profile,self.adapter,refresh=True)
        self.assertEqual(outcome['status'],'blocked');self.assertEqual(outcome['code'],'invalid_personal_source');self.assertNotIn('rules',outcome)
    def test_missing_sources_with_legacy_requires_migration(self):
        self.legacy();self.assertEqual(read_personal_context(self.profile,self.adapter)['status'],'migration_required')
    def test_source_refresh_inference_and_paused_are_preserved(self):
        self.seed();self.source('rules',{'schema_version':1,'rules':[rule('agent_inference')]})
        ctx=read_personal_context(self.profile,self.adapter);self.assertEqual(ctx['rules']['rules'][0]['basis'],'agent_inference')
        from runtime.rules import select_confirmed_rules
        self.assertEqual(select_confirmed_rules(ctx['rules'],{'channel':'moments','surface':'body'}),[])
        self.source('rules',{'schema_version':1,'rules':[rule(status='paused')]});self.adapter.docs['content.methods']['revision']=2
        self.assertEqual(read_personal_context(self.profile,self.adapter,refresh=True)['rules']['rules'][0]['status'],'paused')
    def test_local_cache_supports_offline_work_but_latest_still_requires_network(self):
        self.seed();read_personal_context(self.profile,self.adapter);self.adapter.offline=True
        self.assertEqual(read_personal_context(self.profile,self.adapter)['status'],'ready')
        self.assertEqual(read_personal_context(self.profile,self.adapter,refresh=True)['status'],'blocked')
        cache=self.profile/'snapshots/context.json';data=read_json(cache);data['knowledge']['ip.profile']['content']='tampered';write_json(cache,data)
        self.assertEqual(read_personal_context(self.profile,self.adapter)['status'],'blocked')
    def test_known_account_change_never_uses_cache(self):
        self.seed();read_personal_context(self.profile,self.adapter);self.adapter.account='other'
        self.assertEqual(read_personal_context(self.profile,self.adapter,refresh=True)['code'],'account_mismatch')
        self.assertEqual(read_personal_context(self.profile,self.adapter)['code'],'account_mismatch')
    def test_partial_migration_only_activates_saved_group(self):
        self.legacy();plan=plan_personal_migration(self.profile,self.adapter);self.adapter.fail_key='content.methods'
        first=apply_personal_migration(self.profile,plan,self.adapter,'合成测试：保存预览的两类资料')
        self.assertEqual(first['groups']['collaboration']['status'],'saved');self.assertEqual(first['groups']['rules']['status'],'uncertain')
        state=read_json(self.profile/'state.json');self.assertEqual(state['long_term_sources_status']['collaboration'],'feishu_active');self.assertEqual(state['long_term_sources_status']['rules'],'legacy_pending')
        self.adapter.fail_key=None;second=apply_personal_migration(self.profile,plan,self.adapter,'合成测试：保存预览的两类资料')
        self.assertEqual(second['status'],'saved');self.assertEqual(self.adapter.writes,2)
        self.assertEqual(self.adapter.docs['content.methods']['content'].count('NIANXIANG_PERSONAL_RULES_V1='),1)
        self.assertTrue((self.profile/'rules.local.json').exists())
    def test_changed_source_or_legacy_conflicts_before_write(self):
        self.legacy();plan=plan_personal_migration(self.profile,self.adapter)
        self.adapter.docs['ip.profile']['revision']=2
        self.assertEqual(apply_personal_migration(self.profile,plan,self.adapter,'save preview')['status'],'conflict');self.assertEqual(self.adapter.writes,0)
        plan=plan_personal_migration(self.profile,self.adapter);write_json(self.profile/'rules.local.json',{'schema_version':1,'rules':[]})
        self.assertEqual(apply_personal_migration(self.profile,plan,self.adapter,'save preview')['status'],'conflict')
    def test_alias_conflict_and_unclassified_convention_do_not_migrate(self):
        self.legacy();write_json(self.profile/'local-rules.json',{'schema_version':1,'rules':[]})
        self.assertEqual(plan_personal_migration(self.profile,self.adapter)['status'],'conflict')
        (self.profile/'local-rules.json').unlink();(self.profile/'business-conventions.md').write_text('具体约定需核对')
        plan=plan_personal_migration(self.profile,self.adapter);self.assertTrue(plan['needs_confirmation'])
        self.assertEqual(apply_personal_migration(self.profile,plan,self.adapter,'save preview')['status'],'blocked')
    def test_export_checks_integrity_and_does_not_write_source(self):
        self.seed();ctx=read_personal_context(self.profile,self.adapter)
        self.assertFalse((self.profile/'derived/USER.md').exists())
        self.assertEqual(export_personal_context(self.profile,ctx,['user','memory'])['status'],'exported');self.assertEqual(self.adapter.writes,0)
        ctx['collaboration']['preferred_name']='changed'
        self.assertEqual(export_personal_context(self.profile,ctx,['user'])['status'],'blocked')
    def test_nickname_save_requires_real_evidence_and_preserves_other_data(self):
        self.seed();self.assertEqual(save_preferred_name(self.profile,self.adapter,'新称呼','')['status'],'blocked')
        self.assertEqual(save_preferred_name(self.profile,self.adapter,'新称呼','合成测试：长期称呼改为新称呼')['status'],'saved')
        self.assertEqual(read_personal_context(self.profile,self.adapter)['collaboration']['preferred_name'],'新称呼')
        self.assertFalse((self.profile/'user-profile.json').exists())
    def test_same_nickname_reauthorization_activates_prior_nonactive_evidence(self):
        for status in ('paused','retired','trial'):
            data=collaboration();data['preferred_name_evidence']['status']=status;self.source('collaboration',data)
            outcome=save_preferred_name(self.profile,self.adapter,data['preferred_name'],'合成测试：重新长期使用这个称呼')
            self.assertEqual(outcome['status'],'saved')
            self.assertEqual(read_personal_context(self.profile,self.adapter)['collaboration']['preferred_name_evidence']['status'],'active')
    def test_malformed_legacy_rules_returns_blocked_without_writes(self):
        for bad in ([],{'schema_version':1,'rules':['bad-rule']},{'schema_version':1,'rules':None}):
            write_json(self.profile/'rules.local.json',bad)
            self.assertEqual(plan_personal_migration(self.profile,self.adapter)['status'],'blocked')
            self.assertEqual(self.adapter.writes,0)

    def test_migration_preview_cannot_follow_rebound_knowledge_object(self):
        self.legacy();plan=plan_personal_migration(self.profile,self.adapter)
        config=read_json(self.profile/'local-config.json');config['knowledge_map']['ip.profile']['obj_token']='new-ip-object'
        write_json(self.profile/'local-config.json',config);self.adapter.docs['ip.profile']['obj_token']='new-ip-object'
        self.assertEqual(apply_personal_migration(self.profile,plan,self.adapter,'保存预览指定对象')['status'],'conflict')
        self.assertEqual(self.adapter.writes,0)
    def test_migration_duplicate_remote_readback_never_activates_group(self):
        self.legacy();plan=plan_personal_migration(self.profile,self.adapter);original=self.adapter.write
        def duplicate(request):
            out=original(request)
            if request['target']['knowledge_id']=='ip.profile':self.adapter.docs['ip.profile']['content']+='\n'+request['content']['text']
            return out
        self.adapter.write=duplicate;out=apply_personal_migration(self.profile,plan,self.adapter,'保存预览')
        self.assertEqual(out['groups']['collaboration']['status'],'blocked')
        self.assertEqual(read_json(self.profile/'state.json')['long_term_sources_status']['collaboration'],'legacy_pending')

    def test_nickname_append_duplicate_never_reports_saved(self):
        original=self.adapter.write
        def duplicate(request):
            out=original(request);self.adapter.docs['ip.profile']['content']+='\n'+request['content']['text'];return out
        self.adapter.write=duplicate
        self.assertNotEqual(save_preferred_name(self.profile,self.adapter,'称呼','合成授权：长期称呼')['status'],'saved')

if __name__=='__main__':unittest.main()
