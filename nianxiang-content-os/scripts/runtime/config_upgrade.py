"""Read-only discovery and account-bound schema 4 -> 5 private configuration upgrade."""
from __future__ import annotations
import copy
from pathlib import Path
from validate_local_config import validate
from .models import NianxiangError, digest, file_digest, read_json, write_json, profile_lock, now
from .knowledge import profile_state, verify_account, verify_node
from .personal import parse_personal_source

METHODS_TITLE = '01｜创作方法与规则'


def _validate(config, version):
    try:
        validate(config, schema_version=version)
    except (ValueError, KeyError, TypeError) as exc:
        raise NianxiangError('invalid_configuration', 'configuration does not match its upgrade schema') from exc


def _bound_adapter(adapter, config):
    """New mappings require a distinct adapter view; never mutate the caller's config."""
    bound = copy.copy(adapter)
    bound.config = copy.deepcopy(config)
    return bound


def _read_binding(state, config, key, adapter):
    verify_node(state, config, {'knowledge_id': key}, adapter)
    item = adapter.read(key)
    mapping = config['knowledge_map'][key]
    if any(item.get(k) != v for k, v in {'account_id': state['account_id'], 'space_id': state['space_id'], 'obj_token': mapping['obj_token']}.items()):
        raise NianxiangError('target_mismatch', 'source body identity differs from configured object')
    if item.get('revision') is None or not isinstance(item.get('content'), str):
        raise NianxiangError('invalid_response', 'source body and revision are required')
    if key == 'methodology.current':
        try:
            data = parse_personal_source(item['content'], 'rules')
        except NianxiangError as exc:
            raise NianxiangError('private_rules_migration_required', 'historical root machine rules need a separate reviewed migration') from exc
        if data.get('rules'):
            raise NianxiangError('private_rules_migration_required', 'historical root machine rules must be retained and explicitly migrated')
    else:
        parse_personal_source(item['content'], 'rules')
    return {'obj_token': mapping['obj_token'], 'mapping_digest': digest(mapping), 'revision': item['revision'], 'body_digest': digest(item['content'])}


def verify_methods_authority(state, config, adapter):
    """Every connection path must reject leftover root rules before activation."""
    verify_account(state, adapter)
    bound = _bound_adapter(adapter, config)
    bindings = {key: _read_binding(state, config, key, bound) for key in ('methodology.current', 'content.methods')}
    verify_account(state, bound)
    return bindings


def _discover(state, source, adapter):
    root = source['knowledge_map']['methodology.current']
    children = adapter.list_nodes(root)
    if not isinstance(children, list) or not all(isinstance(x, dict) for x in children):
        raise NianxiangError('invalid_response', 'complete child listing required')
    matches = [x for x in children if x.get('title') == METHODS_TITLE]
    if len(matches) != 1:
        raise NianxiangError('ambiguous_methods_source', 'exactly one directly nested methods document is required')
    child = matches[0]
    if child.get('space_id') != state['space_id'] or child.get('parent_node_token') != root['node_token'] or child.get('obj_type') != 'docx':
        raise NianxiangError('target_mismatch', 'methods document must be a Docx child in the same space')
    if not child.get('node_token') or not child.get('obj_token'):
        raise NianxiangError('invalid_response', 'methods document identity is required')
    candidate = copy.deepcopy(source)
    candidate['schema_version'] = 5
    candidate['knowledge_map']['content.methods'] = {'expected_title': METHODS_TITLE, 'node_token': child['node_token'], 'obj_token': child['obj_token'], 'obj_type': 'docx', 'parent_node_token': root['node_token'], 'access': 'read_write'}
    candidate['write_targets']['sync_candidate_knowledge_ids'].append('content.methods')
    _validate(candidate, 5)
    return candidate


def _verify_sources(state, source, candidate, adapter):
    verify_account(state, adapter)
    original_adapter = _bound_adapter(adapter, source)
    for key in source['knowledge_map']:
        verify_node(state, source, {'knowledge_id': key}, original_adapter)
    # Repeat discovery ensures the chosen child remains unique before applying.
    if _discover(state, source, original_adapter) != candidate:
        raise NianxiangError('source_binding_changed', 'methods mapping differs from preview')
    return verify_methods_authority(state, candidate, adapter)


def plan_config_upgrade(profile_dir, adapter):
    """Inspect only; no local cache/config changes and no remote writes."""
    profile = Path(profile_dir).resolve()
    try:
        state = profile_state(profile, require_active=False)
        source = read_json(profile/'local-config.json')
        if source.get('schema_version') == 5:
            _validate(source, 5)
            return {'status': 'current', 'schema_version': 5, 'profile_id': state['profile_id']}
        _validate(source, 4)
        if source['space_id'] != state['space_id']:
            raise NianxiangError('space_mismatch', 'configuration belongs to another space')
        verify_account(state, adapter)
        candidate = _discover(state, source, _bound_adapter(adapter, source))
        bindings = _verify_sources(state, source, candidate, adapter)
        plan = {'schema_version': 1, 'profile_id': state['profile_id'], 'account_id': state['account_id'], 'space_id': state['space_id'], 'source': source, 'source_digest': digest(source), 'source_file_digest': file_digest(profile/'local-config.json'), 'candidate': candidate, 'candidate_digest': digest(candidate), 'bindings': bindings}
        plan['plan_id'] = digest(plan)
        plan['status'] = 'preview'
        return plan
    except (NianxiangError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return {'status': 'blocked', 'code': getattr(exc, 'code', 'invalid_plan')}


def apply_config_upgrade(profile_dir, plan, adapter, consent):
    """Apply an exact preview locally, retain backup, and require structural re-verification."""
    profile = Path(profile_dir).resolve()
    try:
        if not isinstance(consent, str) or not consent.strip():
            raise NianxiangError('authorization_required', 'configuration upgrade requires explicit user instruction')
        if not isinstance(plan, dict) or plan.get('status') != 'preview' or digest({k: v for k, v in plan.items() if k not in ('plan_id', 'status')}) != plan.get('plan_id'):
            raise NianxiangError('invalid_plan', 'preview was modified')
        source, candidate = plan['source'], plan['candidate']
        _validate(source, 4); _validate(candidate, 5)
        if digest(source) != plan['source_digest'] or digest(candidate) != plan['candidate_digest']:
            raise NianxiangError('invalid_plan', 'preview configuration digests differ')
        with profile_lock(profile):
            state = profile_state(profile, require_active=False)
            if any(plan.get(k) != state.get(k) for k in ('profile_id', 'account_id', 'space_id')):
                raise NianxiangError('invalid_plan', 'preview belongs to another profile or account')
            current = read_json(profile/'local-config.json')
            already = digest(current) == plan['candidate_digest']
            if not already and (digest(current) != plan['source_digest'] or file_digest(profile/'local-config.json') != plan['source_file_digest']):
                return {'status': 'conflict', 'code': 'configuration_changed'}
            if _verify_sources(state, source, candidate, adapter) != plan['bindings']:
                return {'status': 'conflict', 'code': 'source_changed'}
            backup_name = 'local-config.schema4.' + plan['source_digest'][:16] + '.json'
            backup = profile/backup_name
            if backup.exists():
                if digest(read_json(backup)) != plan['source_digest']:
                    raise NianxiangError('backup_conflict', 'existing schema 4 backup differs')
            else:
                if already:
                    raise NianxiangError('backup_missing', 'cannot acknowledge a prior upgrade without its original backup')
                write_json(backup, source)
            if not already:
                # Deactivate before changing config, so a interrupted upgrade fails closed.
                state['active'] = False
                state['config_upgrade'] = {'plan_id': plan['plan_id'], 'from_schema': 4, 'to_schema': 5, 'at': now(), 'consent': consent, 'backup': backup_name, 'context_invalidated': True}
                write_json(profile/'state.json', state)
                write_json(profile/'local-config.json', candidate)
            return {'status': 'upgraded', 'schema_version': 5, 'backup': backup_name, 'already_applied': already, 'requires_verification': not bool(state.get('active')), 'originals_retained': True, 'source_written': False}
    except (NianxiangError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return {'status': 'blocked', 'code': getattr(exc, 'code', 'invalid_plan')}
