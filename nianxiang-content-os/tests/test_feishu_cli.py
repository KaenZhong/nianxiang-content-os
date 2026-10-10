import json
from pathlib import Path
import sys
import unittest
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

if __name__=='__main__':unittest.main()
