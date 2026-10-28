import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import shutil

spec = importlib.util.spec_from_file_location('graphic_workbench', Path(__file__).parents[1] / 'scripts/graphic_workbench.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class WorkbenchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'content.json'
        self.data = dict(id='test-work', body='正文</script>', titles=[dict(text='测试标题', type='判断型')], selectedTitle=0, images=[])
        self.path.write_text(json.dumps(self.data))

    def test_empty_and_stable_revision(self):
        first = module.build(self.path)
        self.assertEqual(first['revision'], module.build(self.path)['revision'])
        self.assertIn('image-placeholder', (self.root / 'app.js').read_text())
        self.assertNotIn('</script>', (self.root / 'data.js').read_text())

    def selection(self):
        module.build(self.path)
        return dict(schema_version='nianxiang.graphic-workbench.selection.v1', work_id='test-work', base_revision=module.revision(self.data), body='用户改稿', title_candidates=self.data['titles'], selected_title='测试标题', images=[])

    def test_import_and_stale_rejection(self):
        chosen = self.selection()
        selection = self.root / 'selection.json'
        selection.write_text(json.dumps(chosen))
        module.build(self.path, selection)
        self.assertEqual(json.loads(self.path.read_text())['body'], '用户改稿')
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            module.build(self.path, selection)
        self.assertEqual(before, self.path.read_bytes())

    def test_cross_work_and_path_rejected(self):
        chosen = self.selection(); chosen['work_id']='other'
        selection = self.root / 'selection.json'; selection.write_text(json.dumps(chosen))
        with self.assertRaises(ValueError): module.build(self.path, selection)
        self.data['images']=[dict(id='cover',label='封面',path='../private.png')]
        self.path.write_text(json.dumps(self.data))
        with self.assertRaises(ValueError): module.build(self.path)

    def test_multiple_images_order(self):
        (self.root/'images').mkdir()
        for name in ['a','b']:(self.root/'images'/f'{name}.png').write_bytes(b'fixture')
        self.data['images']=[dict(id=n,label=n,path=f'images/{n}.png') for n in ['a','b']]
        self.path.write_text(json.dumps(self.data)); chosen=self.selection();chosen['images']=list(reversed(self.data['images']))
        selection=self.root/'selection.json';selection.write_text(json.dumps(chosen));module.build(self.path,selection)
        self.assertEqual(json.loads(self.path.read_text())['images'][0]['id'],'b')

    def test_template_update_keeps_content_revision_and_handoff_valid(self):
        chosen = self.selection()
        before = json.loads(self.path.read_text())
        template = self.root / 'test-template'
        shutil.copytree(module.TEMPLATE, template)
        css = template / 'style.css'
        css.write_text(css.read_text() + '\n/* template update fixture */\n')
        selection = self.root / 'selection.json'
        selection.write_text(json.dumps(chosen))
        with patch.object(module, 'TEMPLATE', template):
            result = module.build(self.path)
            self.assertEqual(result['revision'], before['revision'])
            self.assertEqual(json.loads(self.path.read_text()), before)
            self.assertIn('template update fixture', (self.root / 'style.css').read_text())
            module.build(self.path, selection)
        self.assertEqual(json.loads(self.path.read_text())['body'], '用户改稿')
