import copy
from test_knowledge_runtime import KnowledgeRuntime, FakeFeishu
from runtime.models import NianxiangError, read_json

class PersonalFake(FakeFeishu):
    def __init__(self, profile):
        super().__init__(); self.docs={}; self.fail_key=None; self.written_keys=set()
        config=read_json(profile/'local-config.json')
        for key,m in config['knowledge_map'].items():
            if m['obj_type']=='docx':
                self.docs[key]={'account_id':self.account,'space_id':self.space,**{k:v for k,v in m.items() if k!='expected_title'},'title':m['expected_title'],'revision':1,'content':'synthetic '+key}
    def get_node(self,target):
        return copy.deepcopy(self.docs[target['knowledge_id']]) if target['knowledge_id'] in self.docs else super().get_node(target)
    def read(self,key):
        if self.offline or (self.fail_key==key and key in self.written_keys): raise NianxiangError('offline','unavailable')
        return copy.deepcopy(self.docs[key])
    def write(self,request):
        if request['target']['obj_type']=='bitable': return super().write(request)
        self.writes+=1; self.written_keys.add(request['target']['knowledge_id']); doc=self.docs[request['target']['knowledge_id']]; c=request['content']
        doc['content']=doc['content']+'\n'+c['text'] if request['action']=='append' else doc['content'].replace(c['pattern'],c['replacement'],1)
        doc['revision']+=1; return copy.deepcopy(doc)

class Fixture:
    def setUp(self):
        KnowledgeRuntime.setUp(self); self.adapter=PersonalFake(self.profile)

def rule(basis='user_explicit',status='active'):
    return {'id':'r-one','instruction':'正文具体，不编造效果。','channels':['moments'],'surfaces':['body'],'materials':['*'],'status':status,'basis':basis,'source':'synthetic:user-request','confirmed_at':None}

def collaboration():
    return {'schema_version':1,'preferred_name':'测试作者','preferred_name_evidence':{'status':'active','basis':'user_explicit','source':'synthetic:user-request','confirmed_at':None},'preferences':[],'boundaries':[]}
