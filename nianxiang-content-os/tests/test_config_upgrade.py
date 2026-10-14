import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from runtime.models import digest, read_json, write_json
from runtime.paths import create_profile
from runtime.config_upgrade import plan_config_upgrade, apply_config_upgrade


class UpgradeAdapter:
    def __init__(self, config):
        self.config = copy.deepcopy(config)
        self.account = 'account-a'
        self.nodes = {}
        for key, mapping in config['knowledge_map'].items():
            self.nodes[key] = {**mapping, 'title': mapping['expected_title'], 'space_id': 'space-a', 'account_id': self.account, 'revision': 1, 'content': 'synthetic ' + key}
        parent = config['knowledge_map']['methodology.current']['node_token']
        self.nodes['content.methods'] = {'title': '01｜创作方法与规则', 'node_token': 'methods-node', 'obj_token': 'methods-doc', 'obj_type': 'docx', 'parent_node_token': parent, 'space_id': 'space-a', 'account_id': self.account, 'revision': 1, 'content': 'synthetic methods'}
        self.children = [self.nodes['content.methods']]
        self.writes = 0
    def get_account(self): return {'identity': 'user', 'account_id': self.account}
    def get_node(self, target): return copy.deepcopy(self.nodes[target['knowledge_id']])
    def list_nodes(self, parent): return copy.deepcopy(self.children)
    def read(self, key): return copy.deepcopy(self.nodes[key])
    def write(self, request): self.writes += 1; raise AssertionError('no remote mutation')


class ConfigUpgrade(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.profile = root / 'profiles' / create_profile(root, 'account-a', 'space-a')
        config = json.loads((Path(__file__).resolve().parents[1] / 'local/local-config.example.json').read_text())
        config['schema_version'] = 4
        config['knowledge_map'].pop('content.methods', None)
        config['write_targets']['sync_candidate_knowledge_ids'] = [x for x in config['write_targets']['sync_candidate_knowledge_ids'] if x != 'content.methods']
        config['space_id'] = 'space-a'
        for i, (key, item) in enumerate(config['knowledge_map'].items()):
            item.update(node_token='node-'+str(i), obj_token='doc-'+str(i), parent_node_token='parent-'+str(i))
        for keys, parent in [(('content.strategy','audience.needs','ip.profile','expression.baseline'), 'positioning'), (('cocreation.index','content.assets'), 'assets'), (('operations.index','content.archives','content.campaigns','content.reviews'), 'operations')]:
            for key in keys: config['knowledge_map'][key]['parent_node_token'] = parent
        config['knowledge_map']['operations.base']['parent_node_token'] = config['knowledge_map']['operations.index']['node_token']
        for key, item in config['base_tables'].items(): item['table_id'] = 'table-'+key; item['auxiliary_field'] = 'keep'
        config['base_tables']['works_index'] = {'expected_title': '旧作品索引（迁移备份）', 'table_id': 'old', 'other': [1]}
        config['other'] = {'preserve': True}
        write_json(self.profile/'local-config.json', config)
        state = read_json(self.profile/'state.json'); state['active'] = True; write_json(self.profile/'state.json', state)
        self.original = config
        self.adapter = UpgradeAdapter(config)
    def test_preview_is_read_only_and_apply_preserves_private_data(self):
        before = (self.profile/'local-config.json').read_bytes()
        for name in ('pending/op.json', 'tasks/task.json', 'snapshots/old.json', 'derived/personal-context.json'):
            write_json(self.profile/name, {'private': name})
        plan = plan_config_upgrade(self.profile, self.adapter)
        self.assertEqual(plan['status'], 'preview')
        self.assertEqual((self.profile/'local-config.json').read_bytes(), before)
        result = apply_config_upgrade(self.profile, plan, self.adapter, 'user:执行吧')
        self.assertEqual(result['status'], 'upgraded')
        upgraded = read_json(self.profile/'local-config.json')
        self.assertEqual(upgraded['schema_version'], 5)
        self.assertEqual(upgraded['base_tables'], self.original['base_tables'])
        self.assertEqual(upgraded['other'], self.original['other'])
        self.assertEqual({k:v for k,v in upgraded['knowledge_map'].items() if k != 'content.methods'}, self.original['knowledge_map'])
        self.assertFalse(read_json(self.profile/'state.json')['active'])
        self.assertEqual(read_json(self.profile/result['backup']), self.original)
        for name in ('pending/op.json', 'tasks/task.json', 'snapshots/old.json', 'derived/personal-context.json'):
            self.assertEqual(read_json(self.profile/name), {'private': name})
        self.assertEqual(apply_config_upgrade(self.profile, plan, self.adapter, 'user:执行吧')['status'], 'upgraded')
        self.assertEqual(self.adapter.writes, 0)
    def test_account_or_node_mismatch_and_ambiguous_child_block(self):
        self.adapter.account = 'other'
        self.assertEqual(plan_config_upgrade(self.profile, self.adapter)['code'], 'account_mismatch')
        self.adapter.account = 'account-a'
        self.adapter.nodes['content.assets']['title'] = 'changed'
        self.assertEqual(plan_config_upgrade(self.profile, self.adapter)['code'], 'target_mismatch')
        self.adapter.nodes['content.assets']['title'] = self.original['knowledge_map']['content.assets']['expected_title']
        self.adapter.children *= 2
        self.assertEqual(plan_config_upgrade(self.profile, self.adapter)['code'], 'ambiguous_methods_source')
    def test_historical_or_malformed_root_rules_require_migration(self):
        for body in ('NIANXIANG_PERSONAL_RULES_V1={bad}', 'NIANXIANG_PERSONAL_RULES_V1={"schema_version":1,"rules":[{}]}', 'NIANXIANG_PERSONAL_RULES_V1={"schema_version":1,"rules":[]}\nNIANXIANG_PERSONAL_RULES_V1={"schema_version":1,"rules":[]}'):
            self.adapter.nodes['methodology.current']['content'] = body
            self.assertEqual(plan_config_upgrade(self.profile, self.adapter)['code'], 'private_rules_migration_required')
    def test_valid_nonempty_root_rules_block_but_empty_machine_segment_is_safe(self):
        rule = {'id': 'historical', 'instruction': 'keep this rule', 'channels': ['moments'], 'surfaces': ['body'], 'materials': ['*'], 'status': 'trial', 'basis': 'user_explicit', 'source': 'synthetic', 'confirmed_at': None}
        self.adapter.nodes['methodology.current']['content'] = 'NIANXIANG_PERSONAL_RULES_V1=' + json.dumps({'schema_version': 1, 'rules': [rule]})
        self.assertEqual(plan_config_upgrade(self.profile, self.adapter)['code'], 'private_rules_migration_required')
        self.adapter.nodes['methodology.current']['content'] = 'NIANXIANG_PERSONAL_RULES_V1=' + json.dumps({'schema_version': 1, 'rules': []})
        self.adapter.nodes['content.methods']['content'] = 'NIANXIANG_PERSONAL_RULES_V1=' + json.dumps({'schema_version': 1, 'rules': [rule]})
        self.assertEqual(plan_config_upgrade(self.profile, self.adapter)['status'], 'preview')
    def test_changed_local_config_and_tampered_backup_fail_closed(self):
        plan = plan_config_upgrade(self.profile, self.adapter)
        altered = copy.deepcopy(self.original); altered['other']['preserve'] = False
        write_json(self.profile/'local-config.json', altered)
        self.assertEqual(apply_config_upgrade(self.profile, plan, self.adapter, 'yes')['code'], 'configuration_changed')
        write_json(self.profile/'local-config.json', self.original)
        result = apply_config_upgrade(self.profile, plan, self.adapter, 'yes')
        self.assertEqual(result['status'], 'upgraded')
        write_json(self.profile/result['backup'], altered)
        self.assertEqual(apply_config_upgrade(self.profile, plan, self.adapter, 'yes')['code'], 'backup_conflict')
    def test_tampered_plan_changed_source_and_consent_block(self):
        plan = plan_config_upgrade(self.profile, self.adapter)
        self.assertEqual(apply_config_upgrade(self.profile, plan, self.adapter, '')['code'], 'authorization_required')
        altered = copy.deepcopy(plan); altered['candidate']['other'] = {}
        self.assertEqual(apply_config_upgrade(self.profile, altered, self.adapter, 'yes')['code'], 'invalid_plan')
        self.adapter.nodes['content.methods']['revision'] = 2
        self.assertEqual(apply_config_upgrade(self.profile, plan, self.adapter, 'yes')['code'], 'source_changed')
        self.assertEqual(read_json(self.profile/'local-config.json'), self.original)
    def test_invalid_child_rules_and_cross_space_child_block(self):
        self.adapter.nodes['content.methods']['content'] = 'NIANXIANG_PERSONAL_RULES_V1={bad}'
        self.assertEqual(plan_config_upgrade(self.profile, self.adapter)['code'], 'invalid_personal_source')
        self.adapter.nodes['content.methods']['content'] = 'synthetic'
        self.adapter.nodes['content.methods']['space_id'] = 'other'
        self.assertEqual(plan_config_upgrade(self.profile, self.adapter)['status'], 'blocked')

if __name__ == '__main__': unittest.main()
