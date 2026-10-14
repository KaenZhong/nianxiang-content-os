import copy,json,unittest
import test_knowledge_runtime
from runtime.models import read_json
from validate_local_config import validate
from init_local_config import select_unique,InitError
import re

class MethodsContract(unittest.TestCase):
    setUp=test_knowledge_runtime.KnowledgeRuntime.setUp
    def test_methods_mapping_requires_direct_parent_and_exact_title(self):
        base=read_json(self.profile/'local-config.json')
        validate(base)
        for key,value in [('parent_node_token','foreign-parent'),('expected_title','内容方法')]:
            candidate=copy.deepcopy(base);candidate['knowledge_map']['content.methods'][key]=value
            with self.assertRaises(ValueError):validate(candidate)
    def test_schema4_is_rejected_by_runtime_but_available_for_upgrade_validation(self):
        old=read_json(self.profile/'local-config.json');old['schema_version']=4
        old['knowledge_map'].pop('content.methods');old['write_targets']['sync_candidate_knowledge_ids'].remove('content.methods')
        validate(old,schema_version=4)
        with self.assertRaises(ValueError):validate(old)
    def test_methods_discovery_rejects_duplicate_foreign_or_wrong_type(self):
        node={'space_id':'space-a','parent_node_token':'methods-root','title':'01｜创作方法与规则','obj_type':'docx','node_token':'child','obj_token':'doc'}
        pattern=re.compile(r'^01｜创作方法与规则$')
        for candidates in ([node,node],[{**node,'space_id':'foreign'}],[{**node,'parent_node_token':'foreign'}],[{**node,'obj_type':'bitable'}]):
            with self.assertRaises(InitError):select_unique(candidates,pattern,'content.methods','space-a','methods-root')
