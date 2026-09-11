"""Fail-closed, occurrence-bound dry-run plans. No apply/write-to-source API."""
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re

from .adoption import signature, tsv
from .analysis import id_sort, occurrence
from .gameplay import ACTION, build_inventory, normalized
from .human_reviews import validate
from .restoration import digest
from .scope import excerpt, layout_key
from . import context_overrides

RELATIONS={'adjudicated_name','same_name_shared_help','same_name_action_button',
           'same_name_action_help','same_action_and_exact_name_prefix'}
TOKEN=re.compile(r'\\[\s\S]|\\$|<[^>]*>|[<>]|%(?:\d+\$)?[-+#0 ]*(?:\d+|\*)?(?:\.(?:\d+|\*))?[hlLzjt]*[A-Za-z%]|%|\{[^}]*\}|[{}"\r\n\t]')


def tokens(value):
    return TOKEN.findall(value)


def read_audit(directory):
    directory=Path(directory)
    table=directory/'scope-audit.tsv'; meta=directory/'scope-metadata.json'
    with table.open(encoding='utf8',newline='') as stream:
        rows=[{k:json.loads(v) for k,v in r.items()} for r in csv.DictReader(stream,delimiter='\t')]
    return rows,json.loads(meta.read_text(encoding='utf8')),{
        table.name:hashlib.sha256(table.read_bytes()).hexdigest(),meta.name:hashlib.sha256(meta.read_bytes()).hexdigest()}


def location(row):
    return row.get('source_path'),row.get('source_line'),row.get('related_string_id')


def relation_valid(row,rec,en,inventory):
    relation=row['relation']; sid=row['related_string_id']; target=rec['string_id']
    expected=rec['expected_de_english']
    target_row=inventory.get(target,{})
    helps={e['help_id'] for e in target_row.get('evidence',[])}
    if relation=='adjudicated_name': return sid==target and en.value==expected
    if relation=='same_name_shared_help':
        return normalized(en.value)==normalized(expected) and bool(helps & {
            e['help_id'] for e in inventory.get(sid,{}).get('evidence',[])})
    if relation=='same_name_action_help':
        match=ACTION.match(en.value)
        return bool(match and normalized(match[2])==normalized(expected) and sid in helps)
    actions={e['action'] for e in target_row.get('evidence',[])}
    if relation=='same_name_action_button': return any(en.value==f'{a} {expected}' for a in actions)
    if relation=='same_action_and_exact_name_prefix':
        return any(re.match(r'^'+re.escape(a+' '+expected)+r'(?:$| \()',en.value) for a in actions)
    return False


def build_plan(data,ledger,rows,metadata,artifact_hashes=None):
    from .source_states import restore_scope, filter_plan
    original, before_rows, before_meta, states = restore_scope(data, ledger, rows, metadata)
    if states:
        return filter_plan(build_plan(original, ledger, before_rows, before_meta, artifact_hashes),
                           states, base_only=True)
    validate(ledger)
    direct=context_overrides.validate_scope(data,rows,metadata)
    direct_records={r['string_id']:r for r in direct['records']} if direct else {}
    records={r['string_id']:r for r in ledger['records']}
    required=[r for r in rows if r.get('scope_class')=='required']
    groups=defaultdict(list)
    for r in required: groups[location(r)].append(r)
    inventory={r['string_id']:r for r in build_inventory(data)['rows']}
    live_hashes={f.path:f.sha256 for d in data.values() for f in d.files}
    expected_hashes={f['path']:f['sha256'] for f in metadata['inputs']}
    ledger_hash=digest(json.dumps(ledger,ensure_ascii=False,sort_keys=True))
    global_errors=[]
    if metadata.get('ledger_sha256')!=ledger_hash: global_errors.append('ledger_hash_mismatch')
    for path,sha in expected_hashes.items():
        if not sha or live_hashes.get(path)!=sha: global_errors.append('source_hash_mismatch:'+path)
    valid_decisions={}
    for sid,rec in records.items():
        en=data['de_en'].resolved(sid)
        live_helps={e['help_id'] for e in inventory.get(sid,{}).get('evidence',[])}
        valid_decisions[sid]=(en is not None and en.value==rec['expected_de_english'] and
            signature(data,sid,rec['help_ids'])==rec['signature'] and live_helps==set(rec['help_ids']))
    operations=[]; blocked=[]; locations=[]
    for loc,requests in sorted(groups.items(),key=lambda item:(str(item[0][0]),item[0][1] or 0,id_sort(str(item[0][2])))):
        path,line,sid=loc; errors=list(global_errors); candidates=[]
        entries=[e for e in data['de_jp'].entries.get(sid,[]) if e.path==path and e.line==line]
        if not isinstance(line,int) or isinstance(line,bool) or line<1 or len(entries)!=1:
            errors.append('nonunique_or_missing_occurrence')
        entry=entries[0] if len(entries)==1 else None
        if entry and (entry.ambiguous or sid in data['de_jp'].invalid_ids): errors.append('malformed_occurrence')
        before=entry.value if entry else None
        for r in requests:
            is_direct=r['relation']==context_overrides.RELATION
            rec=(direct_records if is_direct else records).get(r.get('decision_string_id'))
            if rec is None:
                errors.append('unknown_decision'); continue
            if (not is_direct and not valid_decisions[rec['string_id']]) or r.get('decision_signature')!=rec['signature']:
                errors.append('decision_signature_mismatch')
            if r.get('effective_jp')!=rec['proposed_jp'] or r.get('effective_decision')!=rec['decision']:
                errors.append('canonical_translation_mismatch')
            if r.get('evidence_status')!='matches' or r.get('conflict'):
                errors.append('unapproved_or_conflicting_audit')
            if r.get('change_candidate') is not True or (not is_direct and (r.get('normalized_equal') is not False or r.get('normalized_equivalent'))):
                errors.append('not_a_required_change')
            if not r.get('source_sha256') or r['source_sha256']!=expected_hashes.get(path) or r['source_sha256']!=live_hashes.get(path):
                errors.append('occurrence_file_hash_mismatch')
            proof=r.get('english_source')
            en_entries=[e for e in data['de_en'].entries.get(sid,[]) if isinstance(proof,dict) and
                        occurrence(e)==proof and Path(e.path).name==Path(path or '').name]
            if len(en_entries)!=1 or en_entries[0].ambiguous or sid in data['de_en'].invalid_ids:
                errors.append('english_occurrence_not_unique')
            elif not is_direct and not relation_valid(r,rec,en_entries[0],inventory):
                errors.append('relation_evidence_mismatch')
            a,b=r.get('start'),r.get('end'); matched=r.get('matched_jp')
            if before is None or type(a)!=int or type(b)!=int or not 0<=a<b<=len(before):
                errors.append('invalid_or_missing_span'); continue
            if not isinstance(matched,str) or before[a:b]!=matched:
                errors.append('expected_current_span_mismatch'); continue
            # Phase 1C keeps excerpts; the matching full-file SHA authenticates the entire
            # original value, and this comparison also checks the saved review context.
            if r.get('related_jp')!=excerpt(before,a): errors.append('expected_current_value_mismatch')
            replacement=rec['proposed_jp']
            if not is_direct and layout_key(matched)==layout_key(replacement): errors.append('normalized_equivalent')
            if r.get('relation') in ('adjudicated_name','same_name_shared_help') and (a,b)!=(0,len(before)):
                errors.append('name_span_not_full_value')
            if r.get('relation')=='same_name_action_help':
                h=re.match(r'^\s*<b>(.*?)<b>',before)
                if not h or (a,b)!=h.span(1): errors.append('help_heading_span_mismatch')
            if r.get('relation') in ('same_name_action_button','same_action_and_exact_name_prefix'):
                boundaries=[before.index(c) for c in ('(','（') if c in before]
                if boundaries and b>min(boundaries): errors.append('button_span_outside_title')
                aliases={replacement}
                current=data['de_jp'].resolved(rec['string_id'])
                if current: aliases.add(current.value)
                for h in rec['help_ids']:
                    text=data['de_jp'].resolved(h)
                    heading=re.match(r'^\s*<b>(.*?)<b>',text.value) if text else None
                    if heading: aliases.add(heading[1])
                if matched not in aliases: errors.append('button_span_not_a_known_name')
            after=before[:a]+replacement+before[b:]
            if tokens(before)!=tokens(after): errors.append('technical_structure_changed')
            candidates.append(dict(start=a,end=b,matched=matched,replacement=replacement,request=r))
        # Quarantine the entire location when any requested edit is unsafe.
        by_span=defaultdict(list)
        for c in candidates: by_span[(c['start'],c['end'])].append(c)
        spans=sorted(by_span)
        for span,items in by_span.items():
            if len({c['replacement'] for c in items})>1: errors.append('replacement_conflict')
        for i,span in enumerate(spans):
            if i and span[0]<spans[i-1][1]: errors.append('overlapping_span_conflict')
        if errors:
            blocked.append(dict(source_path=path,source_line=line,string_id=sid,
                decision_string_ids=sorted({r['decision_string_id'] for r in requests},key=id_sort),
                candidate_count=len(requests),reasons=sorted(set(errors)),
                requested_spans=[dict(start=r.get('start'),end=r.get('end'),matched=r.get('matched_jp'),replacement=r.get('effective_jp')) for r in requests]))
            continue
        final=before
        for a,b in reversed(spans): final=final[:a]+by_span[(a,b)][0]['replacement']+final[b:]
        if tokens(before)!=tokens(final):
            blocked.append(dict(source_path=path,source_line=line,string_id=sid,candidate_count=len(requests),
                                reasons=['combined_technical_structure_changed'])); continue
        operation_ids=[]
        for a,b in spans:
            items=by_span[(a,b)]; replacement=items[0]['replacement']
            proofs=[dict(decision_string_id=c['request']['decision_string_id'],decision_signature=c['request']['decision_signature'],
                         relation=c['request']['relation'],english_source=c['request']['english_source']) for c in items]
            for proof,item in zip(proofs,items):
                if item['request']['relation']==context_overrides.RELATION:
                    proof.update(context_signature=item['request']['context_signature'],context_ledger_sha256=metadata['context_override_ledger']['sha256'])
            proofs=sorted({json.dumps(p,sort_keys=True):p for p in proofs}.values(),key=lambda p:(id_sort(p['decision_string_id']),p['relation']))
            opid=digest(json.dumps([path,line,sid,a,b,replacement],ensure_ascii=False))[:20]
            operation_ids.append(opid)
            operations.append(dict(operation_id=opid,source_path=path,source_line=line,string_id=sid,
                before=before,after=before[:a]+replacement+before[b:],expected_source_sha256=expected_hashes[path],
                expected_value_sha256=digest(before),matched_span=[a,b],matched=before[a:b],replacement=replacement,
                replacement_type='full_value' if (a,b)==(0,len(before)) else 'span',
                decision_string_ids=sorted({p['decision_string_id'] for p in proofs},key=id_sort),
                relations=sorted({p['relation'] for p in proofs}),evidence=proofs,
                merged_candidate_count=len(items),duplicate_dataset_id=len(data['de_jp'].entries[sid])>1))
        locations.append(dict(source_path=path,source_line=line,string_id=sid,before=before,after=final,
                              expected_source_sha256=expected_hashes[path],expected_value_sha256=digest(before),operation_ids=operation_ids))
    stats=dict(required_input_candidates=len(required),excluded_scope_rows=len(rows)-len(required),
        unique_source_locations=len(locations),unique_string_ids=len({o['string_id'] for o in operations}),
        patch_operations=len(operations),full_value_replacements=sum(o['replacement_type']=='full_value' for o in operations),
        span_replacements=sum(o['replacement_type']=='span' for o in operations),
        accepted_candidate_rows=sum(o['merged_candidate_count'] for o in operations),
        blocked_locations=len(blocked),blocked_candidate_rows=sum(b['candidate_count'] for b in blocked),
        conflicts=sum(any('conflict' in reason for reason in b['reasons']) for b in blocked),
        blocked_reasons=dict(sorted(Counter(reason for b in blocked for reason in b['reasons']).items())),
        duplicate_id_patch_operations=sum(o['duplicate_dataset_id'] for o in operations),
        per_decision=dict(sorted(Counter(s for o in operations for s in o['decision_string_ids']).items(),key=lambda item:id_sort(item[0]))),
        per_relation=dict(sorted(Counter(r for o in operations for r in o['relations']).items())))
    return dict(schema_version=1,mode='dry_run_only',statistics=stats,operations=operations,locations=locations,blocked=blocked,
                ledger_sha256=ledger_hash,audit_artifact_hashes=artifact_hashes or {},source_inventory=metadata['inputs'])


def render_tsv(plan):
    return tsv(plan['operations'],['operation_id','source_path','source_line','string_id','before','after',
        'expected_source_sha256','expected_value_sha256','matched_span','matched','replacement','replacement_type',
        'decision_string_ids','relations','evidence','merged_candidate_count','duplicate_dataset_id'])


def render_summary(plan):
    s=plan['statistics']
    lines=['# Phase 1D dry-run patch plan','',
           '公式source・人間裁定・Mod用翻訳は未変更。apply機能はない。before/afterは解析済み保存値であり、ファイル全体ではない。', '',
           '| 集計 | 件数 |','|---|---:|']
    lines += [f'| {k} | {v} |' for k,v in s.items() if not isinstance(v,dict)]
    lines += ['', '## Blockedの理由', '', '```json',json.dumps(s['blocked_reasons'],ensure_ascii=False,indent=2),'```', '',
              'レイアウト改行等が置換span内にある場合、その配置を推測せずtechnical_structure_changedとして保留する。',
              '重複IDはpath/line/IDの一意な出現で指定する。他出現への暗黙の適用はしない。',
              '同じspanの同一置換は統合。異なる置換・重なるspan・検証失敗は同じ出現位置全体をblockedにする。', '',
              '## Relation別operation数', '', '```json',json.dumps(s['per_relation'],ensure_ascii=False,indent=2),'```', '',
              '## Decision別operation数', '', '```json',json.dumps(s['per_decision'],ensure_ascii=False,indent=2),'```', '',
              '集計のdecision/relationは1 operationが複数の根拠を持つため、合計がoperation数を超える場合がある。',
              '複数の非重複spanがある場合、operations.afterは単独編集後、locations.afterは全編集後の値。全spanは共通のbeforeに対するUnicode文字位置。', '',
              '正本SHA-256: '+plan['ledger_sha256'],'']
    return '\n'.join(lines)
