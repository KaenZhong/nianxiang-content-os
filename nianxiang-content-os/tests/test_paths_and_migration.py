import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from runtime.paths import resolve_data_root, resolve_profile, create_profile, plan_migration, apply_migration
from runtime.models import NianxiangError

class PrivatePaths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.skill = self.root/'skill'; self.skill.mkdir()
        self.data = self.root/'private'
        self.pid = create_profile(self.data, 'synthetic-account', 'synthetic-space')
        self.profile = self.data/'profiles'/self.pid
    def test_explicit_root_beats_environment_and_default_is_home(self):
        with patch.dict(os.environ, {'NIANXIANG_HOME': str(self.root/'env')}):
            self.assertEqual(resolve_data_root(self.skill, self.data), self.data)
            self.assertEqual(resolve_data_root(self.skill), self.root/'env')
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_data_root(self.skill), Path.home()/'.nianxiang')
    def test_never_guesses_profile(self):
        with self.assertRaisesRegex(NianxiangError, 'selection_required'):
            resolve_profile(self.skill, self.data, None)
        self.assertEqual(resolve_profile(self.skill, self.data, self.pid), self.profile)
    def test_rejects_inside_skill_parent_skill_and_symlink_escape(self):
        for location in (self.skill, self.skill/'local', self.root):
            with self.assertRaises(NianxiangError): resolve_data_root(self.skill, location)
        alias=self.root/'alias'; alias.symlink_to(self.skill, target_is_directory=True)
        with self.assertRaises(NianxiangError): resolve_data_root(self.skill, alias/'local')
    def test_profile_ids_are_uuid_and_account_isolated(self):
        with self.assertRaises(NianxiangError): resolve_profile(self.skill, self.data, '../skill')
        other=create_profile(self.data, 'other-account', 'other-space')
        self.assertNotEqual(other,self.pid)
        self.assertNotEqual(resolve_profile(self.skill,self.data,other),self.profile)
    def legacy(self):
        legacy=self.root/'old-local';legacy.mkdir()
        (legacy/'user-profile.json').write_text('{"preferred_name":"测试昵称"}')
        (legacy/'content-strategy-snapshot.md').write_text('synthetic strategy')
        (legacy/'local-config.example.json').write_text('public example')
        return legacy
    def test_preview_writes_nothing_copy_is_lossless_repeat_is_safe(self):
        legacy=self.legacy(); before=set(self.profile.rglob('*'))
        plan=plan_migration(legacy,self.profile)
        self.assertEqual(set(self.profile.rglob('*')),before)
        self.assertEqual(len(plan['files']),2)
        with self.assertRaises(NianxiangError): apply_migration(plan,'')
        result=apply_migration(plan,'user confirmed copy')
        self.assertEqual(result['status'],'migrated')
        for item in plan['files']:
            self.assertEqual(Path(item['source']).read_bytes(),Path(item['destination']).read_bytes())
            self.assertTrue(Path(item['source']).exists())
        self.assertEqual(apply_migration(plan,'same consent')['status'],'migrated')
        state=json.loads((self.profile/'state.json').read_text())
        self.assertEqual(state['legacy_snapshot_status'],'requires_source_verification')
    def test_conflict_stops_before_copying_anything(self):
        legacy=self.legacy(); (self.profile/'user-profile.json').write_text('existing')
        plan=plan_migration(legacy,self.profile)
        with self.assertRaises(NianxiangError): apply_migration(plan,'copy consent')
        self.assertFalse((self.profile/'content-strategy-snapshot.md').exists())
        self.assertEqual((self.profile/'user-profile.json').read_text(),'existing')
    def test_migration_config_bound_to_chosen_space(self):
        legacy=self.legacy()
        (legacy/'local-config.json').write_text('{"space_id":"foreign-space"}')
        with self.assertRaises(NianxiangError):apply_migration(plan_migration(legacy,self.profile),'copy')
        self.assertFalse((self.profile/'user-profile.json').exists())

    def test_changed_source_and_symlink_do_not_migrate(self):
        legacy=self.legacy();plan=plan_migration(legacy,self.profile)
        (legacy/'user-profile.json').write_text('changed since preview')
        with self.assertRaises(NianxiangError): apply_migration(plan,'copy consent')
        self.assertFalse((self.profile/'user-profile.json').exists())
        (legacy/'user-profile.json').unlink();(legacy/'user-profile.json').symlink_to(self.root/'missing')
        with self.assertRaises(NianxiangError): plan_migration(legacy,self.profile)

if __name__=='__main__': unittest.main()
