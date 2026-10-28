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

    def test_single_file_survives_isolation_and_preserves_image_paths(self):
        import base64
        import re
        from html.parser import HTMLParser
        import subprocess
        (self.root / 'images').mkdir()
        picture = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV1cAAAAASUVORK5CYII=')
        (self.root / 'images/cover.png').write_bytes(picture)
        self.data['images'] = [dict(id='cover', label='封面', path='images/cover.png')]
        self.path.write_text(json.dumps(self.data))
        first = module.build(self.path)
        isolated = self.root / 'isolated'
        isolated.mkdir()
        shutil.copy2(self.root / 'index.html', isolated / 'index.html')
        page = (isolated / 'index.html').read_text()
        class Dependencies(HTMLParser):
            def __init__(self):
                super().__init__(); self.external = []; self.textarea_seen = False; self.early_scripts = []
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == 'textarea': self.textarea_seen = True
                if tag == 'script' and not self.textarea_seen: self.early_scripts.append(tag)
                if tag in ('script', 'img', 'link'):
                    ref = attrs.get('src') or attrs.get('href')
                    if ref and not ref.startswith('data:'): self.external.append(ref)
        parsed = Dependencies(); parsed.feed(page)
        self.assertEqual(parsed.external, [])
        self.assertEqual(parsed.early_scripts, [])
        scripts = re.findall(r'<script>(.*?)</script>', page, re.S)
        self.assertEqual(len(scripts), 2)
        resources = json.loads(re.search(r'window.WORKBENCH_IMAGES = (.*);', scripts[0]).group(1))
        self.assertEqual(base64.b64decode(resources['images/cover.png'].split(',', 1)[1]), picture)
        # Execute the actual inline scripts after the fixture DOM exists, without sibling files.
        if shutil.which('node'):
            harness = r"""
const vm=require('vm'),assert=require('assert'),fs=require('fs');
const scripts=JSON.parse(fs.readFileSync(0,'utf8'));const els=new Map();let copied='';
class E { constructor(){this.children=[];this.attrs={};this.style={};this.listeners={};this.classList={add(){},remove(){},toggle(){},contains(){return false}};}
append(...x){this.children.push(...x)}replaceChildren(){this.children=[]}setAttribute(k,v){this.attrs[k]=v}getAttribute(k){return this.attrs[k]}addEventListener(k,f){(this.listeners[k]??=[]).push(f)} }
const get=id=>{if(!els.has(id))els.set(id,new E());return els.get(id)};
const c={window:{addEventListener(){},scrollY:0},structuredClone,URL,location:{pathname:'/shared.html'},document:{getElementById:get,createElement:()=>new E(),querySelector:()=>null,addEventListener(){}},localStorage:{getItem:()=>null,setItem(){}},navigator:{clipboard:{writeText:async s=>{copied=s}}},setTimeout:()=>0,clearTimeout(){}};
vm.createContext(c);for(const s of scripts)vm.runInContext(s,c);
assert.equal(get('body').value,'正文</script>');assert.equal(get('titles').children.length,1);
assert(get('gallery').children[0].children[1].children[0].src.startsWith('data:image/png;base64,'));
assert(get('gallery').children[0].children[2].children[0].href.startsWith('data:image/png;base64,'));
for(const fn of get('handoff').listeners.click)fn();assert(copied.includes('images/cover.png'));assert(!copied.includes('data:image/'));
const selection=vm.runInContext('selection()',c);assert.equal(selection.images[0].path,'images/cover.png');
"""
            subprocess.run(['node', '-e', harness], input=json.dumps(scripts), text=True, check=True, capture_output=True)
        self.assertEqual(first['revision'], module.build(self.path, self_contained=False)['revision'])
        self.assertIn('src="data.js"', (self.root / 'index.html').read_text())
        self.assertEqual(first['revision'], module.build(self.path)['revision'])

    def test_empty_standalone_runs_after_dom(self):
        result = module.build(self.path)
        page = (self.root / 'index.html').read_text()
        self.assertTrue(result['self_contained'])
        self.assertIn('window.WORKBENCH_IMAGES = {};', page)
        self.assertNotIn('src="app.js"', page)
        self.assertLess(page.index('id="body"'), page.index('window.WORKBENCH_DATA'))
