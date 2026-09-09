"""Phase 2A-1: evidence-bound concept review, without translation decisions."""
from collections import Counter, defaultdict
from dataclasses import asdict
import json
from pathlib import Path
import re

from .analysis import id_sort, occurrence
from .adoption import tsv
from .duplicate_audit import audit_duplicates
from .gameplay import ACTION, ORDER, build_inventory, cell, jp_key, load_rules, normalized, short_label
from .restoration import digest
from .scope import layout_key

VERSION = 'phase2a-1/2'


def identity(kind, value):
    return kind + '-' + digest(json.dumps(value, sort_keys=True, ensure_ascii=False))[:20]


def relative(entry):
    # Dataset prefix is removed; nested directories are significant.
    return entry.path.split('/', 1)[1]


def pair(data, sid):
    en, jp = (data[n].resolved(sid) for n in ('de_en', 'de_jp'))
    if en is None or jp is None:
        return en, jp, 'missing_or_ambiguous_language_pair'
    if relative(en) != relative(jp):
        return en, jp, 'different_language_file'
    return en, jp, None


def difference(a, b):
    """No spelling key determines concept identity or a preferred translation."""
    if a == b:
        return ['literal_equal']
    tags = []
    # Tokenize escapes in pairs: a literal escaped backslash is not a newline.
    layout = lambda value: [m[0] for m in re.finditer(r'\\[\s\S]|\s+', value)
                            if m[0].isspace() or m[0] in ('\\n', '\\r', '\\t')]
    if layout(a) != layout(b):
        tags.append('layout_difference')
    tags.append('layout_only' if layout_key(a) == layout_key(b) else 'wording_difference')
    return tags


def review_fields():
    return dict(review_status='pending', reviewer=None, reviewed_on=None,
                reviewer_decision=None, reviewer_japanese=None, reviewer_scope=None,
                reviewer_notes=None)


def english_label_forms(value):
    """Conservative lookup forms for unresolved candidates, never identity proof."""
    forms = {value}
    if re.fullmatch(r"[A-Za-z][A-Za-z '\-]*", value):
        if re.search(r'[^aeiou]y$', value, re.I):
            forms.add(value[:-1] + 'ies')
        elif re.search(r'(?:s|x|z|ch|sh)$', value, re.I):
            forms.add(value + 'es')
        else:
            forms.add(value + 's')
    return forms


def build_audit(data, rules=None):
    rules = load_rules()[0] if rules is None else rules
    inv = build_inventory(data, rules)
    by_name = {r['string_id']: r for r in inv['rows']}
    inputs = {f.path: f.sha256 for d in data.values() for f in d.files}
    concepts, occurrences, relations, unresolved = {}, {}, [], {}
    memberships = defaultdict(set)

    def problem(kind, sid, reasons, candidates=()):
        uid = identity('unresolved', [kind, sid])
        item = unresolved.setdefault(uid, dict(unresolved_id=uid, kind=kind,
                    string_id=sid, reasons=[], candidate_concept_ids=[], **review_fields()))
        item['reasons'] = sorted(set(item['reasons']) | set(reasons))
        item['candidate_concept_ids'] = sorted(set(item['candidate_concept_ids']) | set(candidates))
        # Positions/hashes only: unresolved text may be narrative or malformed.
        item['sources'] = {n: [dict(**occurrence(e), value_sha256=digest(e.value))
                              for e in data[n].entries.get(sid, [])]
                           for n in ('de_en', 'de_jp')}
        return uid

    def add_occurrence(cid, sid, role, en, jp, en_span, jp_span, basis):
        oid = identity('occ', [cid, sid, role, en.path, en.line, en_span])
        en_term = en.value[slice(*en_span)]
        jp_term = jp.value[slice(*jp_span)] if jp_span is not None else None
        occurrences[oid] = dict(occurrence_id=oid, concept_id=cid, string_id=sid,
            role=role, en_term=en_term, jp_term=jp_term,
            alignment='structural' if jp_span is not None else 'unresolved',
            en_source=occurrence(en), jp_source=occurrence(jp),
            en_span=en_span, jp_span=jp_span,
            en_value_sha256=digest(en.value), jp_value_sha256=digest(jp.value),
            en_file_sha256=inputs[en.path], jp_file_sha256=inputs[jp.path], basis=basis)
        concepts[cid]['occurrence_ids'].append(oid)
        memberships[sid].add(cid)
        return oid

    # A Help occurrence is the structural anchor, never an English-word bucket.
    anchors = defaultdict(list)
    for row in inv['rows']:
        sid = row['string_id']
        en, jp, error = pair(data, sid)
        valid = []
        for ev in row['evidence']:
            he, hj, help_error = pair(data, ev['help_id'])
            match = ACTION.match(he.value) if he else None
            heading = normalized(match[2]) if match else None
            heading = rules.get('heading_aliases', {}).get(heading, heading)
            accepted = (not error and not help_error and match
                        and row['category'] != 'unknown'
                        and row['content_family'] != 'review-needed'
                        and ev['relation'] == 'verified_offset_and_label'
                        and he.path == en.path == ev['path'] and he.line == ev['line']
                        and normalized(en.value) == heading
                        and ev['category'] == row['category'])
            key = (row['content_family'], en.path if en else ev['path'],
                   row['category'], ev['help_id'])
            cid = identity('concept', key)
            relations.append(dict(relation_id=identity('rel', [sid, ev]), name_id=sid,
                help_id=ev['help_id'], candidate_concept_id=cid,
                status='supported' if accepted else 'candidate', evidence=ev))
            if accepted:
                valid.append((key, row, en, jp, he, hj, match))
        # Do not bridge multiple Help concepts through a possibly reused label.
        if len({v[0] for v in valid}) != 1:
            reason = error or ('multiple_structural_anchors' if valid else 'no_unique_structural_anchor')
            problem('name_relation', sid, [reason], [identity('concept', v[0]) for v in valid])
            for rel in relations:
                if rel['name_id'] == sid and rel['status'] == 'supported':
                    rel['status'] = 'candidate'
            continue
        anchors[valid[0][0]].append(valid[0])

    for key, items in sorted(anchors.items()):
        cid = identity('concept', key)
        _, _, _, _, he, hj, match = items[0]
        concepts[cid] = dict(concept_id=cid, content_family=key[0], source_path=key[1],
            category=key[2], anchor_help_id=key[3], action=match[1],
            english=normalized(match[2]), identity_status='structural_source_evidence',
            runtime_identity_verified=False, occurrence_ids=[], **review_fields())
        for _, row, en, jp, *_ in items:
            add_occurrence(cid, row['string_id'], row['label_role'], en, jp,
                           [0, len(en.value)], [0, len(jp.value)], 'verified_offset_and_label')
        title = re.match(r'^\s*<b>(.*?)<b>', hj.value)
        span = list(title.span(1)) if title and title[1] and len(title[1]) <= 160 else None
        add_occurrence(cid, he.string_id, 'help_heading', he, hj,
                       list(match.span(2)), span, 'anchored_action_help')
        if span is None:
            problem('help_heading', he.string_id, ['nonstandard_japanese_heading'], [cid])

    # Reviewed structural seeds cover named gameplay objects without production Help anchors.
    # The rules assert source roles and identity only; Japanese values are never seed evidence.
    for seed in sorted(rules.get('concept_seeds', []), key=lambda s: s['seed_id']):
        sid = seed['name_id']
        en, jp, error = pair(data, sid)
        reasons = []
        if error:
            reasons.append(error)
        if en and relative(en) != seed['source_path']:
            reasons.append('seed_source_path_mismatch')
        if en and not short_label(en.value):
            reasons.append('seed_not_short_label')
        if sid in by_name:
            reasons.append('seed_already_in_structural_inventory')
        if seed.get('confidence') != 'reviewed_structural':
            reasons.append('seed_confidence_not_supported')
        evidence = dict(seed_id=seed['seed_id'], relation=seed['relation_kind'],
                        confidence=seed['confidence'], provenance=seed['provenance'],
                        source_path=seed['source_path'])
        key = (seed['content_family'], en.path if en else seed['source_path'],
               seed['category'], 'seed:' + seed['seed_id'])
        cid = identity('concept', key)
        relations.append(dict(relation_id=identity('rel', [sid, evidence]), name_id=sid,
            help_id=None, candidate_concept_id=cid,
            status='candidate' if reasons else 'supported', evidence=evidence))
        if reasons:
            problem('concept_seed', sid, reasons, [cid])
            continue
        concepts[cid] = dict(concept_id=cid, content_family=key[0], source_path=key[1],
            category=key[2], anchor_help_id=None, action=None, english=normalized(en.value),
            identity_status='reviewed_structural_seed', runtime_identity_verified=False,
            seed_evidence=evidence, occurrence_ids=[], **review_fields())
        add_occurrence(cid, sid, seed.get('role', 'full_name'), en, jp,
                       [0, len(en.value)], [0, len(jp.value)], seed['relation_kind'])

    # Only exact action/name displays (optionally one parenthesized effect tail).
    button_index = defaultdict(set)
    for cid, c in concepts.items():
        if c['action'] is None:
            continue
        names = {normalized(occurrences[o]['en_term']) for o in c['occurrence_ids']}
        for name in names:
            button_index[(c['source_path'], c['action'] + ' ' + name)].add(cid)
    for sid in sorted(data['de_en'].entries, key=id_sort):
        for entry in data['de_en'].entries[sid]:
            if ACTION.match(entry.value):
                continue
            # No general prose scan or inferred ID arithmetic.
            prefix = entry.value.split(' (', 1)[0]
            if entry.value != prefix and (not entry.value.endswith(')') or '\\n' in entry.value):
                continue
            targets = button_index.get((entry.path, prefix), set())
            if not targets:
                continue
            en, jp, error = pair(data, sid)
            if error or len(targets) != 1:
                problem('action_display', sid, [error or 'multiple_concept_actions'], targets)
                continue
            cid = next(iter(targets)); c = concepts[cid]
            he, hj, _ = pair(data, c['anchor_help_id'])
            title = re.match(r'^\s*<b>(.*?)<b>', hj.value)
            span = None
            if title:
                # Derive the operation suffix from this very Help, not a translation dictionary.
                suffix = re.split(r' [（(]|\\n', hj.value[title.end():], maxsplit=1)[0].strip()
                button = re.split(r' [（(]', jp.value, maxsplit=1)[0].strip()
                if suffix and len(suffix) <= 40 and '<' not in suffix and button.endswith(suffix):
                    term = button[:-len(suffix)].rstrip()
                    if term and len(term) <= 160 and not re.search(r'[<>%{}]|\\', term):
                        start = len(jp.value) - len(jp.value.lstrip())
                        span = [start, start + len(term)]
            add_occurrence(cid, sid, 'action_display', en, jp,
                           [len(c['action']) + 1, len(prefix)], span, 'same_file_exact_action_and_name')
            if span is None:
                problem('action_display', sid, ['japanese_operation_structure_unresolved'], [cid])

    # Keep inventory-external, name-like exact/inflected labels reviewable. These are
    # candidate links only: spelling never creates concept membership.
    candidate_coverage = {}
    label_index = defaultdict(set)
    for cid, c in concepts.items():
        for form in english_label_forms(c['english']):
            label_index[(c['source_path'], form.casefold())].add(cid)
    for sid in sorted(data['de_en'].entries, key=id_sort):
        if sid in by_name or memberships[sid]:
            continue
        en, jp, error = pair(data, sid)
        if error or not en or ACTION.match(en.value) or not short_label(en.value):
            continue
        candidate_label = normalized(en.value)
        candidates = label_index.get((en.path, candidate_label.casefold()), set())
        relation_kind = None
        operation = re.fullmatch(r'(Create|Train|Build|Research|Upgrade to|Advance to|Drop) (.+)',
                                 candidate_label)
        if not candidates and operation:
            candidates = label_index.get((en.path, operation[2].casefold()), set())
            if candidates:
                relation_kind = 'same_file_direct_operation_candidate'
        if not candidates:
            continue
        if relation_kind is None:
            exact = any(concepts[c]['english'].casefold() == candidate_label.casefold() for c in candidates)
            relation_kind = 'same_file_exact_label_candidate' if exact else 'same_file_inflected_label_candidate'
        problem('unclassified_name_candidate', sid,
                ['outside_structural_inventory', relation_kind], candidates)
        candidate_coverage[sid] = dict(string_id=sid, state='not_classified',
            concept_ids=[], candidate_concept_ids=sorted(candidates), inventory_role=None,
            basis=relation_kind)
        for cid in sorted(candidates):
            c = concepts[cid]
            evidence = dict(relation=relation_kind, path=en.path, line=en.line,
                            candidate_english=candidate_label)
            relations.append(dict(relation_id=identity('rel', [sid, cid, evidence]),
                name_id=sid, help_id=c['anchor_help_id'], candidate_concept_id=cid,
                status='candidate', evidence=evidence))

    # Preserve all inventory links; candidate references never imply membership.
    help_concepts = defaultdict(set)
    for cid, c in concepts.items():
        if c['anchor_help_id'] is not None:
            help_concepts[(c['anchor_help_id'], c['source_path'], c['category'])].add(cid)
    for rel in relations:
        cid = rel.pop('candidate_concept_id')
        if cid not in concepts and rel.get('help_id') is not None:
            matches = help_concepts.get((rel['help_id'], rel['evidence'].get('path'),
                                         rel['evidence'].get('category')), set())
            cid = next(iter(matches)) if len(matches) == 1 else cid
        rel['concept_id'] = cid if cid in concepts else None
        if rel['status'] == 'supported' and rel['concept_id'] is None:
            raise ValueError('Supported relation has no concept')
    # Candidate relations are now navigable without reverse-searching relations.json.
    for u in unresolved.values():
        linked = {r['concept_id'] for r in relations
                  if r.get('name_id') == u['string_id'] and r['status'] == 'candidate'
                  and r.get('concept_id') is not None}
        u['candidate_concept_ids'] = sorted(set(u['candidate_concept_ids']) | linked)
    for oid, o in occurrences.items():
        if o['role'] in ('help_heading', 'action_display'):
            relations.append(dict(relation_id=identity('rel', oid), occurrence_id=oid,
                concept_id=o['concept_id'], status='supported', evidence={'relation': o['basis']}))

    findings = []

    def finding(kind, cids, oids, detail=None):
        cids, oids = sorted(set(cids)), sorted(set(oids))
        fid = identity('finding', [kind, cids, oids, detail])
        findings.append(dict(finding_id=fid, kind=kind, concept_ids=cids, occurrence_ids=oids,
            detail=detail, evidence_signature=identity('evidence', [VERSION, inv['rules_sha256'], detail] + [concepts[c] for c in cids] +
                                                    [occurrences[o] for o in oids]), **review_fields()))

    for cid, c in concepts.items():
        c['occurrence_ids'].sort()
        os = [occurrences[o] for o in c['occurrence_ids'] if occurrences[o]['jp_term'] is not None]
        labels = [o for o in os if o['role'] in ('full_name', 'compact_name')]
        headings = [o for o in os if o['role'] == 'help_heading']
        if len({layout_key(o['jp_term']) for o in os}) > 1:
            pairs = [dict(left=a['occurrence_id'], right=b['occurrence_id'],
                          differences=difference(a['jp_term'], b['jp_term']))
                     for i, a in enumerate(os) for b in os[i+1:] if a['jp_term'] != b['jp_term']]
            finding('concept_jp_variation', [cid], [o['occurrence_id'] for o in os], pairs)
        elif len({o['jp_term'] for o in os}) > 1:
            finding('layout_only_variation', [cid], [o['occurrence_id'] for o in os])
        if headings and any(layout_key(a['jp_term']) != layout_key(b['jp_term']) for a in labels for b in headings):
            finding('name_help_mismatch', [cid], [o['occurrence_id'] for o in labels + headings])

    collision_groups = defaultdict(list)
    for o in occurrences.values():
        if o['jp_term'] is not None:
            c = concepts[o['concept_id']]
            collision_groups[(c['content_family'], c['source_path'], c['category'], layout_key(o['jp_term']))].append(o)
    for os in collision_groups.values():
        cids = {o['concept_id'] for o in os}
        if len({concepts[c]['english'] for c in cids}) > 1:
            finding('jp_collision_candidate', cids, [o['occurrence_id'] for o in os])

    history = []
    for sid in sorted({o['string_id'] for o in occurrences.values()
                       if o['role'] in ('full_name', 'compact_name')}, key=id_sort):
        cells = {n: cell(data.get(n), sid) for n in ORDER}
        # Only names are reproduced; historical reused IDs can hold long narrative text.
        for entry_cell in cells.values():
            for e in entry_cell['occurrences']:
                value = e.pop('value')
                e.update(value_sha256=digest(value), value_excerpt=value[:160], excerpted=len(value)>160)
        old_en, new_en = data['hd_en'].resolved(sid), data['de_en'].resolved(sid)
        old_jp, new_jp = data['hd_jp'].resolved(sid), data['de_jp'].resolved(sid)
        history.append(dict(string_id=sid, concept_ids=sorted(memberships[sid]), datasets=cells,
            continuity='unresolved' if old_en is None or new_en is None else
                       'english_literal_equal_not_identity_proof' if old_en.value == new_en.value else
                       'english_changed_requires_review', legacy_english_available=False))
        legacy = [data[n].resolved(sid) for n in ('aok_jp', 'aoc_jp') if data[n].resolved(sid)]
        unambiguous = all(cells[n]['state'] != 'ambiguous' for n in ORDER)
        supported_history = (old_en and new_en and old_jp and new_jp and unambiguous
            and old_en.value == new_en.value and old_jp.value != new_jp.value
            and legacy and all(e.value == old_jp.value for e in legacy)
            and short_label(old_en.value) and short_label(new_en.value))
        if supported_history:
            oids = [o['occurrence_id'] for o in occurrences.values()
                    if o['string_id'] == sid and o['role'] in ('full_name', 'compact_name')]
            detail = dict(comparison='hd_to_de', english_unchanged=True,
                hd_english=old_en.value, hd_japanese=old_jp.value,
                de_english=new_en.value, de_japanese=new_jp.value,
                legacy_japanese_generations=[n for n in ('aok_jp', 'aoc_jp')
                    if data[n].resolved(sid) and data[n].resolved(sid).value == old_jp.value],
                interpretation='review_candidate_only_no_preferred_translation')
            finding('historical_jp_variation', memberships[sid], oids, detail)

    # Exact reconciliation with Phase 1A's 72 groups, without adopting that grouping as identity.
    baseline = defaultdict(list)
    for r in inv['rows']:
        e, j, error = pair(data, r['string_id'])
        if e and j and r['category'] != 'unknown' and r['content_family'] != 'review-needed':
            baseline[(r['content_family'], e.path, r['category'], normalized(e.value))].append((r, j))
    baseline_rows = []
    for key, members in sorted(baseline.items()):
        if len({jp_key(j.value) for _, j in members}) <= 1:
            continue
        sids = sorted({r['string_id'] for r, _ in members}, key=id_sort)
        cids = sorted({c for s in sids for c in memberships[s]})
        complete = len(cids) == 1 and all(memberships[s] == set(cids) for s in sids)
        bid = identity('baseline', key)
        baseline_rows.append(dict(baseline_id=bid, context=list(key), string_ids=sids,
            concept_ids=cids, status='one_supported_concept' if complete else 'unresolved',
            finding_ids=[f['finding_id'] for f in findings if set(cids) & set(f['concept_ids'])],
            variants=[dict(string_id=r['string_id'], jp=j.value) for r, j in members]))
        if not complete:
            baseline_rows[-1]['unresolved_id'] = problem('baseline_group', bid, ['baseline_string_group_not_proven_one_concept'], cids)
        else:
            baseline_rows[-1]['unresolved_id'] = None

    # Missing/unmatched English action headings remain visible, but no narrative is exported.
    anchored = {c['anchor_help_id'] for c in concepts.values()}
    for sid, entries in data['de_en'].entries.items():
        if sid not in anchored and any(ACTION.match(e.value) for e in entries):
            problem('help_anchor', sid, ['no_supported_name_anchor'])

    duplicates = audit_duplicates(data)
    for r in duplicates['rows']:
        for e in r['occurrences']:
            e.pop('value_excerpt', None); e.pop('excerpted', None)
    for u in unresolved.values():
        u['unmaterialized_anchor_ids'] = [c for c in u['candidate_concept_ids'] if c not in concepts]
        u['candidate_concept_ids'] = [c for c in u['candidate_concept_ids'] if c in concepts]
    coverage = [dict(string_id=sid, state='included' if memberships[sid] else 'unresolved',
                     concept_ids=sorted(memberships[sid]),
                     candidate_concept_ids=sorted({c for u in unresolved.values()
                                                   if u['string_id'] == sid
                                                   for c in u['candidate_concept_ids']}),
                     inventory_role=r['label_role'], basis='structural_inventory')
                for sid, r in sorted(by_name.items(), key=lambda x: id_sort(x[0]))]
    for c in concepts.values():
        if c['identity_status'] == 'reviewed_structural_seed':
            for oid in c['occurrence_ids']:
                o = occurrences[oid]
                coverage.append(dict(string_id=o['string_id'], state='included',
                    concept_ids=[c['concept_id']], candidate_concept_ids=[],
                    inventory_role=o['role'], basis='reviewed_structural_seed'))
    coverage.extend(candidate_coverage.values())
    coverage.sort(key=lambda c: id_sort(c['string_id']))
    statistics = dict(concepts=len(concepts), occurrences=len(occurrences), findings=len(findings),
        finding_kinds=dict(sorted(Counter(f['kind'] for f in findings).items())),
        unresolved=len(unresolved), unresolved_kinds=dict(sorted(Counter(u['kind'] for u in unresolved.values()).items())),
        baseline_groups=len(baseline_rows), baseline_ids=len({s for b in baseline_rows for s in b['string_ids']}),
        baseline_statuses=dict(sorted(Counter(b['status'] for b in baseline_rows).items())),
        inventory_names=len(inv['rows']),
        inventory_coverage=dict(sorted(Counter(c['state'] for c in coverage
                                               if c['basis'] == 'structural_inventory').items())),
        coverage_states=dict(sorted(Counter(c['state'] for c in coverage).items())),
        not_classified=sum(c['state'] == 'not_classified' for c in coverage),
        excluded_scope='General UI and prose not classified or aligned in Phase 2A-1')
    return dict(schema_version=1, generator=VERSION, rules_sha256=inv['rules_sha256'], inputs=inputs,
        statistics=statistics, concepts=sorted(concepts.values(), key=lambda c: c['concept_id']),
        occurrences=sorted(occurrences.values(), key=lambda o: o['occurrence_id']),
        relations=sorted(relations, key=lambda r: r['relation_id']),
        findings=sorted(findings, key=lambda f: f['finding_id']),
        unresolved=sorted(unresolved.values(), key=lambda u: u['unresolved_id']),
        baseline_groups=baseline_rows, history=history, coverage=coverage,
        diagnostics=dict(duplicates=duplicates, issues=[dict(dataset=n, **{k:v for k,v in asdict(i).items() if k!='raw'})
                                                     for n,d in data.items() for i in d.issues]))


def artifacts(audit):
    """JSON is authoritative; TSV cells use the existing lossless JSON encoding."""
    dumps = lambda obj: json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)
    result = {name + '.json': dumps(audit[name]) for name in
              ('concepts', 'relations', 'findings', 'unresolved', 'diagnostics')}
    for name in ('occurrences', 'history', 'coverage', 'baseline_groups'):
        rows = audit[name]
        fields = list(rows[0]) if rows else ['empty']
        result[name.replace('_', '-') + '.tsv'] = tsv(rows, fields)
    oby = {o['occurrence_id']: o for o in audit['occurrences']}
    reviews = []
    for c in audit['concepts']:
        fs = [f for f in audit['findings'] if c['concept_id'] in f['concept_ids']]
        reviews.append(dict(**c,
            evidence_signature=identity('evidence', [VERSION, audit['rules_sha256'], c,
                                                   [oby[o] for o in c['occurrence_ids']]]),
            baseline_group_ids=[b['baseline_id'] for b in audit['baseline_groups'] if c['concept_id'] in b['concept_ids']],
            existing_review_references=[r for r in audit.get('review_references', [])
                                       if r['string_id'] in {oby[o]['string_id'] for o in c['occurrence_ids']}],
            finding_ids=[f['finding_id'] for f in fs],
            finding_kinds=sorted({f['kind'] for f in fs}),
            displays=[{k:oby[o][k] for k in ('occurrence_id','string_id','role','en_term','jp_term','alignment')}
                      for o in c['occurrence_ids']]))
    result['review.tsv'] = tsv(reviews, list(reviews[0]) if reviews else ['concept_id'])
    result['findings.tsv'] = tsv(audit['findings'], list(audit['findings'][0]) if audit['findings'] else ['finding_id'])
    result['unresolved.tsv'] = tsv(audit['unresolved'], list(audit['unresolved'][0]) if audit['unresolved'] else ['unresolved_id'])
    lines = ['# Phase 2A-1 concept terminology audit', '',
             'Source-evidenced concepts only; no adjudication, translation, patch or Mod output.', '',
             'Review decisions: 統一する / 現状維持 / 別概念なので対象外. All reviewer fields start empty.', '',
             '## Counts', '', '```json', dumps(audit['statistics']), '```', '',
             '## Concepts with wording findings', '']
    for c in reviews:
        if not set(c['finding_kinds']) - {'layout_only_variation'}:
            continue
        lines.extend([f"### {c['concept_id']} — {c['english']}", '',
                      f"Family: {c['content_family']}; category: {c['category']}; Help: {c['anchor_help_id']}", '',
                      'Findings: ' + ', '.join(c['finding_kinds']), ''])
        for o in c['displays']:
            lines.append(f"- {o['string_id']} ({o['role']}): {json.dumps(o['jp_term'], ensure_ascii=False)}")
        lines.append('')
    result['summary.md'] = '\n'.join(lines)
    manifest = {k:audit[k] for k in ('schema_version','generator','rules_sha256','inputs','statistics')}
    manifest['provenance'] = audit.get('provenance', {})
    manifest['artifact_sha256'] = {name:digest(content.rstrip('\n')+'\n') for name,content in result.items()}
    manifest['review_choices'] = ['統一する', '現状維持', '別概念なので対象外']
    manifest['limitations'] = ['Structural source identity is not runtime game-object verification.',
        'Different Help anchors are not merged by English spelling.',
        'History is ID-aligned evidence, not proven semantic continuity.',
        'General UI/prose classification and body alignment are outside scope.',
        'Layout versus wording classification only; no kana/kanji equivalence rules.']
    result['manifest.json'] = dumps(manifest)
    return result


def write_artifacts(audit, output_dir, source_root):
    from .__main__ import write_report
    target = Path(output_dir).resolve()
    allowed = (Path.cwd() / 'reports' / 'phase2a').resolve()
    source = Path(source_root).resolve()
    if target == allowed or not target.is_relative_to(allowed) or target.is_relative_to(source):
        raise ValueError('Phase 2A reports require reports/phase2a/<new-run>/ outside source')
    protected = [Path.cwd() / name for name in ('source', 'reviews', 'translations', 'dist', 'tools', 'tests', 'docs')]
    if any(target.is_relative_to(p.resolve()) for p in protected):
        raise ValueError('Report path resolves into a protected directory')
    if target.exists():
        raise ValueError('Run directory already exists; choose a new run')
    reports = artifacts(audit)
    for name, content in reports.items():
        write_report(target / name, content.rstrip('\n'), source_root)
        if (target / name).read_text(encoding='utf8') != content.rstrip('\n')+'\n':
            raise ValueError('Report read-back mismatch: ' + name)
    return [str(Path(output_dir) / name) for name in reports]
