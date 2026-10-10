import unittest
from pathlib import Path
from personal_support import Fixture
from runtime.tasks import create_task,update_task,resume_task
from runtime.models import file_digest,read_json,NianxiangError

class Tasks(Fixture,unittest.TestCase):
    def request(self):
        source=self.adapter.docs['content.strategy']
        return {'kind':'creation','mode':'execution','status':'active','goal':'根据已确认素材写朋友圈','context_refs':[{'knowledge_id':'content.strategy','revision':source['revision'],'obj_token':source['obj_token']}],'selected_items':['topic:synthetic'],'artifact_refs':[],'checkpoint':'切口已确认','next_step':'出稿','operation_ids':[]}
    def create(self):return create_task(self.profile,self.request(),'合成测试：创建并恢复此内容任务')
    def test_resume_is_read_only(self):
        task=self.create();out=resume_task(self.profile,task['task_id'],self.adapter)
        self.assertEqual(out['status'],'ready');self.assertEqual(out['task']['selected_items'],['topic:synthetic']);self.assertEqual(self.adapter.writes,0)
    def test_update_rejects_stale_version(self):
        t=self.create();self.assertEqual(update_task(self.profile,t['task_id'],{'checkpoint':'首稿已形成'},1,'记录首稿进度')['status'],'updated')
        path=self.profile/'tasks'/f"{t['task_id']}.json";before=file_digest(path)
        self.assertEqual(update_task(self.profile,t['task_id'],{'checkpoint':'old'},1,'旧更新')['status'],'conflict');self.assertEqual(file_digest(path),before)
    def test_terminal_and_identity_fields_cannot_change(self):
        t=self.create();self.assertEqual(update_task(self.profile,t['task_id'],{'account_id':'other'},1,'update')['status'],'blocked')
        self.assertEqual(update_task(self.profile,t['task_id'],{'status':'completed'},1,'任务完成')['status'],'updated')
        self.assertEqual(update_task(self.profile,t['task_id'],{'status':'active'},2,'重新改')['status'],'blocked')
    def test_resume_missing_artifact_requires_input(self):
        path=Path(self.tmp.name).resolve()/'material.txt';path.write_text('synthetic material')
        req=self.request();req['artifact_refs']=[{'type':'local','path':str(path),'sha256':file_digest(path),'authorized_root':str(Path(self.tmp.name).resolve())}]
        t=create_task(self.profile,req,'授权引用这个合成素材');path.unlink()
        self.assertEqual(resume_task(self.profile,t['task_id'],self.adapter)['status'],'needs_input')
    def test_changed_source_and_account_are_distinct(self):
        t=self.create();self.adapter.docs['content.strategy']['revision']=2
        self.assertEqual(resume_task(self.profile,t['task_id'],self.adapter)['status'],'needs_revalidation')
        self.adapter.account='other';self.assertEqual(resume_task(self.profile,t['task_id'],self.adapter)['status'],'blocked')
    def test_no_authorization_no_file_and_invalid_path(self):
        with self.assertRaisesRegex(NianxiangError,'authorization_required'):create_task(self.profile,self.request(),'')
        self.assertFalse((self.profile/'tasks').exists())
        t=self.create();self.assertEqual(resume_task(self.profile,'../state',self.adapter)['status'],'blocked')
    def test_redirected_task_directory_blocked(self):
        other=Path(self.tmp.name)/'other';other.mkdir();(self.profile/'tasks').symlink_to(other,target_is_directory=True)
        with self.assertRaisesRegex(NianxiangError,'invalid_path'):self.create()
        self.assertEqual(list(other.iterdir()),[])
    def test_uncertain_operation_is_not_published_or_replayed(self):
        from runtime.models import write_json
        req=self.request();req['operation_ids']=['op-test'];t=create_task(self.profile,req,'save checkpoint')
        write_json(self.profile/'pending/op-test.json',{'profile_id':t['profile_id'],'account_id':'account-a','space_id':'space-a','status':'uncertain'})
        out=resume_task(self.profile,t['task_id'],self.adapter)
        self.assertEqual(out['status'],'needs_revalidation');self.assertEqual(out['operations']['op-test'],'uncertain');self.assertEqual(self.adapter.writes,0)
    def test_revision_boolean_is_not_a_source_version(self):
        req=self.request();req['context_refs'][0]['revision']=True
        with self.assertRaisesRegex(NianxiangError,'invalid_reference'):create_task(self.profile,req,'记录此任务')

if __name__=='__main__':unittest.main()
