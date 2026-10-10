"""Name migration exercises real cores, journals, ZIPs and fault recovery."""
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import uuid
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import runtime.releases as release
from runtime.models import file_digest,read_json,write_json
from runtime.paths import create_profile

OLD='nianxiang-content-studio'
NEW='nianxiang-content-os'

class NameMigration(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();private=self.root/'private'
        self.profile=private/'profiles'/create_profile(private,'synthetic-user','synthetic-space')
        write_json(self.profile/'pending/example.json',{'status':'uncertain','body':'synthetic private'})
        self.old=self.root/OLD;self.new=self.root/NEW;self.source=self.root/'new-source'
        self.make_core(self.old,OLD,'4.0.0-beta.1');self.make_core(self.source,NEW,'4.0.0-beta.2')
        self.archive=self.pack(self.source,NEW);self.before=self.hashes(self.profile)
    def hashes(self,p):return {x.relative_to(p).as_posix():file_digest(x) for x in p.rglob('*') if x.is_file()}
    def make_core(self,p,name,version):
        (p/'scripts').mkdir(parents=True)
        (p/'SKILL.md').write_text('---\nname: '+name+'\ndescription: synthetic migration\n---\n'+version+'\n')
        (p/'scripts/manage.py').write_text('import json\nprint(json.dumps({"private_root_outside_skill":True}))\n')
        files={x.relative_to(p).as_posix():{'sha256':hashlib.sha256(x.read_bytes()).hexdigest(),'size':x.stat().st_size} for x in p.rglob('*') if x.is_file()}
        write_json(p/'release-manifest.json',{'schema_version':1,'name':name,'version':version,'entry':'SKILL.md','knowledge_schema_version':4,'data_layout_version':1,'release_source':None,'files':files})
    def pack(self,p,name):
        dest=self.root/(name+'.zip')
        with zipfile.ZipFile(dest,'w') as z:
            for x in p.rglob('*'):
                if x.is_file():z.write(x,name+'/'+x.relative_to(p).as_posix())
        return dest
    def preview(self):
        # Missing callable is a feature failure, not an import/environment error.
        self.assertTrue(callable(getattr(release,'plan_name_migration',None)),'name migration preview is missing')
        return release.plan_name_migration(self.old,self.new,self.profile)
    def apply(self,plan=None):
        plan=plan or self.preview()
        self.assertTrue(callable(getattr(release,'apply_name_migration',None)),'name migration apply is missing')
        return release.apply_name_migration(plan,self.archive,'用户授权合成旧名安装迁移')
    def test_managed_rename_preserves_profile_and_journal(self):
        state=release.installation_state_path(self.old);state.parent.mkdir(parents=True)
        old=read_json(self.old/'release-manifest.json');token=str(uuid.uuid4())
        prior={'schema_version':1,'skill_root':str(self.old),'transaction_id':token,'backup_name':'old-core-'+token,'stage_name':'stage-'+token,'failed_name':'failed-core-'+token,'from_manifest':old,'to_manifest':old,'active_manifest':old,'phase':'active'}
        write_json(state,prior)
        self.assertEqual(self.apply()['status'],'migrated')
        self.assertFalse(self.old.exists());self.assertFalse(state.parent.exists())
        new_state=release.installation_state_path(self.new)
        self.assertEqual(read_json(new_state)['skill_root'],str(self.new))
        self.assertEqual(release.installation_status(self.new)['status'],'active')
        self.assertTrue(release.verify_tree(self.new,read_json(self.source/'release-manifest.json')))
        self.assertTrue(list(new_state.parent.glob('previous-state-*.json')))
        self.assertEqual(self.hashes(self.profile),self.before)
    def test_normal_release_only_accepts_new_name(self):
        self.assertEqual(release.verify_release(self.pack(self.old,OLD))['status'],'blocked')
        self.assertEqual(release.verify_release(self.archive)['status'],'verified')
    def test_unmanaged_legacy_preview_is_read_only(self):
        (self.old/'release-manifest.json').unlink();before=self.hashes(self.root)
        self.assertEqual(self.preview()['status'],'legacy_import_required')
        self.assertEqual(self.hashes(self.root),before)
    def test_conflicting_target_and_changed_source_do_not_overwrite(self):
        plan=self.preview();self.new.mkdir();(self.new/'mine').write_text('retain')
        self.assertEqual(self.apply(plan)['status'],'conflict');self.assertEqual((self.new/'mine').read_text(),'retain')
        (self.new/'mine').unlink();self.new.rmdir();(self.old/'SKILL.md').write_text('user edited')
        self.assertEqual(self.apply(plan)['status'],'conflict');self.assertEqual((self.old/'SKILL.md').read_text(),'user edited')
    def test_journal_changed_after_preview_is_conflict(self):
        plan=self.preview();state=release.installation_state_path(self.old);write_json(state,{'bad':'different'})
        before=self.hashes(self.old)
        self.assertEqual(self.apply(plan)['status'],'conflict');self.assertEqual(self.hashes(self.old),before)
    def test_no_consent_and_redirected_target_are_blocked(self):
        plan=self.preview()
        self.assertEqual(release.apply_name_migration(plan,self.archive,'')['status'],'blocked')
        self.new.symlink_to(self.source,target_is_directory=True)
        self.assertEqual(release.apply_name_migration(plan,self.archive,'consent')['status'],'blocked')
        self.assertTrue(self.old.exists());self.assertEqual(self.hashes(self.profile),self.before)
    def test_interrupted_rename_restores_old_root(self):
        before=self.hashes(self.old);plan=self.preview();original=release.move_core
        def crash(source,dest):
            original(source,dest)
            if source==self.old:raise KeyboardInterrupt('crash after old core move')
        with patch('runtime.releases.move_core',side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):self.apply(plan)
        state=release.installation_state_path(self.old)
        self.assertEqual(release.recover_release(self.old,state,'恢复中断迁移')['status'],'rolled_back')
        self.assertEqual(self.hashes(self.old),before);self.assertFalse(self.new.exists())
        self.assertEqual(release.recover_release(self.old,state,'再次核对')['status'],'rolled_back')
        self.assertEqual(self.hashes(self.profile),self.before)
    def test_crash_after_journal_move_recovers_from_new_address(self):
        plan=self.preview();before=self.hashes(self.old)
        original=release.move_installation_records
        def crash(source,dest):
            original(source,dest);raise KeyboardInterrupt('crash after journal move')
        with patch('runtime.releases.move_installation_records',side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):self.apply(plan)
        self.assertEqual(release.recover_release(self.new,release.installation_state_path(self.new),'恢复迁移')['status'],'rolled_back')
        self.assertEqual(self.hashes(self.old),before);self.assertFalse(self.new.exists())
        self.assertFalse(release.installation_state_path(self.new).parent.exists())
    def test_final_health_failure_restores_old_identity_and_path(self):
        before=self.hashes(self.old)
        with patch('runtime.releases.health_check',side_effect=lambda p,m:p!=self.new):result=self.apply()
        self.assertEqual(result['status'],'rolled_back');self.assertEqual(self.hashes(self.old),before)
        self.assertFalse(self.new.exists());self.assertEqual(self.hashes(self.profile),self.before)
    def test_rollback_returns_old_identity_and_repeated_recovery_is_safe(self):
        before=self.hashes(self.old);self.assertEqual(self.apply()['status'],'migrated')
        self.assertEqual(release.rollback_release(self.new,release.installation_state_path(self.new),'回退改名')['status'],'rolled_back')
        self.assertEqual(self.hashes(self.old),before);self.assertFalse(self.new.exists())
        state=read_json(release.installation_state_path(self.old))
        self.assertEqual(state['active_manifest']['name'],OLD)
        # Old core can parse all three standard manifest fields after rollback.
        self.assertTrue(all(state[k]['name']==OLD for k in ('from_manifest','to_manifest','active_manifest')))
        self.assertEqual(release.recover_release(self.old,release.installation_state_path(self.old),'重复恢复')['status'],'rolled_back')
    def test_backup_redirection_is_blocked_before_rollback(self):
        self.apply();state=release.installation_state_path(self.new);value=read_json(state)
        backup=state.parent/value['backup_name'];other=self.root/'elsewhere';backup.rename(other);backup.symlink_to(other,target_is_directory=True)
        before=self.hashes(self.new)
        self.assertEqual(release.rollback_release(self.new,state,'rollback')['status'],'blocked')
        self.assertEqual(self.hashes(self.new),before);self.assertTrue(self.new.exists())

    def test_partial_rollback_can_recover_from_retained_journal(self):
        before=self.hashes(self.old);self.apply();original=release.move_core
        def denied(source,dest):
            if source.name.startswith('old-core-'):raise PermissionError('synthetic backup move blocked')
            return original(source,dest)
        state=release.installation_state_path(self.new)
        with patch('runtime.releases.move_core',side_effect=denied):
            self.assertEqual(release.rollback_release(self.new,state,'回退')['status'],'recovery_required')
        self.assertFalse(self.new.exists())
        self.assertEqual(release.recover_release(self.new,state,'恢复')['status'],'rolled_back')
        self.assertEqual(self.hashes(self.old),before);self.assertEqual(self.hashes(self.profile),self.before)
    def test_migration_audit_survives_later_public_update(self):
        self.assertEqual(self.apply()['status'],'migrated')
        control=release.installation_state_path(self.new).parent
        audit=list(control.glob('name-migration-*.json'))
        self.assertEqual(len(audit),1,'migration audit must survive a later ordinary update')
        audit_before=self.hashes(control)
        next_core=self.root/'next-core';self.make_core(next_core,NEW,'4.0.0-beta.3')
        next_zip=self.pack(next_core,NEW)
        self.assertEqual(release.apply_release(next_zip,self.new,self.profile,'更新合成下一版')['status'],'updated')
        self.assertEqual(file_digest(audit[0]),audit_before[audit[0].name])
        self.assertEqual(self.hashes(self.profile),self.before)
    def interrupt_before_migration_audit(self):
        original=release.write_json
        def interrupted(path,value):
            if Path(path).name.startswith('name-migration-'):
                raise KeyboardInterrupt('synthetic interruption after active journal commit')
            return original(path,value)
        with patch('runtime.releases.write_json',side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):self.apply()
        state=release.installation_state_path(self.new)
        self.assertEqual(read_json(state)['phase'],'active')
        self.assertFalse(list(state.parent.glob('name-migration-*.json')))
        return state,read_json(state)
    def test_active_recovery_repairs_interrupted_migration_audit(self):
        state,value=self.interrupt_before_migration_audit()
        self.assertEqual(release.recover_release(self.new,state,'恢复迁移审计')['status'],'active')
        audits=list(state.parent.glob('name-migration-*.json'))
        self.assertEqual(len(audits),1)
        self.assertEqual(read_json(audits[0]),value)
        self.assertEqual(self.hashes(self.profile),self.before)
    def test_up_to_date_repairs_interrupted_migration_audit(self):
        state,value=self.interrupt_before_migration_audit()
        self.assertEqual(release.apply_release(self.archive,self.new,self.profile,'检查指定同版包')['status'],'up_to_date')
        audits=list(state.parent.glob('name-migration-*.json'))
        self.assertEqual(len(audits),1)
        self.assertEqual(read_json(audits[0]),value)
        self.assertEqual(self.hashes(self.profile),self.before)
    def test_next_update_preserves_interrupted_migration_evidence(self):
        state,value=self.interrupt_before_migration_audit()
        next_core=self.root/'next-core';self.make_core(next_core,NEW,'4.0.0-beta.3')
        self.assertEqual(release.apply_release(self.pack(next_core,NEW),self.new,self.profile,'更新合成下一版')['status'],'updated')
        audits=list(state.parent.glob('name-migration-*.json'))
        self.assertEqual(len(audits),1)
        self.assertEqual(read_json(audits[0]),value)
        self.assertEqual(read_json(state)['active_manifest']['version'],'4.0.0-beta.3')
        self.assertEqual(self.hashes(self.profile),self.before)
    def test_inconsistent_existing_migration_audit_blocks_recovery_and_update(self):
        self.assertEqual(self.apply()['status'],'migrated')
        state=release.installation_state_path(self.new)
        audit=next(state.parent.glob('name-migration-*.json'))
        value=read_json(audit);value['authorization_evidence']='different evidence'
        write_json(audit,value)
        before=self.hashes(self.new);journal_hash=file_digest(state);audit_hash=file_digest(audit)
        next_core=self.root/'next-core';self.make_core(next_core,NEW,'4.0.0-beta.3')
        self.assertEqual(release.rollback_release(self.new,state,'检查冲突后的回退')['status'],'blocked')
        self.assertEqual(release.recover_release(self.new,state,'检查审计冲突')['status'],'blocked')
        self.assertEqual(release.apply_release(self.pack(next_core,NEW),self.new,self.profile,'更新合成下一版')['status'],'blocked')
        self.assertEqual(self.hashes(self.new),before)
        self.assertEqual(file_digest(state),journal_hash);self.assertEqual(file_digest(audit),audit_hash)
        self.assertEqual(self.hashes(self.profile),self.before)
    def test_real_cli_preview_apply_and_profile_binding(self):
        script=Path(__file__).resolve().parents[1]/'scripts/manage.py';output=self.root/'name-plan.json'
        command=[sys.executable,'-B',str(script),'--data-dir',str(self.profile.parents[1]),'--profile',self.profile.name,'release']
        run=subprocess.run(command+['migrate-plan','--old-root',str(self.old),'--new-root',str(self.new),'--output',str(output)],capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        self.assertEqual(json.loads(run.stdout)['status'],'preview')
        run=subprocess.run(command+['migrate-apply','--plan',str(output),'--archive',str(self.archive),'--consent','合成CLI迁移授权'],capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        self.assertEqual(json.loads(run.stdout)['status'],'migrated')
        self.assertEqual(self.hashes(self.profile),self.before)

if __name__=='__main__':unittest.main()
