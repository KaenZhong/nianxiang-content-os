import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from runtime.feishu_cli import FeishuAdapter
from runtime.models import NianxiangError

class CLIBoundaries(unittest.TestCase):
    def adapter(self,responses):
        self.commands=[]
        def runner(command):
            self.commands.append(command)
            if not responses: raise AssertionError('unexpected remote call')
            return responses.pop(0)
        return FeishuAdapter({'space_id':'synthetic-space','knowledge_map':{},'base_tables':{}},runner=runner)
    def test_verified_identity_is_explicit(self):
        a=self.adapter([{'verified':True,'identities':{'user':{'verified':True,'openId':'synthetic-user'}}}])
        self.assertEqual(a.get_account(),{'identity':'user','account_id':'synthetic-user'})
        self.assertIn('--verify',self.commands[0])
    def test_unverified_identity_never_used(self):
        a=self.adapter([{'identities':{'user':{'openId':'synthetic-user'}}}])
        with self.assertRaisesRegex(NianxiangError,'identity_unverified'):a.get_account()
    def test_cloud_cli_uses_verified_self_contact_when_auth_command_is_absent(self):
        def runner(command):
            if command[1:3]==['auth','status']:raise NianxiangError('unsupported_command','no auth command')
            self.assertEqual(command[1:3],['contact','+get-user'])
            self.assertEqual(command[-4:],['--as','user','--format','json'])
            return {'ok':True,'identity':'user','data':{'user':{'open_id':'cloud-user'}}}
        a=FeishuAdapter({},runner)
        self.assertEqual(a.get_account(),{'identity':'user','account_id':'cloud-user'})
    def test_cloud_fallback_rejects_unverified_contact(self):
        for response in ({'ok':True,'identity':'bot','data':{'user':{'open_id':'cloud-user'}}},
                         {'ok':True,'identity':'user','data':{'user':{}}},
                         {'ok':False,'identity':'user','data':{'user':{'open_id':'cloud-user'}}}):
            def runner(command):
                if command[1:3]==['auth','status']:raise NianxiangError('unsupported_command','no auth command')
                return response
            with self.subTest(response=response):
                with self.assertRaises(NianxiangError):FeishuAdapter({},runner).get_account()
    def test_only_missing_auth_command_triggers_fallback(self):
        a=self.adapter([])
        with patch.object(a,'_run',side_effect=NianxiangError('permission_denied','auth denied')):
            with self.assertRaisesRegex(NianxiangError,'permission_denied'):a.get_account()
    def test_failed_or_bot_response_is_blocked(self):
        for response in ({'ok':True,'identity':'bot','data':{}},{'ok':False,'identity':'user','error':{'type':'permission'}}):
            a=self.adapter([response])
            with self.assertRaises(NianxiangError):a.list_nodes(None)
    def test_partial_list_rejected_and_user_identity_added(self):
        a=self.adapter([{'ok':True,'identity':'user','data':{'nodes':[],'has_more':True}}])
        with self.assertRaisesRegex(NianxiangError,'incomplete_listing'):a.list_nodes(None)
        self.assertEqual(self.commands[0][-4:],['--as','user','--format','json'])
    def test_unknown_write_action_has_no_command(self):
        a=self.adapter([])
        with self.assertRaisesRegex(NianxiangError,'unsupported_action'):a.write({'action':'overwrite','target':{'obj_type':'docx'},'content':{}})
        self.assertEqual(self.commands,[])


    def test_modern_wiki_token_is_read_as_node_not_document(self):
        def runner(command):
            target=command[command.index('--node-token')+1]
            if target!='https://feishu.cn/wiki/Abc123synthetic':
                return {'ok':False,'identity':'user','error':{'type':'validation'}}
            return {'ok':True,'identity':'user','data':{'node':{'node_token':'Abc123synthetic','obj_type':'docx'}}}
        a=FeishuAdapter({'space_id':'synthetic-space'},runner)
        self.assertEqual(a.get_node({'node_token':'Abc123synthetic'})['node_token'],'Abc123synthetic')
    def test_typed_entry_url_is_preserved(self):
        a=self.adapter([{'ok':True,'identity':'user','data':{'node':{'obj_type':'docx'}}}])
        url='https://example.feishu.cn/docx/AbcSynthetic?from=share'
        a.get_node({'node_token':url})
        self.assertEqual(self.commands[0][self.commands[0].index('--node-token')+1],url)
    def test_stderr_permission_envelope_is_classified_without_private_payload(self):
        proc=SimpleNamespace(returncode=2,stdout='',stderr=json.dumps({'ok':False,'identity':'user','error':{'type':'permission','message':'private-source-secret'}}))
        with patch('runtime.feishu_cli.subprocess.run',return_value=proc):
            with self.assertRaises(NianxiangError) as error:FeishuAdapter({'space_id':'synthetic-space'}).list_nodes(None)
        self.assertEqual(error.exception.code,'permission_denied')
        self.assertNotIn('private-source-secret',str(error.exception))
    def test_stderr_success_cannot_authorize_identity(self):
        proc=SimpleNamespace(returncode=2,stdout='',stderr=json.dumps({'verified':True,'identities':{'user':{'verified':True,'openId':'synthetic-user'}}}))
        with patch('runtime.feishu_cli.subprocess.run',return_value=proc):
            with self.assertRaisesRegex(NianxiangError,'invalid_response'):FeishuAdapter({}).get_account()
    def test_non_object_cli_json_is_blocked(self):
        proc=SimpleNamespace(returncode=0,stdout='[]',stderr='')
        with patch('runtime.feishu_cli.subprocess.run',return_value=proc):
            with self.assertRaisesRegex(NianxiangError,'invalid_response'):FeishuAdapter({}).get_account()
    def test_plaintext_unknown_auth_command_is_distinguished(self):
        proc=SimpleNamespace(returncode=1,stdout='',stderr='Error: unknown command "auth" for "lark-cli"')
        with patch('runtime.feishu_cli.subprocess.run',return_value=proc):
            with self.assertRaisesRegex(NianxiangError,'unsupported_command'):FeishuAdapter({})._run(['auth','status','--json','--verify'],auth=True)

    def test_revision_reads_metadata_without_fetching_body(self):
        a=self.adapter([{'ok':True,'identity':'user','data':{'code':0,'data':{'document':{'document_id':'doc-test','revision_id':7}}}}])
        a.config['knowledge_map']['content.strategy']={'obj_type':'docx','obj_token':'doc-test'}
        self.assertEqual(a.get_revision('content.strategy'),{'document_id':'doc-test','revision':7})
        self.assertEqual(self.commands[0][1:4],['api','GET','/open-apis/docx/v1/documents/doc-test'])
    def test_metadata_with_another_document_is_rejected(self):
        a=self.adapter([{'ok':True,'identity':'user','data':{'document':{'document_id':'foreign','revision_id':7}}}])
        a.config['knowledge_map']['content.strategy']={'obj_type':'docx','obj_token':'doc-test'}
        with self.assertRaises(NianxiangError):a.get_revision('content.strategy')

if __name__=='__main__':unittest.main()
