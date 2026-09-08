"""Durable user adjudications; no translation/mod writes or implied propagation."""
from collections import Counter
import json
from pathlib import Path

from .analysis import id_sort
from .gameplay import ACTION, ORDER, cell, normalized
from .restoration import digest

DEFAULT_LEDGER = Path(__file__).resolve().parents[2] / 'reviews/phase1b-decisions.json'


def load_ledger(path=DEFAULT_LEDGER):
    ledger = json.loads(Path(path).read_text(encoding='utf8'))
    validate(ledger)
    return ledger


def validate(ledger):
    baseline = ledger.get('baseline_ids', [])
    if len(baseline) != len(set(baseline)):
        raise ValueError('Duplicate baseline candidate ID')
    ids = set()
    for r in ledger.get('records', []):
        sid = r['string_id']
        if sid in ids:
            raise ValueError(f'Duplicate human decision: {sid}')
        ids.add(sid)
        if r['decision'] not in ('restore', 'keep_de', 'revise'):
            raise ValueError(f'Invalid human decision: {sid}')
        if not isinstance(r.get('proposed_jp'), str) or not r['proposed_jp']:
            raise ValueError(f'Explicit adopted Japanese required: {sid}')
        if not r.get('expected_de_english') or not r.get('signature'):
            raise ValueError(f'Human decision requires evidence binding: {sid}')


def apply_ledger(report, data, inventory, ledger):
    from .adoption import context, signature, value
    validate(ledger)
    records = {r['string_id']:r for r in ledger.get('records', [])}
    original_ids = {r['string_id'] for r in report['rows']}
    baseline = set(ledger.get('baseline_ids', []))
    audit_rows = {r['string_id']:r for r in inventory['rows']}
    current_rows = {r['string_id']:r for r in report['rows']}
    absent = []
    for sid, record in records.items():
        if sid in current_rows:
            continue
        if not data.get('de_en') or sid not in data['de_en'].entries:
            absent.append(sid)
            continue
        a = audit_rows.get(sid, {})
        candidate = dict(string_id=sid, category=a.get('category','unknown'),
                         datasets={n:cell(data.get(n),sid) for n in ORDER},
                         name_evidence=a.get('evidence',[]))
        report['rows'].append(dict(candidate, decision='manual_review', confidence='low',
             proposed_jp=None, legacy_candidate_jp=None, reason='Explicit human record outside current automatic candidate set.',
             flags=[], upstream_class='subjective', upstream_classes=['subjective'],
             related=context(data,candidate,inventory), consistency_evidence=a.get('jp_heading_disagreements',[]),
             basis_sources=candidate['datasets'], current_use_status='source_evidence_only; runtime_unverified',
             signature=signature(data,sid,[e['help_id'] for e in candidate['name_evidence']])))
    stale = []
    for row in report['rows']:
        sid = row['string_id']
        row.update(effective_decision=row['decision'], effective_proposed_jp=row['proposed_jp'],
                   human_review_id=None, human_signature=None, human_evidence_status='not_reviewed',
                   original_candidate=sid in baseline)
        r = records.get(sid)
        if not r:
            continue
        live_helps = sorted({e['help_id'] for e in audit_rows.get(sid,{}).get('evidence',[])},key=id_sort)
        bound = (value(data,'de_en',sid)==r['expected_de_english']
                 and signature(data,sid,r['help_ids'])==r['signature']
                 and live_helps==sorted(set(r['help_ids']),key=id_sort))
        row.update(reviewer=ledger['reviewer'], reviewer_decision=r['decision'],
                   reviewer_proposed_jp=r['proposed_jp'], reviewer_notes=r['notes'],
                   human_review_id=ledger['review_id'], human_signature=r['signature'],
                   human_evidence_status='matches' if bound else 'stale',
                   approval_status='approved' if bound else 'approved_requires_revalidation',
                   effective_decision=r['decision'] if bound else 'manual_review',
                   effective_proposed_jp=r['proposed_jp'] if bound else None)
        if not bound:
            stale.append(sid)
    report['rows'].sort(key=lambda r:id_sort(r['string_id']))
    related = []
    for row in report['rows']:
        sid = row['string_id']
        if sid not in records:
            continue
        en = records[sid]['expected_de_english']
        target_helps = {e['help_id'] for e in audit_rows.get(sid,{}).get('evidence',[])}
        for ref in row['related']:
            other = ref['string_id']
            if other==sid:
                continue
            text = value(data,'de_en',other)
            match = ACTION.match(text or '')
            kind = 'unverified_name_or_series_link'
            if match and normalized(match[2])==normalized(en) and other in target_helps:
                kind = 'same_name_action_help'
            elif text and normalized(text)==normalized(en):
                shared = target_helps & {e['help_id'] for e in audit_rows.get(other,{}).get('evidence',[])}
                if shared:
                    kind = 'same_name_shared_help'
            elif text and any(text==f'{action} {en}' for action in ('Create','Build','Research','Upgrade to','Advance to')):
                # Action label agrees with this name; no full sentence substitution.
                if any(e['action'] == text[:-len(en)].strip() for e in audit_rows.get(sid,{}).get('evidence',[])):
                    kind = 'same_name_action_button'
            known = kind!='unverified_name_or_series_link'
            adjudication = records.get(other)
            status = ('human_agreement' if adjudication['proposed_jp']==records[sid]['proposed_jp'] else 'human_conflict') if known and adjudication else (
                'linked_usage_requires_implementation_review' if known else 'not_propagated')
            related.append(dict(string_id=sid, related_id=other, relation=kind, status=status,
                                expected_name_jp=records[sid]['proposed_jp'] if known else None,
                                current_de_jp=value(data,'de_jp',other),
                                target_human_evidence_status=row['human_evidence_status'],
                                source=ref['datasets']['de_en']))
    count = lambda rs: {d:sum(r['decision']==d for r in rs) for d in ('restore','keep_de','revise')}
    report.update(human_counts=count(records.values()))
    report['baseline_human_counts'] = count([r for s,r in records.items() if s in baseline])
    report['human_review'] = dict(review_id=ledger.get('review_id'),
         ledger_sha256=digest(json.dumps(ledger,sort_keys=True,ensure_ascii=False)),
         baseline_count=len(baseline), recorded_count=len(records),
         missing_baseline_ids=sorted(baseline-records.keys(),key=id_sort),
         additional_ids=sorted(records.keys()-baseline,key=id_sort),
         absent_source_ids=sorted(absent,key=id_sort), stale_ids=sorted(stale,key=id_sort),
         current_unreviewed_ids=sorted(original_ids-records.keys(),key=id_sort),
         related_status_counts=dict(sorted(Counter(r['status'] for r in related).items())),
         related_checks=related)
    report['total']=len(report['rows'])
    return report
