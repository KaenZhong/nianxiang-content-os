#!/usr/bin/env python3
"""Build a self-contained multi-work editor from existing private works; no remote writes."""
import argparse,base64,hashlib,json,mimetypes
from pathlib import Path
from graphic_workbench import CORE,atomic,revision,validate
TEMPLATE=CORE/'assets/content-workbench/index.html'
def build(content):
    content=Path(content).resolve();root=content.parent
    if root==CORE or CORE in root.parents: raise ValueError('private content must be outside the public Skill')
    data=json.loads(content.read_text(encoding='utf-8'))
    if isinstance(data,dict) and 'works' not in data and 'id' in data:
        data={'date':'single-'+data['id'],'works':[data]}
    if not isinstance(data,dict) or not isinstance(data.get('works'),list): raise ValueError('works must be a list')
    works=[];ids=set();resources={}
    for item in data['works']:
        if not isinstance(item,dict): raise ValueError('work must be an object')
        w=dict(item);w.setdefault('titles',[]);w.setdefault('images',[]);w.setdefault('selectedTitle',-1)
        validate(w,root)
        if w['id'] in ids: raise ValueError('duplicate work id')
        if not w['body'].strip(): raise ValueError('existing complete body required')
        ids.add(w['id']);w.setdefault('name',w['body'].split('\n')[0][:40]);w.setdefault('slot','已有稿件 · 待审阅');w['revision']=revision(w)
        resources[w['id']]={}
        for image in w['images']:
            actual=root/image['path'];mime=mimetypes.guess_type(actual.name)[0]
            resources[w['id']][image['path']]='data:'+mime+';base64,'+base64.b64encode(actual.read_bytes()).decode('ascii')
        works.append(w)
    batch=str(data.get('date','batch'))+'-'+hashlib.sha256(json.dumps(works,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:16]
    def safe(value): return json.dumps(value,ensure_ascii=False).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    page=TEMPLATE.read_text(encoding='utf-8').replace('__DAILY_WORKS__',safe(works)).replace('__BATCH_KEY__',safe(batch)).replace('__BATCH_IMAGES__',safe(resources))
    if (root/'index.html').is_symlink(): raise ValueError('output symlink rejected')
    atomic(root/'index.html',page)
    return {'status':'generated','page':str(root/'index.html'),'works':len(works),'batch':batch,'self_contained':True}
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--content',required=True);a=parser.parse_args()
    print(json.dumps(build(a.content),ensure_ascii=False))
if __name__=='__main__':main()
