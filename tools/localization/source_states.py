"""Authenticated before/after evidence views. Never writes a source file.

The compact certificate contains value hashes and 1,368 characters of reverse
delta, not copies of source values. Restoring a delta is only permitted after an
exact after hash match; the restored full value and full file must match before.
"""
from collections import Counter
from dataclasses import replace
from functools import lru_cache
import copy
import hashlib
import json
from pathlib import Path
import re

from .parser import HEADER, parse_text
from .restoration import digest

VALID_BEFORE = 'VALID_BEFORE'
ALREADY_APPLIED = 'ALREADY_APPLIED'
STALE_OR_CONFLICT = 'STALE_OR_CONFLICT'
ROOT = Path(__file__).resolve().parents[2]
CERTIFICATE = ROOT / 'reviews/source-patch-states.json'
CERTIFICATE_SHA256 = 'b3e2b6c533d49e7eed044675009a46cc4e85d2823d10d362ee4fe92a1b0ba920'


def fingerprint(obj):
    return digest(json.dumps(obj, ensure_ascii=False, sort_keys=True))


@lru_cache(None)
def _certificate():
    raw = CERTIFICATE.read_bytes()
    cert = json.loads(raw)
    # Review JSON is content-addressed across Git LF/CRLF checkouts. Game source
    # hashes below remain exact byte hashes, without newline normalization.
    if fingerprint(cert) != CERTIFICATE_SHA256:
        raise ValueError('Source state certificate hash mismatch')
    records = {r['string_id']: r for r in cert['records']}
    if cert['schema_version'] != 1 or len(records) != len(cert['records']):
        raise ValueError('Invalid source state certificate')
    return cert, records


def evidence_entry(entry):
    """Return an authenticated before entry and its tri-state classification."""
    _, records = _certificate()
    record = records.get(entry.string_id)
    if record is None or entry.path != record['source_path']:
        return entry, VALID_BEFORE
    if entry.line != record['source_line'] or entry.ambiguous:
        raise ValueError(f'{STALE_OR_CONFLICT}: occurrence {entry.string_id}')
    sha = digest(entry.value)
    if sha == record['before_sha256']:
        return entry, VALID_BEFORE
    if sha != record['after_sha256']:
        raise ValueError(f'{STALE_OR_CONFLICT}: value {entry.string_id}')
    value = entry.value
    for start, end, original in reversed(record['reverse_edits']):
        value = value[:start] + original + value[end:]
    if digest(value) != record['before_sha256']:
        raise ValueError(f'{STALE_OR_CONFLICT}: reverse delta {entry.string_id}')
    return replace(entry, value=value), ALREADY_APPLIED


def signature_cell(dataset, sid):
    """Preserve the original signature algorithm and occurrence identity."""
    from .gameplay import cell
    result = cell(dataset, sid)
    if dataset is not None and dataset.name == 'de_jp':
        for occurrence, entry in zip(result['occurrences'], dataset.entries.get(sid, [])):
            try:
                original, _ = evidence_entry(entry)
            except ValueError:
                # A third value remains in the signature and cannot match before.
                continue
            occurrence['value'] = original.value
    return result


def evidence_data(data):
    """Normalize certified after values in a private evidence view, fail closed.

For changed files, reparse the current bytes and verify all indexes, then reverse
only certified value deltas at exact physical lines. The original whole-file SHA
authenticates comments, whitespace, unrelated entries, and every technical token.
No cached mutable dataset or caller-provided 'validated' flag is trusted.
"""
    from .analysis import Dataset
    cert, records = _certificate()
    jp = data.get('de_jp')
    if jp is None:
        return data, {}
    bound_paths = {r['source_path'] for r in records.values()}
    if any(source.path in bound_paths and source.raw_bytes is not None for source in jp.files):
        # Even an otherwise-before snapshot must reject a third value; a missing
        # inferred alias must never turn a stale action display into an omission.
        for sid, record in records.items():
            entry = jp.resolved(sid)
            if entry is None or entry.path != record['source_path']:
                raise ValueError(f'{STALE_OR_CONFLICT}: missing/duplicate source {sid}')
            evidence_entry(entry)
    applied = {}
    for sid, record in records.items():
        for entry in jp.entries.get(sid, []):
            if digest(entry.value) == record['after_sha256']:
                if entry.path != record['source_path']:
                    raise ValueError(f'{STALE_OR_CONFLICT}: source path {sid}')
                original, state = evidence_entry(entry)
                if state == ALREADY_APPLIED:
                    if jp.resolved(sid) is None:
                        raise ValueError(f'{STALE_OR_CONFLICT}: nonunique occurrence {sid}')
                    applied[sid] = original
    if not applied:
        return data, {}
    for path, sha in cert['review_sha256'].items():
        if fingerprint(json.loads((ROOT / path).read_text(encoding='utf8'))) != sha:
            raise ValueError('Source state review certificate is stale: ' + path)
    # Certify every target, including those still before, in a mixed snapshot.
    for sid, record in records.items():
        entry = jp.resolved(sid)
        if entry is None or entry.path != record['source_path']:
            raise ValueError(f'{STALE_OR_CONFLICT}: missing/duplicate source {sid}')
        evidence_entry(entry)
    files = {f.path: f for d in data.values() for f in d.files}
    if len(files) != sum(len(d.files) for d in data.values()) or set(files) != set(cert['source_sha256']):
        raise ValueError(f'{STALE_OR_CONFLICT}: source inventory')
    normalized = Dataset('de_jp')
    current_index = Dataset('de_jp')
    for source in jp.files:
        if source.raw_bytes is None or hashlib.sha256(source.raw_bytes).hexdigest() != source.sha256:
            raise ValueError(f'{STALE_OR_CONFLICT}: source bytes/hash {source.path}')
        parsed = parse_text(source.raw_bytes.decode('utf-8-sig'), source.path)
        if parsed.entries != source.entries or parsed.issues != source.issues:
            raise ValueError(f'{STALE_OR_CONFLICT}: parsed source mismatch {source.path}')
        current_index.add(source)
        # Split physical lines only; retain every separator and BOM byte.
        lines = re.split(r'(\r\n|\n|\r)', source.raw_bytes.decode('utf-8'))
        entries = []
        for entry in source.entries:
            original = applied.get(entry.string_id, entry)
            entries.append(original)
            if original != entry:
                index = 2 * (entry.line - 1)
                raw = lines[index]
                offset = 1 if index == 0 and raw.startswith('\ufeff') else 0
                header = HEADER.match(raw, offset)
                if header is None or header[1] != entry.string_id:
                    raise ValueError(f'{STALE_OR_CONFLICT}: physical occurrence {entry.string_id}')
                start = header.end()
                if raw[start:start + len(entry.value)] != entry.value:
                    raise ValueError(f'{STALE_OR_CONFLICT}: physical value {entry.string_id}')
                lines[index] = raw[:start] + original.value + raw[start + len(entry.value):]
        raw = ''.join(lines).encode('utf-8')
        sha = hashlib.sha256(raw).hexdigest()
        if sha != cert['source_sha256'][source.path]:
            raise ValueError(f'{STALE_OR_CONFLICT}: restored source hash {source.path}')
        normalized.add(replace(source, entries=entries, raw_bytes=raw, sha256=sha, size_bytes=len(raw)))
    if (current_index.entries != jp.entries or current_index.issues != jp.issues
            or current_index.invalid_ids != jp.invalid_ids or current_index.empty_slots != jp.empty_slots):
        raise ValueError(f'{STALE_OR_CONFLICT}: source occurrence index')
    for name, dataset in data.items():
        if name != 'de_jp':
            for source in dataset.files:
                if source.sha256 != cert['source_sha256'][source.path]:
                    raise ValueError(f'{STALE_OR_CONFLICT}: identity source hash {source.path}')
    return {**data, 'de_jp': normalized}, {sid: ALREADY_APPLIED for sid in applied}


def project_scope(report, states):
    """Keep original span evidence, label authenticated applied occurrences no-op."""
    result = copy.deepcopy(report)
    for row in result['rows']:
        if row['related_string_id'] in states and row['scope_class'] == 'required':
            row.update(scope_class='already_consistent', change_candidate=False,
                       source_state=ALREADY_APPLIED)
    result['source_states'] = states
    counts = Counter(r['scope_class'] for r in result['rows'])
    result['scope_counts'] = {key: counts[key] for key in result['scope_counts']}
    return result


def restore_scope(data, ledger, rows, metadata):
    """Rebuild and compare the complete audit, never trust caller no-op flags."""
    from .scope import build_scope
    original, states = evidence_data(data)
    if not states:
        return original, rows, metadata, states
    descriptor = metadata.get('context_override_ledger')
    report = build_scope(original, ledger, context_path=descriptor['path'] if descriptor else None)
    expected = project_scope(report, states)
    if rows != expected['rows'] or {k:v for k,v in metadata.items() if k != 'rows'} != {
            k:v for k,v in expected.items() if k != 'rows'}:
        raise ValueError('Source state scope audit mismatch; regenerate scope from current source')
    return original, report['rows'], {k:v for k,v in report.items() if k != 'rows'}, states


def filter_plan(plan, states, *, phase2a=False, base_only=False):
    """Suppress only operations re-proven by the original formal planners."""
    if not states:
        return plan
    _, records = _certificate()
    result = copy.deepcopy(plan)
    if not base_only:
        group = 'phase2a' if phase2a else 'baseline'
        expected = {sid for sid in states if records[sid]['group'] == group}
        if expected - {op['string_id'] for op in result['operations']}:
            raise ValueError(f'{STALE_OR_CONFLICT}: applied operation missing from formal plan')
    for op in result['operations']:
        if op['string_id'] in states:
            record = records[op['string_id']]
            proof = {**op, 'layout_provenance': {'kind':'baseline_phase1d'}} if base_only else op
            if fingerprint(proof) != record['operation_sha256']:
                raise ValueError(f'{STALE_OR_CONFLICT}: planned operation {op["string_id"]}')
    removed = {o['string_id'] for o in result['operations'] if o['string_id'] in states}
    result['operations'] = [o for o in result['operations'] if o['string_id'] not in removed]
    ops = result['operations']
    stats = result['statistics']
    result['source_states'] = states
    if phase2a:
        for target in result['targets']:
            if target['string_id'] in removed:
                target.update(status='already_matching', change_required=False, source_state=ALREADY_APPLIED)
        stats.update(changed_ids=len(ops), already_matching=sum(t['status']=='already_matching' for t in result['targets']),
                     full=sum(o['replacement_type']=='full_value' for o in ops),
                     span=sum(o['replacement_type']=='span' for o in ops), unique_operation_ids=len(ops))
    else:
        result['locations'] = [o for o in result['locations'] if o['string_id'] not in removed]
        stats.update(patch_operations=len(ops), unique_source_locations=len(result['locations']),
                     unique_string_ids=len({o['string_id'] for o in ops}),
                     full_value_replacements=sum(o['replacement_type']=='full_value' for o in ops),
                     span_replacements=sum(o['replacement_type']=='span' for o in ops),
                     accepted_candidate_rows=sum(o['merged_candidate_count'] for o in ops),
                     duplicate_id_patch_operations=sum(o['duplicate_dataset_id'] for o in ops),
                     per_decision=dict(sorted(Counter(s for o in ops for s in o['decision_string_ids']).items())),
                     per_relation=dict(sorted(Counter(s for o in ops for s in o['relations']).items())),
                     already_applied=len(removed))
        if not base_only:
            stats.update(layout_resolved_locations=sum(o['layout_provenance']['kind'] != 'baseline_phase1d' for o in ops),
                         automatic_layout_locations=sum(o['layout_provenance']['kind'] == 'automatic_layout' for o in ops),
                         human_layout_locations=sum(o['layout_provenance']['kind'] == 'human_layout' for o in ops))
    return result
