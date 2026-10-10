"""Discover or resume compatible skeletons without replacing existing personal content."""
from __future__ import annotations
import copy
from pathlib import Path
from .models import NianxiangError,digest,read_json,write_json,now,profile_lock
from .knowledge import profile_state,verify_account
from validate_local_config import validate

def check_structure(structure):
    if structure.get('schema_version')!=1 or structure.get('knowledge_schema_version')!=4 or structure.get('data_layout_version')!=1:raise NianxiangError('incompatible_structure','unsupported skeleton schema')
    if not structure.get('account_id') or not structure.get('space_id'):raise NianxiangError('identity_required','choose actual account and target space')
    seen=set()
    for node in structure['nodes']:
        if node['id'] in seen or (node.get('parent') and node['parent'] not in seen) or not node['title'] or node['obj_type'] not in ('docx','bitable'):
            raise NianxiangError('invalid_structure','node order, IDs or types are invalid')
        seen.add(node['id'])
    mappings=set(structure['config_template']['knowledge_map'])
    if not mappings.issubset(seen) or len(mappings)!=12 or len(structure['tables'])!=4:raise NianxiangError('invalid_structure','complete 12 mappings and four tables required')

def select_node(adapter,structure,spec,parent):
    titles=[spec['title']]+spec.get('legacy_titles',[])
    if not all(isinstance(t,str) and t for t in titles):raise NianxiangError('invalid_structure','titles must be nonempty strings')
    nodes=adapter.list_nodes(parent);matches=[n for n in nodes if n.get('title') in titles]
    if len(matches)>1:raise NianxiangError('ambiguous_node','multiple exact titles; choose the correct node before creating')
    if not matches:return None
    node=matches[0];wanted_parent=(parent or {}).get('node_token','')
    if node.get('space_id')!=structure['space_id'] or node.get('parent_node_token','')!=wanted_parent or node.get('obj_type')!=spec['obj_type'] or not node.get('node_token') or not node.get('obj_token'):
        raise NianxiangError('target_mismatch','existing node has different identity, type or parent')
    return node

def select_table(adapter,base,spec):
    matches=[t for t in adapter.list_tables(base) if t.get('name')==spec['title']]
    if len(matches)>1:raise NianxiangError('ambiguous_table','duplicate table name')
    if not matches:return None
    if not matches[0].get('id'):raise NianxiangError('invalid_response','table ID missing')
    return matches[0]

def verify_fields(adapter,base,table,spec):
    fields=adapter.list_fields(base,table);names={f.get('name'):f for f in fields}
    if len(names)!=len(fields):raise NianxiangError('field_conflict','duplicate field names')
    for expected in spec['fields']:
        actual=names.get(expected['name'])
        if not actual or actual.get('type')!=expected['type']:raise NianxiangError('field_conflict','existing table field is missing or has another type; no implicit schema overwrite')
        if expected['type']=='select' and not {o['name'] for o in expected.get('options',[])}.issubset({o.get('name') for o in actual.get('options',[])}):raise NianxiangError('field_conflict','required select options are absent')
        if expected['type']=='link':
            if actual.get('bidirectional') is not True:raise NianxiangError('field_conflict','topic relationship must be bidirectional')
            target=expected['link_table'];related=[t for t in adapter.list_tables(base) if t.get('name')==target]
            allowed={target}|{t.get('id') for t in related}
            if actual.get('link_table') not in allowed:raise NianxiangError('field_conflict','topic link points to another table')

def plan_bootstrap(adapter,structure):
    structure=copy.deepcopy(structure);check_structure(structure)
    verify_account({'account_id':structure['account_id']},adapter)
    observed={};items=[]
    for spec in structure['nodes']:
        parent=observed.get(spec.get('parent'))
        node=select_node(adapter,structure,spec,parent) if not spec.get('parent') or parent else None
        if node:observed[spec['id']]=node
        items.append({'id':spec['id'],'kind':'node','title':spec['title'],'status':'reuse' if node else 'create','parent':spec.get('parent')})
    base=observed.get('operations.base')
    for spec in structure['tables']:
        table=select_table(adapter,base,spec) if base else None
        items.append({'id':spec['id'],'kind':'table','title':spec['title'],'status':'reuse' if table else 'create'})
    return {'schema_version':1,'account_id':structure['account_id'],'space_id':structure['space_id'],'structure':structure,'scope_digest':digest(structure),'items':items}

def authorize_bootstrap(plan,evidence):
    return {'confirmed':True,'by':'user','evidence':evidence,'scope_digest':plan['scope_digest'],'account_id':plan['account_id'],'space_id':plan['space_id']}

def resume_bootstrap(profile_dir,plan,adapter,authorization):
    profile=Path(profile_dir)
    try:
        state=profile_state(profile,require_active=False);structure=plan['structure'];check_structure(structure)
        if authorization.get('confirmed') is not True or authorization.get('by')!='user' or not str(authorization.get('evidence','')).strip() or authorization.get('scope_digest')!=digest(structure) or plan.get('scope_digest')!=digest(structure) or any(authorization.get(k)!=state[k] or structure.get(k)!=state[k] for k in ('account_id','space_id')):
            raise NianxiangError('authorization_required','skeleton authorization must match account, space and exact structure')
        verify_account(state,adapter)
        with profile_lock(profile):return _resume(profile,plan,adapter,authorization,state)
    except NianxiangError as exc:return {'status':'blocked','message':exc.code}

def _resume(profile,plan,adapter,authorization,state):
    structure=plan['structure'];path=profile/'bootstrap-state.json'
    progress=read_json(path) if path.exists() else {'schema_version':1,'scope_digest':plan['scope_digest'],'objects':{}}
    if progress['scope_digest']!=plan['scope_digest']:raise NianxiangError('bootstrap_scope_changed','existing build belongs to another scope')
    objects=progress['objects'];state['active']=False;write_json(profile/'state.json',state)
    observed={};tables={}
    def create(key,request):
        if objects.get(key,{}).get('attempted'):raise NianxiangError('uncertain_creation','previous creation has no discovered result; inspect before retrying')
        objects[key]={'attempted':True,'started_at':now()};write_json(path,progress)
        try:adapter.write(request)
        except NianxiangError as exc:
            if exc.code not in ('offline','timeout','network_error','invalid_response','uncertain_response'):
                objects[key]['attempted']=False;objects[key]['blocked_reason']=exc.code;write_json(path,progress)
            raise
    try:
        for spec in structure['nodes']:
            verify_account(state,adapter)
            parent=observed.get(spec.get('parent'))
            if spec.get('parent'):
                live=adapter.get_node({'node_token':parent['node_token']})
                if any(str(live.get(k,''))!=str(parent.get(k,'')) for k in ('space_id','node_token','obj_token','obj_type','parent_node_token','title')):raise NianxiangError('target_mismatch','parent changed during build')
            node=select_node(adapter,structure,spec,parent)
            if not node:
                target={'space_id':state['space_id'],'parent_node_token':(parent or {}).get('node_token',''),'title':spec['title'],'obj_type':spec['obj_type']}
                create(spec['id'],{'operation_id':'bootstrap-'+spec['id'],'target':target,'action':'create_node','content':{},'authorization':authorization})
                node=select_node(adapter,structure,spec,parent)
                if not node:raise NianxiangError('uncertain_creation','created node not discoverable')
            observed[spec['id']]=node;objects[spec['id']]={'verified':True,'node_token':node['node_token'],'obj_token':node['obj_token']};write_json(path,progress)
        base=observed['operations.base']
        for spec in structure['tables']:
            verify_account(state,adapter);table=select_table(adapter,base,spec)
            if not table:
                create('table:'+spec['id'],{'operation_id':'bootstrap-table-'+spec['id'],'target':{'obj_token':base['obj_token'],'title':spec['title'],'obj_type':'bitable'},'action':'create_table','content':{'fields':spec['fields']},'authorization':authorization})
                table=select_table(adapter,base,spec)
                if not table:raise NianxiangError('uncertain_creation','created table not discoverable')
            verify_fields(adapter,base,table,spec)
            tables[spec['id']]={'expected_title':spec['title'],'table_id':table['id']};objects['table:'+spec['id']]={'verified':True,'table_id':table['id']};write_json(path,progress)
        # Recheck every node after the full build before activating any connection.
        for spec in structure['nodes']:
            node=select_node(adapter,structure,spec,observed.get(spec.get('parent')))
            if not node or node['node_token']!=observed[spec['id']]['node_token']:raise NianxiangError('target_mismatch','structure changed before activation')
        verify_account(state,adapter)
        for spec in structure['tables']:
            table=select_table(adapter,base,spec)
            if not table or table['id']!=tables[spec['id']]['table_id']:raise NianxiangError('target_mismatch','table changed before activation')
            verify_fields(adapter,base,table,spec)
        config=copy.deepcopy(structure['config_template']);config['space_id']=state['space_id'];config['last_verified_date']=now()[:10]
        for key,item in config['knowledge_map'].items():
            node=observed[key]
            for field in ('node_token','obj_token','obj_type','parent_node_token'):item[field]=node.get(field,'')
        config['base_tables']=tables;validate(config)
        write_json(profile/'local-config.json',config);state['active']=True;state['bootstrap_verified_at']=now();write_json(profile/'state.json',state)
        progress['status']='ready';write_json(path,progress)
        return {'status':'ready','knowledge_mappings':12,'tables':4,'personal_content':'empty_or_existing_content_preserved'}
    except (NianxiangError,ValueError,KeyError) as exc:
        code=getattr(exc,'code','invalid_configuration');progress['status']='uncertain' if code in ('offline','timeout','network_error','uncertain_creation','invalid_response','uncertain_response') else 'blocked'
        progress['message']=code;write_json(path,progress)
        return {'status':progress['status'],'message':code,'profile_active':False}
