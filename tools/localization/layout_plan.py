"""Integrate validated automatic layout and explicit human decisions, dry-run only."""
from collections import Counter
import copy
import json

from .blocked_audit import audit_blocked
from .patch_plan import build_plan,tokens
from .restoration import digest
from .scope import layout_key
from .adoption import tsv
from .analysis import id_sort


PHASE2A_LAYOUT_BINDING_MODE = 'phase2a_wording_compact_layout_v1'


def tokens_without_newlines(value):
    """Technical tokens with display newlines omitted for explicit human layout review."""
    return [token for token in tokens(value) if token not in (r'\n', '\r', '\n')]


def explicit_human_layout_safe(before, after, replacement, canonical):
    """Allow only layout whitespace/newline changes around an adjudicated wording value."""
    return (layout_key(replacement) == layout_key(canonical)
            and tokens_without_newlines(before) == tokens_without_newlines(after)
            and tokens_without_newlines(replacement) == tokens_without_newlines(canonical))


def binding(item):
    return dict(source_path=item['source_path'],source_line=item['source_line'],string_id=item['string_id'],
                current=item['current'],requests=[{k:r[k] for k in
                ('decision_string_id','decision_signature','relation','source_sha256','english_source',
                 'canonical','matched_span','matched')} for r in item['requests']])


def record_signature(record):
    return digest(json.dumps({k:v for k,v in record.items() if k!='signature'},ensure_ascii=False,sort_keys=True))


def key(item):
    return item['source_path'],item['source_line'],item['string_id']


def integrate(data,ledger,rows,metadata,hashes,human):
    baseline=build_plan(data,ledger,rows,metadata,hashes)
    audit=audit_blocked(data,ledger,rows,metadata,hashes)
    if human.get('schema_version')!=1 or human.get('authority')!='explicit_user_layout_decisions':
        raise ValueError('Invalid human layout ledger authority/schema')
    records={}
    for r in human['records']:
        if r.get('signature')!=record_signature(r): raise ValueError('Invalid human layout record signature')
        mode=r.get('binding',{}).get('binding_mode')
        if mode is not None:
            if mode != PHASE2A_LAYOUT_BINDING_MODE:
                raise ValueError('Unknown human layout binding mode')
            # Phase 2A records are validated and consumed by phase2a_patch_plan.
            # They must not enter the legacy inferred-scope planner while wording is deferred.
            continue
        if key(r) in records: raise ValueError('Duplicate human layout occurrence')
        records[key(r)]=r
    unresolved={key(x):x for x in audit['manual_review']}
    if set(records)-set(unresolved):
        raise ValueError('Human layout records do not match current manual review occurrences')
    result=copy.deepcopy(baseline)
    added=[]; added_locations=[]; resolved=set(); failed={}
    # Keep the legacy plan's provenance stable while Phase 2A scoped decisions are deferred.
    legacy_human={**human,'records':[r for r in human['records']
                                     if r.get('binding',{}).get('binding_mode') is None]}
    ledger_hash=digest(json.dumps(legacy_human,ensure_ascii=False,sort_keys=True))
    for item in audit['auto_resolvable']+audit['manual_review']:
        loc=key(item); h=records.get(loc)
        if item in audit['manual_review']:
            if h is None: continue
            if binding(item)!=h.get('binding'):
                failed[loc]='human_layout_evidence_mismatch'; continue
            if any(r['blocked_reason']!=['technical_structure_changed'] for r in item['requests']):
                failed[loc]='human_layout_non_layout_gate'; continue
        candidates={}; error=None
        for request in item['requests']:
            a,b=request['matched_span']; before=item['current']
            replacement=h['replacement'] if h else request['proposed_replacement']
            if not isinstance(replacement,str) or before[a:b]!=request['matched']:
                error='layout_current_span_mismatch'; break
            if layout_key(replacement)!=layout_key(request['canonical']):
                error='layout_canonical_mismatch'; break
            after=before[:a]+replacement+before[b:]
            if h:
                if not explicit_human_layout_safe(before,after,replacement,request['canonical']):
                    error='layout_technical_structure_changed'; break
            elif tokens(before)!=tokens(after): error='layout_technical_structure_changed'; break
            if after==before or layout_key(before[a:b])==layout_key(replacement):
                error='layout_normalized_equivalent'; break
            if (a,b) in candidates and candidates[(a,b)][0]!=replacement:
                error='layout_replacement_conflict'; break
            candidates.setdefault((a,b),(replacement,[]))[1].append(request)
        spans=sorted(candidates)
        if any(spans[i][0]<spans[i-1][1] for i in range(1,len(spans))): error='layout_overlap_conflict'
        if error: failed[loc]=error; continue
        full_after=item['current']
        for a,b in reversed(spans): full_after=full_after[:a]+candidates[(a,b)][0]+full_after[b:]
        if h:
            safe=(tokens_without_newlines(full_after)==tokens_without_newlines(item['current'])
                  and all(layout_key(candidates[span][0]) == layout_key(r['canonical'])
                          for span in spans for r in candidates[span][1]))
        else:
            safe=tokens(full_after)==tokens(item['current'])
        if not safe:
            failed[loc]='layout_combined_tokens_changed'; continue
        opids=[]
        for a,b in spans:
            replacement,requests=candidates[(a,b)]
            proofs=[{k:r[k] for k in ('decision_string_id','decision_signature','relation','english_source')} for r in requests]
            proofs=sorted({json.dumps(p,sort_keys=True):p for p in proofs}.values(),key=lambda p:(id_sort(p['decision_string_id']),p['relation']))
            opid=digest(json.dumps([*loc,a,b,replacement],ensure_ascii=False))[:20];opids.append(opid)
            provenance=(dict(kind='human_layout',review_id=human['review_id'],reviewer=human['reviewer'],
                            record_signature=h['signature'],layout_ledger_sha256=ledger_hash) if h else
                        dict(kind='automatic_layout',rule='unique_canonical_space_unchanged_component_v1',
                             reasons=sorted({r['resolution_reason'] for r in requests})))
            added.append(dict(operation_id=opid,source_path=loc[0],source_line=loc[1],string_id=loc[2],
                before=item['current'],after=item['current'][:a]+replacement+item['current'][b:],
                expected_source_sha256=requests[0]['source_sha256'],expected_value_sha256=digest(item['current']),
                matched_span=[a,b],matched=item['current'][a:b],replacement=replacement,
                replacement_type='full_value' if (a,b)==(0,len(item['current'])) else 'span',
                decision_string_ids=sorted({p['decision_string_id'] for p in proofs},key=id_sort),
                relations=sorted({p['relation'] for p in proofs}),evidence=proofs,
                merged_candidate_count=len(requests),duplicate_dataset_id=requests[0]['duplicate_dataset_id'],
                layout_provenance=provenance))
        added_locations.append(dict(source_path=loc[0],source_line=loc[1],string_id=loc[2],before=item['current'],after=full_after,
            expected_source_sha256=item['requests'][0]['source_sha256'],expected_value_sha256=digest(item['current']),operation_ids=opids))
        resolved.add(loc)
    for op in result['operations']: op['layout_provenance']={'kind':'baseline_phase1d'}
    result['operations']+=added;result['locations']+=added_locations
    result['operations'].sort(key=lambda o:(*key(o),o['matched_span']))
    result['locations'].sort(key=key)
    result['blocked']=[b for b in result['blocked'] if key(b) not in resolved]
    for b in result['blocked']:
        if key(b) in failed:b['reasons']=sorted(set(b['reasons']+[failed[key(b)]]))
    ops=result['operations'];blocked=result['blocked'];s=result['statistics']
    s.update(patch_operations=len(ops),unique_source_locations=len(result['locations']),unique_string_ids=len({o['string_id'] for o in ops}),
        full_value_replacements=sum(o['replacement_type']=='full_value' for o in ops),span_replacements=sum(o['replacement_type']=='span' for o in ops),
        accepted_candidate_rows=sum(o['merged_candidate_count'] for o in ops),blocked_locations=len(blocked),
        blocked_candidate_rows=sum(b['candidate_count'] for b in blocked),conflicts=sum(any('conflict' in r for r in b['reasons']) for b in blocked),
        duplicate_id_patch_operations=sum(o['duplicate_dataset_id'] for o in ops),
        blocked_reasons=dict(sorted(Counter(r for b in blocked for r in b['reasons']).items())),
        per_decision=dict(sorted(Counter(d for o in ops for d in o['decision_string_ids']).items(),key=lambda p:id_sort(p[0]))),
        per_relation=dict(sorted(Counter(r for o in ops for r in o['relations']).items())),
        layout_resolved_locations=len(resolved),automatic_layout_locations=sum(key(x) in resolved for x in audit['auto_resolvable']),
        human_layout_locations=sum(key(x) in resolved for x in audit['manual_review']))
    result.update(layout_ledger_sha256=ledger_hash,layout_review_id=human['review_id'])
    return result


def render_table(plan):
    return tsv(plan['operations'],list(plan['operations'][0]) if plan['operations'] else ['operation_id','layout_provenance'])
