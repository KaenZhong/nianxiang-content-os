"""Synthetic OS journey: actual Python runtime, external profile, no live user data."""
import copy,json,shutil,unittest,zipfile
from pathlib import Path
from personal_support import Fixture,rule,collaboration
from runtime.personal import read_personal_context
from runtime.knowledge import load_context,save_change,authorize_request
from runtime.models import read_json,write_json,file_digest
from runtime.tasks import create_task,update_task,resume_task
from runtime.releases import build_manifest,apply_release,rollback_release,installation_state_path

class OSJourney(Fixture,unittest.TestCase):
    def seed(self):
        self.adapter.docs['ip.profile']['content']='个人事实：这是合成作者，不代表真实用户。\nNIANXIANG_COLLABORATION_V1='+json.dumps(collaboration(),ensure_ascii=False,separators=(',',':'))
        self.adapter.docs['methodology.current']['content']='NIANXIANG_PERSONAL_RULES_V1='+json.dumps({'schema_version':1,'rules':[rule()]},ensure_ascii=False,separators=(',',':'))
        self.adapter.docs['content.strategy']['content']='已确认：向小团队介绍需求访谈。没有报名入口。'
        self.adapter.docs['audience.needs']['content']='合成访谈：整理原始记录费时；普遍需求未知。'
        self.adapter.docs['expression.baseline']['content']='仅当前样本：用具体事实。'
    def journey(self):
        self.seed();ctx=read_personal_context(self.profile,self.adapter)
        self.assertEqual(ctx['status'],'ready')
        context=load_context(self.profile,['ip.profile','content.strategy','audience.needs','expression.baseline'],self.adapter)
        refs=[{'knowledge_id':k,'obj_token':v['obj_token'],'revision':v['revision']} for k,v in context['knowledge'].items()]
        target={'knowledge_id':'operations.base','obj_type':'bitable','table_key':'moments_works','key_field':'作品键','object_key':'nxw:synthetic:os'}
        draft='对方想自动化写报告。追问后才知道，最费时的是整理原始记录。先问清哪一步耗时，再决定做什么工具。'
        req={'operation_id':'os-save-work','target':target,'action':'create','base_revision':None,'content':{'作品键':target['object_key'],'作品标题':'先问清哪一步','第一版':draft,'发表状态':'待发布','沉淀状态':'待沉淀'}}
        req['authorization']=authorize_request(self.profile,req,'合成测试：保存首稿，不发布')
        self.assertEqual(save_change(self.profile,req,self.adapter)['status'],'saved')
        task=create_task(self.profile,{'kind':'creation','mode':'execution','status':'active','goal':'合成样本朋友圈创作','context_refs':refs,'selected_items':['选题：先问清哪一步'],'artifact_refs':[{'type':'remote','target':target,'revision':1}],'checkpoint':'作品已保存待发布','next_step':'用户实际发布后反馈','operation_ids':['os-save-work']},'合成测试：记录本任务恢复点')
        return task,target
    def test_resume_does_not_duplicate_saved_work(self):
        task,target=self.journey();before=copy.deepcopy(self.adapter.records);new_session=copy.deepcopy(self.adapter)
        out=resume_task(self.profile,task['task_id'],new_session)
        self.assertEqual(out['status'],'ready');self.assertEqual(new_session.records,before);self.assertEqual(new_session.writes,self.adapter.writes)
        self.assertEqual(out['operations']['os-save-work'],'saved');self.assertEqual(new_session.records[target['object_key']]['content']['发表状态'],'待发布')
    def test_feedback_candidate_does_not_write_without_consent(self):
        task,target=self.journey();before=self.adapter.docs['methodology.current']['revision'];writes=self.adapter.writes
        candidate={'operation_id':'os-feedback-candidate','target':{'knowledge_id':'methodology.current','obj_type':'docx'},'action':'append','base_revision':before,'content':{'text':'候选：以后更早给出具体现场，效果仍待观察。'}}
        self.assertEqual(save_change(self.profile,candidate,self.adapter)['status'],'blocked');self.assertEqual(self.adapter.writes,writes);self.assertEqual(self.adapter.docs['methodology.current']['revision'],before)
        # Actual publishing/feedback fields are user supplied; engagement alone never supplies sales fields.
        record=self.adapter.records[target['object_key']];fields=copy.deepcopy(record['content']);fields.update(发表状态='已发布',用户反馈='合成用户回报：3条评论；咨询、成交未知')
        req={'operation_id':'os-feedback-record','target':target,'action':'update','base_revision':record['revision'],'content':fields};req['authorization']=authorize_request(self.profile,req,'合成测试：回填这次发布与评论，不推断成交')
        self.assertEqual(save_change(self.profile,req,self.adapter)['status'],'saved');self.assertNotIn('成交',self.adapter.records[target['object_key']]['content'])
        self.assertEqual(resume_task(self.profile,task['task_id'],self.adapter)['status'],'needs_revalidation')
    def test_public_upgrade_preserves_task_and_personal_state(self):
        task,target=self.journey();before={str(p.relative_to(self.profile)):file_digest(p) for p in self.profile.rglob('*') if p.is_file()}
        root=Path(self.tmp.name).resolve();source=Path(__file__).resolve().parents[1];old=root/'old-core';new=root/'new-core';shutil.copytree(source,old);shutil.copytree(source,new)
        write_json(old/'release-manifest.json',build_manifest(old,'4.0.0-beta.1'));write_json(new/'release-manifest.json',build_manifest(new,'4.0.0-beta.2'));archive=root/'update.zip'
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for p in new.rglob('*'):
                if p.is_file():z.write(p,'nianxiang-content-os/'+p.relative_to(new).as_posix())
        self.assertEqual(apply_release(archive,old,self.profile,'合成测试：更新公开核心')['status'],'updated')
        self.assertEqual({str(p.relative_to(self.profile)):file_digest(p) for p in self.profile.rglob('*') if p.is_file()},before)
        self.assertEqual(rollback_release(old,installation_state_path(old),'合成测试：回退公开核心')['status'],'rolled_back')
        self.assertEqual({str(p.relative_to(self.profile)):file_digest(p) for p in self.profile.rglob('*') if p.is_file()},before)
        self.assertEqual(resume_task(self.profile,task['task_id'],self.adapter)['status'],'ready')
        self.assertEqual(read_personal_context(self.profile,self.adapter)['collaboration']['preferred_name'],'测试作者')
    def test_foreign_remote_artifact_is_blocked(self):
        task,target=self.journey();self.adapter.records[target['object_key']]['account_id']='another-account'
        self.assertEqual(resume_task(self.profile,task['task_id'],self.adapter)['status'],'blocked')
if __name__=='__main__':unittest.main()
