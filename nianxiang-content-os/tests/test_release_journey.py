"""Synthetic complete core + update journey with the actual public Python core."""
import copy
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
import zipfile
import test_core_journey as core_cases
from runtime.models import file_digest,read_json,write_json
from runtime.knowledge import load_context
from runtime.rules import select_confirmed_rules
from runtime.releases import build_manifest,verify_release,apply_release,rollback_release,installation_state_path,verify_tree

class ReleaseJourney(unittest.TestCase):
    setUp=core_cases.CoreJourney.setUp
    plan=core_cases.CoreJourney.plan
    run_plan=core_cases.CoreJourney.run_plan
    def test_existing_knowledge_work_rules_survive_actual_core_update_and_rollback(self):
        core_cases.CoreJourney.test_core_journey(self)
        rule={'id':'r-synthetic','instruction':'先澄清具体耗时环节，再提出工具方案','scope':'channel','channels':['moments'],'surfaces':['body'],'materials':['general'],'status':'active','basis':'user_confirmed','source':'explicit synthetic user confirmation'}
        write_json(self.profile/'local-rules.json',{'schema_version':1,'rules':[rule]})
        # Keep a genuinely uncertain operation for the later session; do not replay it.
        write_json(self.profile/'pending/synthetic-lost-readback.json',{'status':'uncertain','attempted':True,'content':'synthetic fixture'})
        before={str(p.relative_to(self.profile)):file_digest(p) for p in self.profile.rglob('*') if p.is_file()}
        root=self.profile.parents[1];old=root/'installed';new=root/'new-core';source=Path(__file__).resolve().parents[1]
        shutil.copytree(source,old);shutil.copytree(source,new)
        write_json(old/'release-manifest.json',build_manifest(old,'4.0.0-beta.0'))
        write_json(new/'release-manifest.json',build_manifest(new,'4.0.0-beta.1'))
        old_manifest=read_json(old/'release-manifest.json');archive=root/'update.zip'
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for p in new.rglob('*'):
                if p.is_file():z.write(p,'nianxiang-content-os/'+p.relative_to(new).as_posix())
        self.assertEqual(verify_release(archive)['status'],'verified')
        self.assertEqual(apply_release(archive,old,self.profile,'合成用户授权本地核心更新')['status'],'updated')
        self.assertEqual({str(p.relative_to(self.profile)):file_digest(p) for p in self.profile.rglob('*') if p.is_file()},before)
        rules=select_confirmed_rules(read_json(self.profile/'local-rules.json'),{'channel':'moments','surface':'body','material':'general'})
        self.assertEqual(rules[0]['id'],rule['id'])
        self.assertEqual(rollback_release(old,installation_state_path(old),'合成用户授权回退')['status'],'rolled_back')
        self.assertTrue(verify_tree(old,old_manifest))
        self.assertEqual({str(p.relative_to(self.profile)):file_digest(p) for p in self.profile.rglob('*') if p.is_file()},before)
        self.assertEqual(read_json(self.profile/'pending/synthetic-lost-readback.json')['status'],'uncertain')
        # New host restores the same knowledge and work; source edits are still noticed.
        new_host=copy.deepcopy(self.adapter);context=load_context(self.profile,['content.strategy'],new_host)
        self.assertIn('需求访谈',context['knowledge']['content.strategy']['content'])
        self.assertEqual(new_host.records['nxw:synthetic:journey']['content']['沉淀状态'],'待沉淀')
        doc=new_host.config['knowledge_map']['content.strategy']['obj_token']
        new_host.bodies[doc].update(revision=99,content='合成用户新的经营策略')
        self.assertEqual(load_context(self.profile,['content.strategy'],new_host)['knowledge']['content.strategy']['content'],'合成用户新的经营策略')
    def test_real_cli_verify_check_update_and_manifest(self):
        root=self.profile.parents[1];source=Path(__file__).resolve().parents[1];copy_root=root/'core';shutil.copytree(source,copy_root)
        command=[sys.executable,'-B',str(source/'scripts/manage.py')]
        def run(*args):
            proc=subprocess.run(command+list(args),capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
            import json
            return json.loads(proc.stdout)
        self.assertEqual(run('release','manifest','--source-dir',str(copy_root),'--version','4.0.0-beta.1')['status'],'manifest_created')
        self.assertEqual(run('release','check-update','--manifest',str(copy_root/'release-manifest.json'))['status'],'not_configured')
        self.assertEqual(run('release','status','--skill-root',str(copy_root))['status'],'unmanaged')
        archive=root/'cli-package.zip'
        with zipfile.ZipFile(archive,'w') as z:
            for p in copy_root.rglob('*'):
                if p.is_file():z.write(p,'nianxiang-content-os/'+p.relative_to(copy_root).as_posix())
        self.assertEqual(run('release','verify','--archive',str(archive))['status'],'verified')

if __name__=='__main__':unittest.main()
