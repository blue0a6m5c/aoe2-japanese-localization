"""Occurrence-bound Phase 2A terminology dry-run planning; never applies source changes."""
from collections import Counter
import json

from .analysis import id_sort
from .human_reviews import (PHASE2A_BINDING_MODE, source_bindings_match,
                            target_binding_signature, target_scope_signature, validate)
from .layout_plan import (PHASE2A_LAYOUT_BINDING_MODE, record_signature,
                          explicit_human_layout_safe)
from .patch_plan import tokens
from .restoration import digest
from .scope import layout_key


def _layout_records(layout_ledger):
    records = []
    for record in layout_ledger.get('records', []):
        if record.get('binding', {}).get('binding_mode') == PHASE2A_LAYOUT_BINDING_MODE:
            records.append(record)
    return records


def validate_layout_records(data, wording_ledger, layout_ledger):
    """Validate Phase 2A compact layouts against the wording ledger and live source."""
    validate(wording_ledger)
    if (layout_ledger.get('schema_version') != 1
            or layout_ledger.get('authority') != 'explicit_user_layout_decisions'):
        raise ValueError('Invalid human layout ledger authority/schema')
    targets = {}
    for owner in wording_ledger['records']:
        if owner.get('binding_mode') != PHASE2A_BINDING_MODE:
            continue
        if not source_bindings_match(owner, data):
            raise ValueError(f'Stale Phase 2A wording binding: {owner["string_id"]}')
        for target in owner['target_bindings']:
            targets[target['string_id']] = (owner, target)
    result = {}
    for record in _layout_records(layout_ledger):
        if record.get('signature') != record_signature(record):
            raise ValueError(f'Invalid Phase 2A layout signature: {record.get("string_id")}')
        sid = record['string_id']
        if sid in result:
            raise ValueError(f'Duplicate Phase 2A layout target: {sid}')
        if sid not in targets:
            raise ValueError(f'Phase 2A layout target is not wording-bound: {sid}')
        owner, target = targets[sid]
        binding = record['binding']
        expected = dict(
            binding_mode=PHASE2A_LAYOUT_BINDING_MODE,
            wording_decision_string_id=owner['string_id'],
            wording_decision_signature=owner['signature'],
            target_scope_signature=owner['target_scope_signature'],
            concept_id=owner['concept_id'], category=owner['category'], role='compact_name',
            target_binding_signature=target['binding_signature'],
            source_path=target['jp_source']['path'], source_line=target['jp_source']['line'],
            string_id=sid, current_term=target['current_japanese_term'],
            jp_span=target['jp_span'], layout_before=binding.get('layout_before'),
            canonical=owner['proposed_jp'])
        if binding != expected:
            raise ValueError(f'Phase 2A layout evidence mismatch: {sid}')
        if target['role'] != 'compact_name' or not target['change_required']:
            raise ValueError(f'Phase 2A layout target is not a changed compact name: {sid}')
        jp = data['de_jp'].resolved(sid)
        start, end = target['jp_span']
        if (not jp or record['source_path'] != jp.path or record['source_line'] != jp.line
                or record['source_path'] != binding['source_path']
                or record['source_line'] != binding['source_line']
                or jp.value[start:end] != target['current_japanese_term']):
            raise ValueError(f'Phase 2A layout source mismatch: {sid}')
        replacement = record.get('replacement')
        after = jp.value[:start] + replacement + jp.value[end:]
        if (not isinstance(replacement, str)
                or not isinstance(binding.get('layout_before'), str)
                or layout_key(binding['layout_before']) != layout_key(owner['proposed_jp'])
                or layout_key(replacement) != layout_key(owner['proposed_jp'])
                or not explicit_human_layout_safe(binding['layout_before'], replacement,
                                                  replacement, owner['proposed_jp'])
                or (tokens(jp.value) != tokens(after)
                    and not explicit_human_layout_safe(
                        jp.value, after, replacement, owner['proposed_jp']))):
            raise ValueError(f'Unsafe Phase 2A human layout: {sid}')
        result[sid] = record
    return result


def build_plan(data, wording_ledger, layout_ledger):
    """Build all 249 Phase 2A targets and 141 virtual operations from explicit bindings."""
    layouts = validate_layout_records(data, wording_ledger, layout_ledger)
    source_hashes = {source.path:source.sha256 for dataset in data.values() for source in dataset.files}
    targets = []
    operations = []
    blocked = []
    target_owners = {}
    layout_used = set()
    records = [r for r in wording_ledger['records'] if r.get('binding_mode') == PHASE2A_BINDING_MODE]
    for owner in records:
        for binding in owner['target_bindings']:
            sid = binding['string_id']
            previous = target_owners.get(sid)
            if previous is not None:
                raise ValueError(f'Duplicate Phase 2A target: {sid} ({previous}, {owner["string_id"]})')
            target_owners[sid] = owner['string_id']
            jp = data['de_jp'].resolved(sid)
            start, end = binding['jp_span']
            replacement = owner['proposed_jp']
            layout = layouts.get(sid)
            if layout:
                replacement = layout['replacement']
                layout_used.add(sid)
            before = jp.value
            after = (before[:start] + replacement + before[end:]
                     if binding['change_required'] else before)
            reason = None
            if target_binding_signature(binding) != binding['binding_signature']:
                reason = 'target_binding_signature_mismatch'
            elif target_scope_signature(owner) != owner['target_scope_signature']:
                reason = 'target_scope_signature_mismatch'
            elif binding['role'] == 'compact_name' and binding['change_required'] and r'\n' in before[start:end] and not layout:
                reason = 'missing_explicit_compact_layout'
            elif not binding['change_required']:
                pass
            elif layout:
                layout_before = layout['binding']['layout_before']
                if (not explicit_human_layout_safe(layout_before, replacement,
                                                   replacement, owner['proposed_jp'])
                        or not explicit_human_layout_safe(before, after, replacement,
                                                          owner['proposed_jp'])):
                    reason = 'unsafe_explicit_human_layout'
            elif tokens(before) != tokens(after):
                reason = 'technical_structure_changed'
            target = dict(concept_id=owner['concept_id'], concept=owner['expected_de_english'],
                category=owner['category'], gameplay_object=owner['de_object'], role=binding['role'],
                string_id=sid, source_path=jp.path, source_line=jp.line,
                current_japanese=binding['current_japanese_term'], adopted_japanese=owner['proposed_jp'],
                change_required=binding['change_required'], jp_span=[start,end],
                binding_signature=binding['binding_signature'], target_scope_signature=owner['target_scope_signature'],
                layout_record_signature=layout['signature'] if layout else None,
                status='blocked' if reason else ('change' if binding['change_required'] else 'already_matching'),
                blocking_reason=reason)
            targets.append(target)
            if reason:
                blocked.append(target)
                continue
            if not binding['change_required']:
                continue
            replacement_type = 'full_value' if (start,end) == (0,len(before)) else 'span'
            payload = [jp.path,jp.line,sid,start,end,replacement,owner['concept_id']]
            operation = dict(operation_id=digest(json.dumps(payload,ensure_ascii=False))[:20],
                source_path=jp.path, source_line=jp.line, string_id=sid, before=before, after=after,
                expected_source_sha256=source_hashes[jp.path], expected_value_sha256=digest(before),
                matched_span=[start,end], matched=before[start:end], replacement=replacement,
                replacement_type=replacement_type, decision_string_ids=[owner['string_id']],
                relations=['phase2a_target_binding'], evidence=[dict(concept_id=owner['concept_id'],
                    category=owner['category'], gameplay_object=owner['de_object'], role=binding['role'],
                    binding_signature=binding['binding_signature'], target_scope_signature=owner['target_scope_signature'])],
                merged_candidate_count=1, duplicate_dataset_id=False,
                layout_provenance=(dict(kind='human_layout', record_signature=layout['signature'])
                                   if layout else dict(kind='phase2a_wording_binding')))
            operations.append(operation)
    if layout_used != set(layouts):
        raise ValueError(f'Unused Phase 2A layout records: {sorted(set(layouts)-layout_used,key=id_sort)}')
    targets.sort(key=lambda row:id_sort(row['string_id']))
    operations.sort(key=lambda row:(row['source_path'],row['source_line'],id_sort(row['string_id'])))
    stats = dict(concepts=len(records), target_bindings=len(targets), changed_ids=len(operations),
        already_matching=sum(not row['change_required'] for row in targets), blocked=len(blocked),
        full=sum(row['replacement_type']=='full_value' for row in operations),
        span=sum(row['replacement_type']=='span' for row in operations),
        layout_records=len(layouts), unique_target_ids=len({row['string_id'] for row in targets}),
        unique_operation_ids=len({row['string_id'] for row in operations}),
        roles=dict(sorted(Counter(row['role'] for row in targets).items())))
    return dict(schema_version=1, mode='phase2a_virtual_patch_enabled_dry_run',
                statistics=stats, targets=targets, operations=operations, blocked=blocked)
