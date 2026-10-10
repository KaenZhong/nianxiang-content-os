import copy
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from runtime.feishu_cli import FeishuAdapter
from runtime.models import NianxiangError

class MatrixRecords(unittest.TestCase):
    def adapter(self, payload, multiple=False):
        self.commands=[]
        fields=[{'id':'fldKey','name':'作品键','type':'text'}, {'id':'fldState','name':'发表状态','type':'select','multiple':multiple}, {'id':'fldBody','name':'第一版','type':'text'}]
        config={'space_id':'synthetic-space','knowledge_map':{'operations.base':{'obj_type':'bitable','obj_token':'synthetic-base'}},'base_tables':{'moments_works':{'table_id':'tblSynthetic','expected_title':'朋友圈文案'}}}
        def runner(command):
            self.commands.append(command)
            action=command[2]
            data={'tables':[{'id':'tblSynthetic','name':'朋友圈文案'}]} if action=='+table-list' else {'fields':fields,'has_more':False} if action=='+field-list' else copy.deepcopy(payload) if action=='+record-list' else None
            if data is None:raise AssertionError('unexpected command')
            return {'ok':True,'identity':'user','data':data}
        a=FeishuAdapter(config,runner);a.account_id='synthetic-user';return a
    def payload(self, rows=None):
        return {'fields':['作品键','发表状态','第一版'],'field_id_list':['fldKey','fldState','fldBody'],'field_type_list':['text','select','text'],'record_id_list':['recSynthetic'] if rows is None else [],'data':[['nxw:synthetic',['待发布'],'真实素材初稿']] if rows is None else rows,'has_more':False,'rev':7}
    def target(self):return {'knowledge_id':'operations.base','obj_type':'bitable','table_key':'moments_works','key_field':'作品键','object_key':'nxw:synthetic'}
    def test_current_matrix_empty_is_a_verified_absence(self):
        self.assertIsNone(self.adapter(self.payload([])).lookup(self.target(),None))
    def test_current_matrix_row_recovers_key_body_and_single_select(self):
        actual=self.adapter(self.payload()).lookup(self.target(),None)
        self.assertEqual(actual['record_id'],'recSynthetic')
        self.assertEqual(actual['content'],{'作品键':'nxw:synthetic','发表状态':'待发布','第一版':'真实素材初稿'})
        self.assertEqual(actual['account_id'],'synthetic-user')
    def test_multiple_select_keeps_array(self):
        actual=self.adapter(self.payload(),multiple=True).lookup(self.target(),None)
        self.assertEqual(actual['content']['发表状态'],['待发布'])
    def test_malformed_alignment_or_missing_completion_is_blocked(self):
        cases=[]
        for name,value in [('data',[['nxw:synthetic']]),('record_id_list',[]),('fields',['作品键','作品键','第一版']),('field_type_list',['text','text','text']),('field_id_list',['fldWrong','fldState','fldBody'])]:
            p=self.payload();p[name]=value;cases.append(p)
        p=self.payload();p.pop('has_more');cases.append(p)
        for p in cases:
            with self.subTest(payload=p),self.assertRaises(NianxiangError):self.adapter(p).lookup(self.target(),None)
    def test_matrix_wrong_business_key_is_blocked(self):
        p=self.payload();p['data'][0][0]='nxw:another'
        with self.assertRaisesRegex(NianxiangError,'target_mismatch'):self.adapter(p).lookup(self.target(),None)
    def test_partial_or_duplicate_matrix_is_blocked(self):
        p=self.payload();p['has_more']=True
        with self.assertRaisesRegex(NianxiangError,'duplicate_object_key'):self.adapter(p).lookup(self.target(),None)
        p=self.payload();p['data']*=2;p['record_id_list']=['recSynthetic','recAnother']
        with self.assertRaisesRegex(NianxiangError,'duplicate_object_key'):self.adapter(p).lookup(self.target(),None)
    def test_invalid_single_select_is_not_silently_collapsed(self):
        p=self.payload();p['data'][0][1]=['待发布','已发布']
        with self.assertRaisesRegex(NianxiangError,'invalid_response'):self.adapter(p).lookup(self.target(),None)
    def test_legacy_record_envelope_still_works(self):
        p={'records':[{'record_id':'recSynthetic','fields':{'作品键':'nxw:synthetic','发表状态':'待发布'}}],'has_more':False}
        self.assertEqual(self.adapter(p).lookup(self.target(),None)['content']['发表状态'],'待发布')

if __name__=='__main__':unittest.main()
