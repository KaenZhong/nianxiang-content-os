"""Fail-closed user-identity CLI adapter. No shell, credential storage or implicit login."""
from __future__ import annotations
import copy
import html
import json
import subprocess
from .models import NianxiangError,digest

class FeishuAdapter:
    def __init__(self,config,runner=None):
        self.config=copy.deepcopy(config);self.runner=runner or self._subprocess;self.account_id=None
    def _subprocess(self,command):
        try:proc=subprocess.run(command,capture_output=True,text=True,timeout=60,check=False)
        except FileNotFoundError as exc:raise NianxiangError('tool_missing','lark-cli is unavailable') from exc
        except subprocess.TimeoutExpired as exc:raise NianxiangError('timeout','CLI response timed out') from exc
        except OSError as exc:raise NianxiangError('network_error','CLI could not run') from exc
        try:payload=json.loads(proc.stdout)
        except ValueError as exc:raise NianxiangError('invalid_response','CLI response was not JSON; write outcome needs inspection') from exc
        if proc.returncode and payload.get('ok') is not False:raise NianxiangError('network_error','CLI returned an unknown failure')
        return payload
    def _run(self,args,auth=False):
        cmd=['lark-cli']
        if self.config.get('cli_profile'):cmd+=['--profile',self.config['cli_profile']]
        cmd+=args
        if not auth:cmd+=['--as','user','--format','json']
        payload=self.runner(cmd)
        if not isinstance(payload,dict):raise NianxiangError('invalid_response','CLI returned non-object')
        if payload.get('ok') is False:
            err=payload.get('error',{});kind=str(err.get('type',''))
            code='permission_denied' if kind in ('permission','authentication','authorization','auth') else ('network_error' if kind in ('network','transport') else 'cli_rejected')
            raise NianxiangError(code,'CLI rejected action; inspect permissions or target without logging private payload')
        if auth:return payload
        if payload.get('ok') is not True or payload.get('identity')!='user':raise NianxiangError('identity_unverified','CLI must return an ok user response')
        data=payload.get('data')
        if not isinstance(data,dict):raise NianxiangError('invalid_response','CLI data must be an object')
        return data
    def get_account(self):
        payload=self._run(['auth','status','--json','--verify'],auth=True);user=payload.get('identities',{}).get('user',{})
        if payload.get('verified') is not True or user.get('verified') is not True or not user.get('openId'):
            raise NianxiangError('identity_unverified','verified user account ID is required')
        self.account_id=user['openId'];return {'identity':'user','account_id':self.account_id}
    def get_node(self,target):
        item=self.config.get('knowledge_map',{}).get(target.get('knowledge_id'))
        node_token=target.get('node_token') or (item or {}).get('node_token')
        if not node_token:raise NianxiangError('target_mismatch','configured node is required')
        data=self._run(['wiki','+node-get','--node-token',node_token])
        node=data.get('node',data)
        return {**node,'account_id':self.account_id}
    def list_nodes(self,parent):
        args=['wiki','+node-list','--space-id',self.config['space_id'],'--page-all']
        if parent and parent.get('node_token'):args+=['--parent-node-token',parent['node_token']]
        data=self._run(args)
        if data.get('has_more'):raise NianxiangError('incomplete_listing','wiki discovery did not finish')
        nodes=data.get('nodes')
        if not isinstance(nodes,list):raise NianxiangError('invalid_response','wiki node list is missing')
        return nodes
    def list_tables(self,base):
        data=self._run(['base','+table-list','--base-token',base['obj_token']])
        if data.get('has_more'):raise NianxiangError('incomplete_listing','table discovery did not finish')
        tables=data.get('tables')
        if not isinstance(tables,list):raise NianxiangError('invalid_response','table list missing')
        return tables
    def list_fields(self,base,table):
        offset=0;items=[]
        while True:
            data=self._run(['base','+field-list','--base-token',base['obj_token'],'--table-id',table['id'],'--offset',str(offset),'--limit','200'])
            fields=data.get('fields')
            if not isinstance(fields,list):raise NianxiangError('invalid_response','field list missing')
            items+=fields
            if not data.get('has_more'):
                if len(fields)==200 and 'has_more' not in data:raise NianxiangError('incomplete_listing','field pagination status missing')
                return items
            if not fields or offset>10000:raise NianxiangError('incomplete_listing','field pagination did not finish')
            offset+=len(fields)
    def read(self,knowledge_id):
        node=self.get_node({'knowledge_id':knowledge_id})
        if node.get('obj_type')=='bitable':
            tables=self.list_tables(node);return {**node,'revision':digest(tables),'content':tables}
        if node.get('obj_type')!='docx':raise NianxiangError('unsupported_action','only Docx and Base can be read')
        data=self._run(['docs','+fetch','--doc',node['obj_token'],'--doc-format','markdown'])
        document=data.get('document',{})
        if document.get('document_id')!=node['obj_token'] or document.get('revision_id') is None or not isinstance(document.get('content'),str):raise NianxiangError('invalid_response','Docx identity, revision and body are required')
        return {**node,'revision':document['revision_id'],'content':document['content']}
    def _record_coordinates(self,target):
        base=self.config['knowledge_map'].get(target.get('knowledge_id'),{})
        table=self.config['base_tables'].get(target.get('table_key'),{})
        if base.get('obj_type')!='bitable' or not table.get('table_id'):raise NianxiangError('target_mismatch','configured Base and table required')
        tables=self.list_tables(base);matches=[x for x in tables if x.get('id')==table['table_id'] and x.get('name')==table['expected_title']]
        if len(matches)!=1:raise NianxiangError('target_mismatch','live table differs from configured table')
        return base,matches[0]
    def lookup(self,target,operation_id):
        if target.get('obj_type')!='bitable':raise NianxiangError('unsupported_action','record lookup requires Base')
        base,table=self._record_coordinates(target)
        data=self._run(['base','+record-list','--base-token',base['obj_token'],'--table-id',table['id'],'--filter-json',json.dumps({'logic':'and','conditions':[[target['key_field'],'==',target['object_key']]]},ensure_ascii=False),'--limit','200'])
        records=data.get('records')
        if not isinstance(records,list):raise NianxiangError('invalid_response','record list missing')
        if data.get('has_more') or len(records)>1:raise NianxiangError('duplicate_object_key','business key is not unique')
        if not records:return None
        record=records[0];fields=record.get('fields');rid=record.get('id') or record.get('record_id')
        if not isinstance(fields,dict) or not rid:raise NianxiangError('invalid_response','record fields and ID missing')
        if fields.get(target['key_field'])!=target['object_key']:raise NianxiangError('target_mismatch','server returned another record')
        return {'account_id':self.account_id,'space_id':self.config['space_id'],'record_id':rid,'revision':digest(fields),'content':fields,'target':copy.deepcopy(target)}
    def write(self,request):
        target=request['target'];action=request['action'];content=request['content']
        if target.get('obj_type')=='docx' and action in ('replace','append'):
            node=self.get_node(target)
            args=['docs','+update','--doc',node['obj_token'],'--revision-id',str(request['base_revision'])]
            if action=='replace':
                if '\n' in content['pattern'] or '\n' in content['replacement']:raise NianxiangError('unsupported_action','CLI exact replacement is single-line; use native tools for structured edits')
                args+=['--command','str_replace','--pattern',content['pattern'],'--content','<span>'+html.escape(content['replacement'])+'</span>']
            else:
                args+=['--command','append','--content','<p>'+html.escape(content['text']).replace('\n','<br/>')+'</p>']
            data=self._run(args)
            if data.get('result')!='success' or data.get('warnings'):raise NianxiangError('uncertain_response','Docx write was not fully confirmed')
            return {'revision':data.get('document',{}).get('revision_id')}
        if target.get('obj_type')=='bitable' and action in ('create','update'):
            base,table=self._record_coordinates(target);fields=self.list_fields(base,table)
            schema={f.get('name'):f for f in fields};readonly={'formula','lookup','auto_number','attachment','created_at','updated_at','created_by','updated_by','not_support'}
            for name,value in content.items():
                field=schema.get(name)
                if not field or field.get('type') in readonly:raise NianxiangError('invalid_field','field is missing or not writable')
                if field.get('type')=='select':
                    allowed={o.get('name') for o in field.get('options',[])};values=value if isinstance(value,list) else [value]
                    if not set(values).issubset(allowed):raise NianxiangError('invalid_option','select option is not in the live schema')
            existing=self.lookup(target,request['operation_id'])
            if action=='create' and existing:raise NianxiangError('record_conflict','key already exists')
            if action=='update' and (not existing or existing['revision']!=request['base_revision']):raise NianxiangError('record_conflict','latest record changed')
            args=['base','+record-upsert','--base-token',base['obj_token'],'--table-id',table['id'],'--json',json.dumps(content,ensure_ascii=False)]
            if action=='update':args+=['--record-id',existing['record_id']]
            data=self._run(args)
            if data.get('ignored_fields'):raise NianxiangError('uncertain_response','some fields were ignored')
            return {'record_id':(data.get('record') or {}).get('id') or (data.get('record') or {}).get('record_id')}
        if action=='create_node':
            if target.get('space_id')!=self.config['space_id']:raise NianxiangError('target_mismatch','node belongs to another space')
            args=['wiki','+node-create','--space-id',target['space_id'],'--obj-type',target['obj_type'],'--title',target['title']]
            if target.get('parent_node_token'):args+=['--parent-node-token',target['parent_node_token']]
            data=self._run(args);return data.get('node',data)
        if action=='create_table':
            data=self._run(['base','+table-create','--base-token',target['obj_token'],'--name',target['title'],'--fields',json.dumps(content['fields'],ensure_ascii=False)])
            return data.get('table',data)
        raise NianxiangError('unsupported_action','action is not supported by this adapter')
