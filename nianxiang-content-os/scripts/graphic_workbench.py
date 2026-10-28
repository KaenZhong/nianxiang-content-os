#!/usr/bin/env python3
"""Build a private graphic workbench from one content.json; no network writes."""
import argparse
import base64
import mimetypes
import hashlib
import json
import os
from pathlib import Path
import tempfile

CORE = Path(__file__).resolve().parents[1]
TEMPLATE = CORE / 'assets' / 'graphic-workbench'


def revision(data):
    payload = {k: v for k, v in data.items() if k != 'revision'}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def validate(data, root):
    if not isinstance(data.get('id'), str) or not data['id'].strip():
        raise ValueError('id must identify this work')
    if not isinstance(data.get('body'), str):
        raise ValueError('body must be text')
    titles, images = data.get('titles'), data.get('images')
    if not isinstance(titles, list) or not all(isinstance(t, dict) and isinstance(t.get('text'), str) and isinstance(t.get('type'), str) for t in titles):
        raise ValueError('titles require text and type')
    selected = data.get('selectedTitle')
    if type(selected) is not int or (titles and not 0 <= selected < len(titles)) or (not titles and selected != -1):
        raise ValueError('selectedTitle must be valid, or -1 when titles are empty')
    if not isinstance(images, list):
        raise ValueError('images must be a list')
    ids = set()
    for item in images:
        if not isinstance(item.get('id'), str) or item['id'] in ids or not isinstance(item.get('label'), str):
            raise ValueError('images require unique id and label')
        ids.add(item['id'])
        path = Path(item['path'])
        if path.is_absolute() or '..' in path.parts or path.parts[:1] != ('images',):
            raise ValueError('images must use relative paths inside images/')
        actual = (root / path).resolve()
        if root not in actual.parents or not actual.is_file() or actual.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp', '.gif'}:
            raise ValueError('image missing, outside task folder, or unsupported')
    if data.get('creation') is not None and not isinstance(data['creation'], dict):
        raise ValueError('creation must be an object')
    return data


def atomic(path, text):
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.workbench-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def build(content, selection=None, self_contained=True):
    content = Path(content).resolve()
    root = content.parent
    if root == CORE or CORE in root.parents:
        raise ValueError('private content must be outside the public Skill')
    data = validate(json.loads(content.read_text(encoding='utf-8')), root)
    if selection:
        chosen = json.loads(Path(selection).read_text(encoding='utf-8'))
        if chosen.get('schema_version') != 'nianxiang.graphic-workbench.selection.v1' or chosen.get('work_id') != data['id'] or chosen.get('base_revision') != revision(data):
            raise ValueError('work or revision mismatch: merge in conversation before importing')
        known = {i['id']: i for i in data['images']}
        order = [i['id'] for i in chosen['images']]
        if len(order) != len(known) or set(order) != set(known):
            raise ValueError('image set mismatch')
        titles = chosen['title_candidates']
        text = chosen['selected_title']
        selected = next((i for i,t in enumerate(titles) if t['text'] == text), -1)
        data.update(body=chosen['body'], titles=titles, selectedTitle=selected, images=[known[i] for i in order])
        validate(data, root)
    data['revision'] = revision(data)
    # Asset names are reserved outputs; task content and images stay independent.
    files = {name: (TEMPLATE / name).read_text(encoding='utf-8') for name in ('style.css', 'app.js', 'index.html')}
    files['data.js'] = 'window.WORKBENCH_DATA = ' + json.dumps(data, ensure_ascii=False).replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029') + ';\n'
    if self_contained:
        resources = {}
        for image in data['images']:
            path = root / image['path']
            mime = mimetypes.guess_type(path.name)[0]
            resources[image['path']] = 'data:' + mime + ';base64,' + base64.b64encode(path.read_bytes()).decode('ascii')
        page = files['index.html']
        page = page.replace('<link rel="stylesheet" href="style.css">', '<style>' + files['style.css'].replace('</style', '<\\/style') + '</style>')
        page = page.replace('<script defer src="data.js"></script>', '').replace('<script defer src="app.js"></script>', '')
        resource_script = 'window.WORKBENCH_IMAGES = ' + json.dumps(resources) + ';'
        # Inline scripts execute after every page element exists; defer does not defer inline code.
        scripts = '<script>' + files['data.js'] + resource_script + '</script><script>' + files['app.js'].replace('</script', '<\\/script') + '</script>'
        files['index.html'] = page.replace('</body>', scripts + '</body>')
    for name in ('style.css', 'app.js', 'data.js', 'index.html'):
        target = root / name
        if target.is_symlink():
            raise ValueError('output symlink rejected')
    atomic(content, json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    for name in ('style.css', 'app.js', 'data.js', 'index.html'):
        atomic(root / name, files[name])
    return {'status':'generated', 'id': data['id'], 'revision':data['revision'], 'page':str(root / 'index.html'), 'self_contained':self_contained}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--content', required=True, help='private task content.json; outputs go beside it')
    parser.add_argument('--import-selection', help='user-returned selection JSON with matching work and base revision')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--self-contained', dest='self_contained', action='store_true', default=True, help='inline all assets into index.html (default for delivery/sharing)')
    mode.add_argument('--multi-file', dest='self_contained', action='store_false', help='local-only HTML referencing sibling assets')
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.content, args.import_selection, args.self_contained), ensure_ascii=False))
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
