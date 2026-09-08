"""Read-only diagnosis and conservative layout proposals; never an apply API."""
from collections import defaultdict
import json
import re

from .adoption import tsv
from .patch_plan import build_plan, location, tokens, TOKEN
from .scope import layout_key

CATEGORIES = ('layout_whitespace', 'markup_tag', 'placeholder', 'nonunique_span',
              'expected_current_value', 'source_hash', 'duplicate_id', 'overlap', 'other')
LAYOUT = {r'\n', r'\r', r'\t', '\n', '\r', '\t'}


def token_parts(value):
    """Separate recognized game tokens without decoding or mutating stored values."""
    result = dict(layout=[], markup=[], placeholder=[], other=[])
    for token in tokens(value):
        kind = ('layout' if token in LAYOUT else 'placeholder' if token.startswith(('%', '{'))
                or token in ('<cost>', '<hp>', '<attack>', '<armor>') else
                'markup' if token.startswith('<') or token == '>' else 'other')
        result[kind].append(token)
    return result


def layout_proposal(current, canonical):
    """One preserved separator at a unique, anchored canonical word boundary.

    No character-offset transplantation, dictionary, fuzzy matching, or invented
    compound boundary. Changed components on both sides remain manual review.
    """
    if layout_key(current) == layout_key(canonical):
        return None, 'normalized_equivalent: no change needed'
    matches = list(TOKEN.finditer(current))
    if len(matches) != 1 or matches[0][0] not in LAYOUT or tokens(canonical):
        return None, 'requires one layout token and no other technical token inside name'
    m = matches[0]
    left, right = current[:m.start()].rstrip(' '), current[m.end():].lstrip(' ')
    if not left or not right:
        return None, 'empty name component'
    separator = current[len(left):len(current)-len(right)]
    candidates = []
    for boundary in re.finditer(r' +', canonical):
        a, b = canonical[:boundary.start()], canonical[boundary.end():]
        anchors = [side for side, old in ((a, left), (b, right)) if side == old and len(side) >= 2]
        if a and b and anchors:
            proposed = a + separator + b
            if tokens(current) == tokens(proposed) and layout_key(proposed) == layout_key(canonical):
                candidates.append((proposed, anchors))
    if len(candidates) != 1:
        return None, 'no unique canonical space boundary with an unchanged complete component'
    proposed, anchors = candidates[0]
    return proposed, 'explicit canonical space boundary; unchanged component: ' + ' / '.join(anchors)


def causes(block, requests, duplicate=False):
    result = set()
    for reason in block['reasons']:
        if reason in ('technical_structure_changed', 'combined_technical_structure_changed'):
            for row in requests:
                before, after = token_parts(row.get('matched_jp') or ''), token_parts(row.get('effective_jp') or '')
                for kind, category in [('layout','layout_whitespace'), ('markup','markup_tag'),
                                       ('placeholder','placeholder'), ('other','other')]:
                    if before[kind] != after[kind]: result.add(category)
            if not result: result.add('other')
        elif 'hash_mismatch' in reason and 'ledger' not in reason: result.add('source_hash')
        elif reason.startswith('expected_current'): result.add('expected_current_value')
        elif reason == 'overlapping_span_conflict': result.add('overlap')
        elif reason in ('nonunique_or_missing_occurrence', 'english_occurrence_not_unique'):
            result.add('duplicate_id' if duplicate else 'nonunique_span')
        elif 'span' in reason: result.add('nonunique_span' if 'unique' in reason else 'other')
        else: result.add('other')
    return sorted(result)


def audit_blocked(data, ledger, rows, metadata, artifact_hashes=None, expected_plan=None, expected_blocked=None):
    # Repeat all Phase 1D validations, including signatures, hashes, occurrence,
    # current context, relation, span and conflict checks. Never relax those gates.
    plan = build_plan(data, ledger, rows, metadata, artifact_hashes)
    if expected_plan is not None and {k:v for k,v in plan.items() if k!='blocked'} != expected_plan:
        raise ValueError('Saved patch plan differs from freshly validated inputs; regenerate separately')
    if expected_blocked is not None and plan['blocked'] != expected_blocked:
        raise ValueError('Saved blocked report differs from freshly validated inputs')
    groups = defaultdict(list)
    for row in rows:
        if row.get('scope_class') == 'required': groups[location(row)].append(row)
    table=[]; auto=[]; manual=[]
    counts={c:dict(source_locations=0,candidates=0) for c in CATEGORIES}
    for block in plan['blocked']:
        path,line,sid=block['source_path'],block['source_line'],block['string_id']
        requests=groups[(path,line,sid)]
        entries=[e for e in data['de_jp'].entries.get(sid,[]) if e.path==path and e.line==line]
        current=entries[0].value if len(entries)==1 else None
        duplicate=len(data['de_jp'].entries.get(sid,[]))>1
        categories=causes(block,requests,duplicate)
        for c in categories:
            counts[c]['source_locations']+=1; counts[c]['candidates']+=len(requests)
        records=[]
        for row in requests:
            proposed=None; reason='non-layout safety gate failed; manual review required'
            if block['reasons']==['technical_structure_changed'] and categories==['layout_whitespace']:
                proposed,reason=layout_proposal(row['matched_jp'],row['effective_jp'])
            a,b=row.get('start'),row.get('end')
            after=current[:a]+proposed+current[b:] if proposed is not None and current is not None else None
            if after is not None and tokens(current)!=tokens(after):
                proposed=after=None; reason='full-value token sequence changed'
            records.append(dict(string_id=sid,source_path=path,source_line=line,current=current,
                english=row['related_en'],
                canonical=row['effective_jp'],proposed_replacement=proposed,proposed_after=after,
                matched_span=[a,b],matched=row.get('matched_jp'),blocked_reason=block['reasons'],
                cause_categories=categories,resolution_class='auto_resolvable' if proposed is not None else 'manual_review',
                resolution_reason=reason,decision_string_id=row['decision_string_id'],
                decision_signature=row['decision_signature'],relation=row['relation'],
                source_sha256=row['source_sha256'],english_source=row.get('english_source'),
                duplicate_dataset_id=duplicate,tokens_before=tokens(current or ''),
                tokens_after=tokens(after) if after is not None else None))
        edits={(tuple(r['matched_span']),r['proposed_replacement']) for r in records if r['proposed_replacement'] is not None}
        spans=sorted(edits)
        conflict=any(spans[i][0][0]<spans[i-1][0][1] for i in range(1,len(spans)))
        safe=all(r['resolution_class']=='auto_resolvable' for r in records) and not conflict
        final=current
        if safe:
            for (a,b),replacement in reversed(spans): final=final[:a]+replacement+final[b:]
            safe=tokens(current)==tokens(final)
        if not safe:
            for r in records:
                if r['resolution_class']=='auto_resolvable':
                    r.update(resolution_class='manual_review',resolution_reason='entire occurrence quarantined: unresolved or conflicting request',
                             proposed_replacement=None,proposed_after=None,tokens_after=None)
        item=dict(source_path=path,source_line=line,string_id=sid,candidate_count=len(requests),
                  operation_count=len(edits) if safe else 0,current=current,proposed_after=final if safe else None,
                  causes=categories,requests=records)
        (auto if safe else manual).append(item); table.extend(records)
    stats=dict(current_operations=len(plan['operations']),blocked_locations=len(plan['blocked']),
        blocked_candidates=len(table),cause_counts=counts,auto_resolvable_locations=len(auto),
        auto_resolvable_candidates=sum(x['candidate_count'] for x in auto),
        additional_operations=sum(x['operation_count'] for x in auto),
        simulated_operations=len(plan['operations'])+sum(x['operation_count'] for x in auto),
        manual_review_locations=len(manual),manual_review_candidates=sum(x['candidate_count'] for x in manual))
    return dict(mode='dry_run_simulation_only',statistics=stats,rows=table,auto_resolvable=auto,manual_review=manual,
                ledger_sha256=plan['ledger_sha256'],audit_artifact_hashes=plan['audit_artifact_hashes'])


def render_table(result):
    return tsv(result['rows'],['string_id','source_path','source_line','english','current','canonical',
        'proposed_replacement','proposed_after','matched_span','matched','blocked_reason','cause_categories',
        'resolution_class','resolution_reason','decision_string_id','decision_signature','relation','source_sha256',
        'english_source','duplicate_dataset_id','tokens_before','tokens_after'])


def json_artifacts(result):
    """Objects passed directly to the standard serializer, never JSON templates."""
    shared={k:v for k,v in result.items() if k in
            ('mode','statistics','ledger_sha256','audit_artifact_hashes')}
    return {name: shared | {'locations':result[key]} for name,key in
            [('auto-resolvable.json','auto_resolvable'),('manual-review.json','manual_review')]}


def serialize_json(value):
    # ASCII is a UTF-8 subset. Escapes preserve Unicode codepoints exactly and
    # avoid Windows PowerShell 5.1's ANSI fallback for BOM-less UTF-8 files.
    return json.dumps(value,ensure_ascii=True,allow_nan=False,indent=2)


def load_json(path):
    def reject_constant(value):
        raise ValueError('Non-JSON constant: '+value)
    def unique_object(pairs):
        result={}
        for key,value in pairs:
            if key in result: raise ValueError('Duplicate JSON key: '+key)
            result[key]=value
        return result
    with path.open(encoding='utf-8') as stream:
        return json.load(stream,parse_constant=reject_constant,object_pairs_hook=unique_object)


def verify_json(path,expected):
    actual=load_json(path)
    if actual!=expected:
        raise ValueError('JSON artifact round-trip mismatch: '+str(path))


def render_manual_review(artifact):
    """Human-readable table from the saved artifact; no source reload or decisions."""
    def cell(value):
        return str(value).replace('\r',r'\r').replace('\n',r'\n').replace('|',r'\|')
    lines=['| String ID | English | Current Japanese | Canonical Japanese | Reason |',
           '|---|---|---|---|---|']
    for item in artifact['locations']:
        requests=item['requests']
        canonical=' / '.join(dict.fromkeys(r['canonical'] for r in requests))
        reason=' / '.join(dict.fromkeys(r['resolution_reason'] for r in requests))
        if reason=='no unique canonical space boundary with an unchanged complete component':
            reason=('採用訳に明示的な語区切りなし' if all(' ' not in r['canonical'] for r in requests)
                    else '構成要素に基づく改行位置を一意に確定できない')
        english=' / '.join(dict.fromkeys(r['english'] for r in requests))
        lines.append('| '+' | '.join(cell(v) for v in (item['string_id'],english,item['current'],canonical,reason))+' |')
    return '\n'.join(lines)+'\n'


def render_summary(result):
    s=result['statistics']
    lines=['# Phase 1D blocked audit', '', 'Dry-run only. Source, human decisions and original patch plan are unchanged.', '',
           '| Metric | Count |','|---|---:|']
    lines += [f'| {k} | {v} |' for k,v in s.items() if k!='cause_counts']
    lines += ['', '| Cause | Source locations | Candidates |','|---|---:|---:|']
    lines += [f'| {k} | {v["source_locations"]} | {v["candidates"]} |' for k,v in s['cause_counts'].items()]
    lines += ['', 'Causes can overlap; candidate counts include all requests quarantined at each affected location.', '',
        '## Resolution rule', '',
        'Only a single layout token at a unique canonical space boundary with an unchanged whole component (at least two characters) is transferable. '
        'No inferred compound splits or character-offset transfer. The complete ordered token sequence and normalized canonical value must match. '
        'All Phase 1D validations are repeated before proposing anything. Multiple requests are merged by occurrence and span; any unresolved request quarantines the location.', '',
        'Auto-resolvable means structurally reproducible under this conservative rule; it does not prove the new label fits the game UI. Visual testing remains necessary.', '',
        '## Manual review locations', '']
    lines += [f'- {x["string_id"]} ({x["source_path"]}:{x["source_line"]}): '+x['requests'][0]['resolution_reason'] for x in result['manual_review']]
    return '\n'.join(lines)+'\n'
