"""Offline acceptance journey: real runtime and temporary files, synthetic Feishu."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_bootstrap_rules as bootstrap_cases
from runtime.knowledge import load_context,save_change,authorize_request
from runtime.models import digest

class JourneyFeishu(bootstrap_cases.SkeletonFeishu):
    def __init__(self):super().__init__();self.bodies={};self.records={};self.record_writes=0
    def get_node(self,target):
        if 'knowledge_id' in target:target={'node_token':self.config['knowledge_map'][target['knowledge_id']]['node_token']}
        return super().get_node(target)
    def read(self,key):
        node=self.get_node({'knowledge_id':key});body=self.bodies.get(node['obj_token'],{'revision':1,'content':''})
        return {**node,**body,'account_id':self.account}
    def lookup(self,target,operation_id):return copy.deepcopy(self.records.get(target['object_key']))
    def write(self,request):
        if request['action'] in ('create_node','create_table'):return super().write(request)
        if request['target']['obj_type']=='docx':
            node=self.get_node(request['target']);old=self.bodies.get(node['obj_token'],{'revision':1,'content':''})
            value={'revision':old['revision']+1,'content':old['content']+request['content']['text']};self.bodies[node['obj_token']]=value;return value
        self.record_writes+=1
        value={'target':request['target'],'record_id':'synthetic-record','revision':digest(request['content']),'content':copy.deepcopy(request['content']),'account_id':self.account,'space_id':self.space}
        self.records[request['target']['object_key']]=value;return value

class CoreJourney(unittest.TestCase):
    setUp=bootstrap_cases.Bootstrap.setUp
    plan=bootstrap_cases.Bootstrap.plan
    run_plan=bootstrap_cases.Bootstrap.run_plan
    def test_core_journey(self):
        self.adapter=JourneyFeishu();self.assertEqual(self.run_plan()['status'],'ready')
        from runtime.models import read_json
        self.adapter.config=read_json(self.profile/'local-config.json')
        facts={'ip.profile':'合成用户：自由职业咨询顾问。客户匿名，经营结果未知。','content.strategy':'已确认：分享需求访谈经验，帮助小团队澄清需求。无报名入口。','audience.needs':'待验证：小团队可能需要访谈方法。证据来自本份合成素材，未证明普遍需求。','expression.baseline':'暂无已确认的跨渠道个人表达规则。单篇使用具体事实，暂不升级长期规则。'}
        for key,text in facts.items():
            r={'operation_id':'initial-'+key.replace('.','-'),'target':{'knowledge_id':key,'obj_type':'docx'},'action':'append','base_revision':1,'content':{'text':text}}
            r['authorization']=authorize_request(self.profile,r,'合成用户确认本段文字，保存到指定知识页')
            self.assertEqual(save_change(self.profile,r,self.adapter)['status'],'saved')
        context=load_context(self.profile,list(facts),self.adapter)
        for key,item in context['knowledge'].items():self.assertEqual(item['content'],facts[key]);self.assertEqual(item['source'],'feishu')
        # Creative draft is a human-readable synthetic fixture, never claimed as user effectiveness.
        draft='访谈时，对方说想自动化写报告。继续追问才知道，每次最费时的是整理原始记录。\n\n先把哪一步耗时问清楚，再决定做什么工具。这次经历让我想把需求访谈放在方案前面。'
        r={'operation_id':'save-synthetic-work','target':{'knowledge_id':'operations.base','obj_type':'bitable','table_key':'moments_works','key_field':'作品键','object_key':'nxw:synthetic:journey'},'action':'create','base_revision':None,'content':{'作品键':'nxw:synthetic:journey','作品标题':'先问清哪一步耗时','第一版':draft,'发表状态':'待发布','沉淀状态':'待沉淀'}}
        self.assertEqual(save_change(self.profile,r,self.adapter)['status'],'blocked');self.assertEqual(self.adapter.record_writes,0)
        r['authorization']=authorize_request(self.profile,r,'合成用户允许保存第一版，不填写待发布版或已发布版')
        self.assertEqual(save_change(self.profile,r,self.adapter)['status'],'saved')
        self.assertEqual(save_change(self.profile,r,self.adapter)['status'],'saved');self.assertEqual(self.adapter.record_writes,1)
        new_host=copy.deepcopy(self.adapter)
        restored=load_context(self.profile,['content.strategy','ip.profile'],new_host)
        self.assertEqual(restored['knowledge']['ip.profile']['content'],facts['ip.profile'])
        record=new_host.lookup(r['target'],r['operation_id'])
        self.assertEqual(record['content']['第一版'],draft);self.assertNotIn('已发布版',record['content']);self.assertNotIn('待发布版',record['content'])
        self.assertEqual(record['content']['沉淀状态'],'待沉淀')

if __name__=='__main__':unittest.main()
