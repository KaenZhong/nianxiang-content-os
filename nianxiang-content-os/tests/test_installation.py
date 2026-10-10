"""Install-time discovery and explicit private-directory confirmation, using temporary data."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from runtime.models import NianxiangError, read_json, write_json
from runtime.paths import create_profile
from runtime.installation import scan_roots, plan_installation, apply_installation, require_initialized

SKILL=Path(__file__).resolve().parents[1]

class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name).resolve()/'home';self.home.mkdir()
        self.root=self.home/'.nianxiang'
        self.env=patch.dict(os.environ,{},clear=True);self.env.start();self.addCleanup(self.env.stop)
        self.homemock=patch('pathlib.Path.home',return_value=self.home)
        self.homemock.start();self.addCleanup(self.homemock.stop)

    def plan(self,**kw):
        return plan_installation(SKILL,**kw)

    def apply(self,plan,path=None,consent='同意在这个完整路径创建私人目录'):
        return apply_installation(SKILL,plan,path or str(self.root),consent)

    def blocked(self,code,fn):
        with self.assertRaises(NianxiangError) as caught:fn()
        self.assertEqual(caught.exception.code,code)

    def test_scan_and_preview_do_not_create_or_contact_remote(self):
        self.assertEqual(scan_roots(SKILL)['status'],'none_found')
        plan=self.plan()
        self.assertEqual(plan['action'],'create')
        self.assertEqual(plan['data_root'],str(self.root))
        self.assertFalse(self.root.exists())

    def test_confirmation_is_required_and_bound_to_full_path(self):
        plan=self.plan()
        self.blocked('authorization_required',lambda:self.apply(plan,consent=''))
        self.blocked('path_confirmation_mismatch',lambda:self.apply(plan,str(self.home/'other')))
        self.assertFalse(self.root.exists())

    def test_create_readback_and_repeated_install_are_idempotent(self):
        self.assertEqual(self.apply(self.plan())['status'],'initialized')
        state=require_initialized(SKILL,self.root)
        self.assertEqual(state['data_root'],str(self.root))
        self.assertEqual(state['persistence_verification'],'declared')
        before=(self.root/'data-root.json').read_bytes()
        plan=self.plan()
        self.assertEqual(plan['action'],'reuse')
        self.assertEqual(apply_installation(SKILL,plan,str(self.root),None)['status'],'reused')
        self.assertEqual(before,(self.root/'data-root.json').read_bytes())
        if os.name!='nt':
            self.assertEqual(self.root.stat().st_mode&0o777,0o700)
            self.assertEqual((self.root/'data-root.json').stat().st_mode&0o777,0o600)

    def test_existing_profiles_reused_without_losing_contents(self):
        pid=create_profile(self.root,'synthetic-user','synthetic-space')
        original=(self.root/'profiles'/pid/'state.json').read_bytes()
        scan=scan_roots(SKILL)
        self.assertEqual(scan['status'],'existing_found')
        plan=self.plan()
        self.assertEqual(plan['action'],'adopt')
        self.apply(plan)
        self.assertEqual(original,(self.root/'profiles'/pid/'state.json').read_bytes())

    def test_env_and_default_both_scanned_before_new_root(self):
        create_profile(self.root,'synthetic-user','synthetic-space')
        another=self.home/'cloud-data';os.environ['NIANXIANG_HOME']=str(another)
        plan=self.plan()
        self.assertEqual(plan['data_root'],str(self.root))
        self.assertFalse(another.exists())

    def test_multiple_existing_roots_require_explicit_selection(self):
        create_profile(self.root,'synthetic-user','synthetic-space')
        another=self.home/'other';create_profile(another,'synthetic-user','synthetic-space')
        os.environ['NIANXIANG_HOME']=str(another)
        self.blocked('directory_selection_required',lambda:self.plan())
        self.assertEqual(self.plan(data_dir=another)['data_root'],str(another))

    def test_unrelated_contents_and_redirects_are_not_adopted(self):
        self.root.mkdir();(self.root/'note.txt').write_text('retain me')
        self.blocked('directory_conflict',lambda:self.plan())
        self.assertEqual((self.root/'note.txt').read_text(),'retain me')
        redirect=self.home/'redirect';redirect.symlink_to(self.root,target_is_directory=True)
        self.blocked('invalid_private_root',lambda:self.plan(data_dir=redirect))
        self.blocked('invalid_private_root',lambda:self.plan(data_dir=SKILL/'private'))

    def test_preview_change_blocks_apply(self):
        plan=self.plan();self.root.mkdir();(self.root/'new.txt').write_text('concurrent')
        self.blocked('installation_changed',lambda:self.apply(plan))
        self.assertFalse((self.root/'data-root.json').exists())

    def test_cloud_requires_durable_location_evidence(self):
        self.blocked('persistence_required',lambda:self.plan(environment='cloud'))
        self.blocked('persistence_required',lambda:self.plan(environment='cloud',persistence='persistent-volume'))
        plan=self.plan(environment='cloud',persistence='persistent-volume',evidence='平台设置显示用户卷持久挂载')
        outcome=self.apply(plan)
        self.assertEqual(outcome['persistence_verification'],'declared')
        self.assertFalse(outcome['restart_tested'])

    def test_cli_cannot_bypass_initialization_via_profile_create(self):
        result=subprocess.run([sys.executable,'-B',str(SKILL/'scripts/manage.py'),'--data-dir',str(self.root),'profile','create','--space-id','synthetic-space','--consent','建立配置档'],capture_output=True,text=True)
        self.assertEqual(result.returncode,2)
        self.assertEqual(json.loads(result.stdout)['message'],'installation_required')
        self.assertFalse(self.root.exists())

    def test_copied_or_tampered_marker_does_not_count_as_initialized(self):
        self.apply(self.plan())
        state=read_json(self.root/'data-root.json');state['data_root']=str(self.home/'wrong')
        write_json(self.root/'data-root.json',state)
        self.blocked('directory_conflict',lambda:require_initialized(SKILL,self.root))

    @unittest.skipIf(os.name=='nt' or (hasattr(os,'geteuid') and os.geteuid()==0),'POSIX user permissions required')
    def test_readonly_existing_root_cannot_report_successful_reuse(self):
        self.apply(self.plan());os.chmod(self.root,0o500)
        try:
            plan=self.plan()
            self.blocked('directory_not_writable',lambda:self.apply(plan))
        finally:os.chmod(self.root,0o700)

    def test_environment_change_requires_location_recheck(self):
        self.apply(self.plan())
        self.blocked('environment_mismatch',lambda:self.plan(environment='cloud'))

    def test_cli_installation_journey_without_remote_tools(self):
        planpath=self.home/'preview.json'
        env={'HOME':str(self.home),'PATH':os.environ.get('PATH','')}
        def call(*args):
            result=subprocess.run([sys.executable,'-B',str(SKILL/'scripts/manage.py'),*args],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            return json.loads(result.stdout)
        self.assertEqual(call('install','scan')['status'],'none_found')
        plan=call('install','plan','--environment','local','--output',str(planpath))
        self.assertFalse(self.root.exists())
        result=call('install','apply','--plan',str(planpath),'--confirmed-path',plan['data_root'],'--consent','确认使用这个完整路径')
        self.assertEqual(result['status'],'initialized')
        self.assertTrue((self.root/'data-root.json').is_file())

if __name__=='__main__':unittest.main()
