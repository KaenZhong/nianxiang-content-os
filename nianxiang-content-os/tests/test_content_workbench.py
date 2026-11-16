import importlib.util,json,tempfile,unittest
from pathlib import Path
import sys
SCRIPTS=Path(__file__).parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location('content_workbench',SCRIPTS/'content_workbench.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class MultiWorkbenchTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.file=self.root/'content.json'
  self.work={'id':'work-a','body':'正文</script>','titles':[{'text':'候选','type':'判断型'}],'selectedTitle':-1,'images':[]}
 def build(self,works):
  self.file.write_text(json.dumps({'date':'fixture','works':works},ensure_ascii=False));return m.build(self.file)
 def test_two_works_safe_and_source_unchanged(self):
  other={**self.work,'id':'work-b','body':'第二篇'}
  self.file.write_text(json.dumps({'works':[self.work,other]},ensure_ascii=False));before=self.file.read_bytes();result=m.build(self.file)
  self.assertEqual(self.file.read_bytes(),before);self.assertEqual(result['works'],2)
  page=(self.root/'index.html').read_text();self.assertNotIn('正文</script>',page);self.assertIn('正文\\u003c/script>',page)
  self.assertNotIn('id="add-draft"',page);self.assertNotIn('id="mobile-copy"',page)
 def test_images_embedded_and_paths_kept(self):
  (self.root/'images').mkdir();(self.root/'images/a.png').write_bytes(b'fixture')
  self.work['images']=[{'id':'a','label':'配图','path':'images/a.png'}];self.build([self.work]);page=(self.root/'index.html').read_text()
  self.assertIn('data:image/png;base64,',page);self.assertEqual(json.loads(self.file.read_text())['works'][0]['images'][0]['path'],'images/a.png')
 def test_duplicate_and_escape_rejected(self):
  with self.assertRaises(ValueError):self.build([self.work,self.work])
  self.work['images']=[{'id':'a','label':'图','path':'../secret.png'}]
  with self.assertRaises(ValueError):self.build([self.work])
 def test_empty_and_bad_selected_title(self):
  self.assertEqual(self.build([])['works'],0)
  self.work['selectedTitle']=5
  with self.assertRaises(ValueError):self.build([self.work])

 def test_single_work_and_legacy_entry_deliver_unified_ui(self):
  import graphic_workbench
  self.file.write_text(json.dumps(self.work,ensure_ascii=False))
  before=self.file.read_bytes();result=m.build(self.file)
  self.assertEqual(result['works'],1);self.assertEqual(before,self.file.read_bytes())
  result=graphic_workbench.build(self.file)
  self.assertEqual(result['works'],1)
  page=(self.root/'index.html').read_text()
  self.assertIn('id="draft-sidebar"',page)
  self.assertNotIn('id="copy-post"',page)
  self.assertNotIn("check.type='checkbox'",page)
  self.assertIn('交回全部稿件',page)
