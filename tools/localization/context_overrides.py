"""Explicit context-bound whole-value decisions, never terminology propagation."""
import json
from pathlib import Path

from .adoption import signature
from .analysis import occurrence
from .human_reviews import validate as validate_decisions
from .restoration import digest

DEFAULT_PATH=Path(__file__).resolve().parents[2]/'reviews/context-overrides.json'
RELATION='explicit_context_override'


def fingerprint(value):
    return digest(json.dumps(value,ensure_ascii=False,sort_keys=True))


def record_signature(record):
    return fingerprint({k:v for k,v in record.items() if k!='binding_signature'})


def load(path=DEFAULT_PATH):
    path=Path(path)
    with path.open(encoding='utf-8') as stream:ledger=json.load(stream)
    if ledger.get('schema_version')!=1 or ledger.get('authority')!='explicit_context_decisions':
        raise ValueError('Invalid context override schema/authority')
    validate_decisions(ledger)
    for r in ledger['records']:
        if r.get('kind')!='context_full_value' or r.get('binding_signature')!=record_signature(r):
            raise ValueError('Invalid context override binding signature: '+r['string_id'])
    return ledger


def binding(data,record):
    sid=record['string_id'];jp=data['de_jp'].resolved(sid);en=data['de_en'].resolved(sid)
    if jp is None or en is None:raise ValueError('Context override has missing/ambiguous input: '+sid)
    hashes={f.path:f.sha256 for d in data.values() for f in d.files}
    return dict(source_path=jp.path,source_line=jp.line,source_sha256=hashes[jp.path],
                current_value_sha256=digest(jp.value),english_source=occurrence(en),english_sha256=hashes[en.path])


def validate_source(data,ledger):
    from .patch_plan import tokens
    from .source_states import evidence_data
    live = data
    data, states = evidence_data(data)
    validate_decisions(ledger)
    locations=set()
    for r in ledger['records']:
        sid=r['string_id']
        if sid in states and live['de_jp'].resolved(sid).value != r['proposed_jp']:
            raise ValueError('Context expected after value mismatch: '+sid)
        if r.get('binding_signature')!=record_signature(r):raise ValueError('Context record signature mismatch: '+sid)
        if r.get('kind')!='context_full_value' or r.get('target')!=binding(data,r):
            raise ValueError('Context source occurrence/hash mismatch: '+sid)
        if data['de_en'].resolved(sid).value!=r['expected_de_english'] or signature(data,sid,r['help_ids'])!=r['signature']:
            raise ValueError('Context source evidence signature mismatch: '+sid)
        jp=data['de_jp'].resolved(sid)
        if tokens(jp.value)!=tokens(r['proposed_jp']):raise ValueError('Context technical tokens changed: '+sid)
        loc=(jp.path,jp.line)
        if loc in locations:raise ValueError('Duplicate context override location')
        locations.add(loc)


def rows(data,ledger):
    from .scope import comparison_fields,excerpt
    validate_source(data,ledger)
    result=[]
    for r in ledger['records']:
        sid=r['string_id'];jp=data['de_jp'].resolved(sid)
        changed=jp.value!=r['proposed_jp']
        cls='required' if changed else 'already_consistent'
        result.append(dict(decision_string_id=sid,decision_en=r['expected_de_english'],current_jp=jp.value,
            effective_jp=r['proposed_jp'],effective_decision=r['decision'],related_string_id=sid,
            related_type='context_full_value',related_en=excerpt(r['expected_de_english']),related_jp=excerpt(jp.value),
            source_path=jp.path,source_line=jp.line,relation=RELATION,scope_class=cls,confidence='high',
            reason='Explicit human whole-value override, limited to the bound context; no propagation.',
            reviewer_decision='',reviewer_notes=r['notes'],start=0,end=len(jp.value),matched_jp=jp.value,
            excerpted=len(jp.value)>180 or len(r['expected_de_english'])>180,english_source=r['target']['english_source'],
            source_sha256=r['target']['source_sha256'],decision_signature=r['signature'],
            context_signature=r['binding_signature'],evidence_status='matches',change_candidate=changed,
            literal_scope_class=cls,literal_change_candidate=changed,**comparison_fields(jp.value,r['proposed_jp']),
            conflict=False,match_basis=['explicit_context_decision']))
    return result


def merge_scope(existing,direct_rows):
    owners={(r['source_path'],r['source_line']):r for r in direct_rows}
    for r in existing:
        owner=owners.get((r['source_path'],r['source_line']))
        if owner:
            r.update(scope_class='review',change_candidate=False,conflict=False,
                     suppressed_by_context_override=owner['decision_string_id'],
                     suppression_signature=owner['context_signature'],
                     reason=r['reason']+' Explicit whole-value decision owns this occurrence; propagation retained for audit only.')
    return existing+direct_rows


def from_metadata(data,metadata):
    if 'context_override_ledger' not in metadata:return None,[]
    descriptor=metadata['context_override_ledger']
    ledger=load(Path(descriptor['path']))
    if fingerprint(ledger)!=descriptor['sha256']:raise ValueError('Context override ledger hash mismatch')
    return ledger,rows(data,ledger)


def validate_scope(data,audit_rows,metadata):
    """Reconstruct ownership; do not trust edited suppression flags or exclusions."""
    ledger,expected=from_metadata(data,metadata)
    actual=[r for r in audit_rows if r['relation']==RELATION]
    if len(actual)!=len(expected):raise ValueError('Missing/extra context scope rows')
    for expected_row in expected:
        matches=[r for r in actual if r['decision_string_id']==expected_row['decision_string_id']]
        if len(matches)!=1 or any(matches[0].get(k)!=v for k,v in expected_row.items()):
            raise ValueError('Context scope record mismatch')
    owners={(r['source_path'],r['source_line']):r for r in expected}
    for r in audit_rows:
        if r['relation']==RELATION:continue
        owner=owners.get((r['source_path'],r['source_line']))
        if owner:
            if (r.get('suppressed_by_context_override')!=owner['decision_string_id'] or
                r.get('suppression_signature')!=owner['context_signature'] or r['scope_class']!='review' or r['change_candidate']):
                raise ValueError('Context override ownership mismatch')
        elif r.get('suppressed_by_context_override'):
            raise ValueError('Unbound suppression of name propagation')
    return ledger
