import copy
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from runtime.models import file_digest,read_json,write_json
from runtime.paths import create_profile
from runtime.releases import build_manifest,verify_release,apply_release,rollback_release,installation_state_path,recover_release,check_update

class Releases(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        private=self.root/'private';self.profile=private/'profiles'/create_profile(private,'synthetic-user','synthetic-space')
        write_json(self.profile/'local-rules.json',{'schema_version':1,'rules':[{'id':'r1','instruction':'先澄清具体耗时环节','channels':['moments'],'surfaces':['body'],'materials':['general'],'status':'active','basis':'user_confirmed','source':'synthetic user confirmation','scope':'channel'}]})
        write_json(self.profile/'snapshots/example.json',{'content':'synthetic private content'})
        write_json(self.profile/'pending/op.json',{'status':'pending','content':'synthetic pending'})
        self.old=self.root/'installed';self.new=self.root/'new-source';self.make_core(self.old,'4.0.0-beta.0');self.make_core(self.new,'4.0.0-beta.1')
        self.archive=self.pack(self.new);self.private_before=self.hashes(self.profile)
    def hashes(self,path):return {str(p.relative_to(path)):file_digest(p) for p in path.rglob('*') if p.is_file()}
    def make_core(self,path,version):
        (path/'scripts').mkdir(parents=True)
        (path/'SKILL.md').write_text('---\nname: nianxiang-content-os\ndescription: Synthetic update test\n---\nVersion: '+version+'\n')
        (path/'scripts/manage.py').write_text('import json\nprint(json.dumps({"private_root_outside_skill":True,"release_management":"available"}))\n')
        write_json(path/'release-manifest.json',build_manifest(path,version))
    def pack(self,path,extras=None):
        dest=self.root/('package-'+str(len(list(self.root.glob('package-*'))))+'.zip')
        with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
            for p in sorted(path.rglob('*')):
                if p.is_file():z.write(p,'nianxiang-content-os/'+str(p.relative_to(path)))
            for name,value in (extras or {}).items():z.writestr(name,value)
        return dest
    def apply(self,**kwargs):return apply_release(self.archive,self.old,self.profile,'用户授权更新这个合成本地包',**kwargs)
    def test_verify_and_no_source_check(self):
        outcome=verify_release(self.archive,read_json(self.new/'release-manifest.json'))
        self.assertEqual(outcome['status'],'verified');self.assertEqual(check_update(outcome['manifest'])['status'],'not_configured')
    def test_digest_error_unlisted_file_and_manifest_mismatch_rejected(self):
        for change in ('digest','extra','manifest'):
            with self.subTest(change=change):
                new=self.root/change;shutil.copytree(self.new,new)
                if change=='digest':(new/'SKILL.md').write_text('tampered')
                if change=='extra':(new/'unexpected.txt').write_text('unlisted')
                manifest=read_json(self.new/'release-manifest.json')
                if change=='manifest':manifest['version']='wrong'
                self.assertEqual(verify_release(self.pack(new),manifest)['status'],'blocked')
    def test_archive_escape_symlink_and_duplicate_rejected(self):
        for name in ('../escape','nianxiang-content-os/../../escape','/absolute','nianxiang-content-os/a\\b','nianxiang-content-os/local/local-config.json'):
            with self.subTest(name=name):self.assertEqual(verify_release(self.pack(self.new,{name:'bad'}),read_json(self.new/'release-manifest.json'))['status'],'blocked')
        for kind in ('symlink','duplicate'):
            archive=self.pack(self.new)
            with zipfile.ZipFile(archive,'a') as z:
                info=zipfile.ZipInfo('nianxiang-content-os/link')
                if kind=='symlink':info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(info,'/outside')
                else:z.writestr('nianxiang-content-os/SKILL.md','duplicate')
            self.assertEqual(verify_release(archive,read_json(self.new/'release-manifest.json'))['status'],'blocked')
    def test_incompatible_schema_or_layout_keeps_core_and_private(self):
        before=self.hashes(self.old)
        for key in ('knowledge_schema_version','data_layout_version'):
            m=read_json(self.new/'release-manifest.json');m[key]=99;write_json(self.new/'release-manifest.json',m)
            self.archive=self.pack(self.new)
            self.assertEqual(self.apply()['status'],'blocked');self.assertEqual(self.hashes(self.old),before)
        self.assertEqual(self.hashes(self.profile),self.private_before)
    def test_no_consent_and_local_edit_keep_everything(self):
        before=self.hashes(self.old)
        self.assertEqual(apply_release(self.archive,self.old,self.profile,'')['status'],'blocked')
        self.assertEqual(self.hashes(self.old),before);self.assertFalse(installation_state_path(self.old).exists())
        (self.old/'SKILL.md').write_text('my local edit')
        self.assertEqual(self.apply()['status'],'conflict');self.assertEqual((self.old/'SKILL.md').read_text(),'my local edit')
    def test_apply_rollback_preserve_private_and_rules(self):
        before=self.hashes(self.old)
        self.assertEqual(self.apply()['status'],'updated')
        self.assertEqual(self.hashes(self.old),self.hashes(self.new));self.assertEqual(self.hashes(self.profile),self.private_before)
        from runtime.rules import select_confirmed_rules
        self.assertEqual(select_confirmed_rules(read_json(self.profile/'local-rules.json'),{'channel':'moments','surface':'body','material':'general'})[0]['id'],'r1')
        state=installation_state_path(self.old)
        self.assertEqual(rollback_release(self.old,state,'用户授权回退')['status'],'rolled_back')
        self.assertEqual(self.hashes(self.old),before);self.assertEqual(self.hashes(self.profile),self.private_before)
        self.assertEqual(rollback_release(self.old,state,'用户授权核对回退')['status'],'rolled_back')
    def test_health_failure_restores_exact_old_core(self):
        before=self.hashes(self.old)
        with patch('runtime.releases.health_check',side_effect=lambda root,manifest:not(root==self.old and manifest['version']=='4.0.0-beta.1')):outcome=self.apply()
        self.assertEqual(outcome['status'],'rolled_back');self.assertEqual(self.hashes(self.old),before);self.assertEqual(self.hashes(self.profile),self.private_before)
    def test_busy_lock_and_profile_overlap_blocked(self):
        from runtime.models import profile_lock
        control=installation_state_path(self.old).parent;control.mkdir(parents=True)
        with profile_lock(control):self.assertEqual(self.apply()['status'],'blocked')
        self.assertEqual(apply_release(self.archive,self.old,self.old,'update')['status'],'blocked')
    def test_rollback_local_edits_conflict_and_missing_consent_blocks(self):
        self.apply();state=installation_state_path(self.old)
        self.assertEqual(rollback_release(self.old,state)['status'],'blocked')
        (self.old/'SKILL.md').write_text('edit after update')
        self.assertEqual(rollback_release(self.old,state,'rollback')['status'],'conflict')
        self.assertEqual((self.old/'SKILL.md').read_text(),'edit after update')
    def test_recovery_rechecks_old_health_before_reporting_ready(self):
        self.apply();state=installation_state_path(self.old)
        self.assertEqual(rollback_release(self.old,state,'rollback')['status'],'rolled_back')
        with patch('runtime.releases.health_check',return_value=False):
            self.assertEqual(recover_release(self.old,state,'recover')['status'],'recovery_required')

    def test_restored_core_mutation_during_health_is_not_reported_rolled_back(self):
        self.apply();state=installation_state_path(self.old)
        def mutating_health(root,manifest):
            (root/'SKILL.md').write_text('changed during restored health');return True
        with patch('runtime.releases.health_check',side_effect=mutating_health):
            self.assertNotEqual(rollback_release(self.old,state,'rollback')['status'],'rolled_back')
        self.assertEqual(read_json(state)['phase'],'recovery_required')

    def test_manifest_builder_rejects_case_variant_private_names(self):
        from runtime.models import NianxiangError
        for name in ('Private/secret.json','LOCAL/LOCAL-CONFIG.JSON','tasks/task.json','derived/USER.md','rules.local.json','business-conventions.md'):
            with self.subTest(name=name):
                core=self.root/('case-core-'+name.replace('/','-'));shutil.copytree(self.new,core)
                file=core/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_text('synthetic secret')
                with self.assertRaises(NianxiangError):build_manifest(core,'4.0.0-beta.1')

    def test_recovery_on_active_update_does_not_undo_success(self):
        self.apply();before=self.hashes(self.old)
        self.assertEqual(recover_release(self.old,installation_state_path(self.old),'核对是否需恢复')['status'],'active')
        self.assertEqual(self.hashes(self.old),before)

    def test_backup_root_symlink_cannot_replace_installed_core(self):
        self.apply();state=installation_state_path(self.old);journal=read_json(state)
        backup=state.parent/journal['backup_name'];external=self.root/'redirected-backup'
        backup.rename(external);backup.symlink_to(external,target_is_directory=True)
        before=self.hashes(self.old)
        self.assertEqual(rollback_release(self.old,state,'rollback')['status'],'blocked')
        self.assertFalse(self.old.is_symlink());self.assertEqual(self.hashes(self.old),before)
        self.assertEqual(self.hashes(self.profile),self.private_before)

    def test_partial_rollback_failure_reports_recovery_required_and_recovers(self):
        self.apply();state=installation_state_path(self.old)
        import runtime.releases as release
        original=release.move_core
        def denied_backup(source,dest):
            if source.name.startswith('old-core-'):raise PermissionError('synthetic backup rename denied')
            return original(source,dest)
        with patch('runtime.releases.move_core',side_effect=denied_backup):
            self.assertEqual(rollback_release(self.old,state,'rollback')['status'],'recovery_required')
        self.assertFalse(self.old.exists());self.assertEqual(read_json(state)['phase'],'recovery_required')
        self.assertEqual(recover_release(self.old,state,'recover')['status'],'rolled_back')
        self.assertEqual(self.hashes(self.profile),self.private_before)

    def test_first_install_requires_valid_baseline_manifest(self):
        (self.old/'release-manifest.json').unlink();before=self.hashes(self.old)
        self.assertEqual(self.apply()['status'],'blocked');self.assertEqual(self.hashes(self.old),before)
    def test_interrupted_switch_can_recover_old_core(self):
        before=self.hashes(self.old)
        import runtime.releases as release
        original=release.move_core
        def crash(source,dest):
            original(source,dest)
            if source==self.old:raise KeyboardInterrupt('synthetic crash after backup rename')
        with patch('runtime.releases.move_core',side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):self.apply()
        self.assertFalse(self.old.exists())
        self.assertEqual(recover_release(self.old,installation_state_path(self.old),'用户授权恢复中断更新')['status'],'rolled_back')
        self.assertEqual(self.hashes(self.old),before);self.assertEqual(self.hashes(self.profile),self.private_before)

if __name__=='__main__':unittest.main()
