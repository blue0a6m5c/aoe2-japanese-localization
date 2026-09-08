"""Unapproved editorial review sheets, with bounded contextual source evidence."""
from collections import Counter
import csv
import io
import json
from pathlib import Path

from .analysis import id_sort
from .gameplay import ORDER, build_inventory, cell, normalized
from .restoration import build_restoration, digest, display_cell

DECISIONS = ('restore', 'keep_de', 'revise', 'manual_review')
SERIES = [('Samurai', 'Elite Samurai'), ('Galleon', 'Cannon Galleon', 'Elite Cannon Galleon'),
          ('Fire Galley', 'Fire Ship', 'Fast Fire Ship'), ('Turtle Ship', 'Elite Turtle Ship')]


def value(data, name, sid):
    e = data[name].resolved(sid) if name in data else None
    return e.value if e else None


def signature(data, sid, help_ids):
    return digest(json.dumps({s: {n: cell(data.get(n), s) for n in ORDER}
                              for s in sorted({sid, *help_ids}, key=id_sort)}, sort_keys=True, ensure_ascii=False))


def context(data, name, inventory):
    sid = name['string_id']
    en = value(data, 'de_en', sid)
    paths = {e.path for e in data['de_en'].entries.get(sid, [])}
    labels = {normalized(en)} if en else set()
    for series in SERIES:
        if en in series:
            labels.update(series)
    references = {}
    for other, entries in data['de_en'].entries.items():
        for e in entries:
            if e.path not in paths:
                continue
            text = normalized(e.value)
            if text in labels:
                references[other] = 'name_or_series_label'
            elif any(text == f'{action} {label}' for action in ('Create', 'Build', 'Research', 'Upgrade to', 'Advance to') for label in labels):
                references[other] = 'action_button'
    # Only actual name/heading links; no arithmetic ID guesses.
    for row in inventory['rows']:
        if row['string_id'] in references:
            for ev in row['evidence']:
                references[ev['help_id']] = 'linked_help'
    for ev in name['name_evidence']:
        references[ev['help_id']] = 'linked_help'
    return [dict(string_id=s, relation=references[s], datasets={n:cell(data.get(n),s) for n in ORDER})
            for s in sorted(references, key=id_sort)]


def build_adoption(data, inventory=None, cases=None, human_ledger=None):
    inventory = inventory if inventory is not None else build_inventory(data)
    source = build_restoration(data, inventory)
    if cases is None:
        cases = json.loads(Path(__file__).with_name('adoption_cases.json').read_text(encoding='utf8'))
    audit_by_id = {r['string_id']:r for r in inventory['rows']}
    rows = []
    for candidate in source['rows']:
        if candidate['classification'] != 'restore_candidate':
            continue
        sid = candidate['string_id']
        helps = sorted({ev['help_id'] for ev in candidate['name_evidence']}, key=id_sort)
        fingerprint = signature(data, sid, helps)
        case = cases.get(sid)
        valid = case and case['signature'] == fingerprint
        row = dict(candidate, decision='manual_review', confidence='low', approval_status='pending',
                   reviewer='', reviewer_decision='', reviewer_proposed_jp='', reviewer_notes='',
                   legacy_candidate_jp=candidate['proposed_jp'], proposed_jp=None,
                   reason='HD/DE英語名称とLegacy/HD日本語は一致。名称の一致だけでは仕様継続を証明できないため、関連Helpの日英・世代差を個別確認する。',
                   upstream_class='subjective', signature=fingerprint,
                   related=context(data,candidate,inventory),
                   consistency_evidence=audit_by_id[sid]['jp_heading_disagreements'],
                   current_use_status='source_help_linked; runtime_unverified')
        if valid:
            row.update({k:case[k] for k in ('decision','confidence','reason','upstream_class')})
            row['proposed_jp'] = (candidate['proposed_jp'] if case['decision']=='restore'
                                  else value(data,'de_jp',sid) if case['decision']=='keep_de'
                                  else case.get('proposed_jp'))
        elif case:
            row['reason'] = 'レビュー時から原資料または出現位置が変わったため、以前の判断を保留。再確認が必要。'
            row['flags'] = sorted(set(row['flags']) | {'stale_editorial_review'})
        row['upstream_classes'] = sorted({row['upstream_class']} | ({'consistency_fix'} if row['consistency_evidence'] else set()))
        rows.append(row)
    bugs = []
    # A reviewed ID-reuse hazard, not a claim of an existing Japanese mistranslation.
    sid = '5526'
    if value(data,'de_en',sid)=='Champi Scout' and value(data,'hd_en',sid)=='Joan of Arc':
        candidate = next((r for r in source['rows'] if r['string_id']==sid), None)
        if candidate:
            bugs.append(dict(string_id=sid, upstream_class='definite_bug',
                bug_scope='legacy_id_join_or_automatic_restoration', confidence='high',
                current_de_translation_bug_confirmed=False, approval_status='pending',
                reason='HDの英雄名IDがDEで斥候名に再利用されている。同IDへ旧英雄名を復元すれば別概念の誤表示になる。現在のDE翻訳自体の誤りとは区別し、関連名称・作成・Helpの日英出現を別途確認する。現在のゲームの誤表示は未確認。',
                related=context(data,candidate,inventory)))
    report = dict(schema_version=2, scope='automatic proposals and separately bound human adjudications; no mod application',
                total=len(rows), counts={d:sum(r['decision']==d for r in rows) for d in DECISIONS},
                upstream_counts=dict(sorted(Counter(r['upstream_class'] for r in rows).items())),
                consistency_rows=sum(bool(r['consistency_evidence']) for r in rows), rows=rows, bugs=bugs,
                inputs=source['inputs'], policy_sha256=source['policy_sha256'],
                cases_sha256=digest(json.dumps(cases,sort_keys=True,ensure_ascii=False)))
    from .human_reviews import apply_ledger, load_ledger
    return apply_ledger(report,data,inventory,load_ledger() if human_ledger is None else human_ledger)


def tsv(rows, fields):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fields, delimiter='\t', lineterminator='\n')
    writer.writeheader()
    for row in rows:
        writer.writerow({k:json.dumps(row.get(k),ensure_ascii=False) for k in fields})
    return stream.getvalue()


def render_review(report):
    rows=[]
    for r in report['rows']:
        out = {k:v for k,v in r.items() if k not in ('datasets','related')}
        out.update({n:display_cell(r['datasets'][n]) for n in ORDER})
        out['related_ids'] = [x['string_id'] for x in r['related']]
        rows.append(out)
    return tsv(rows, ['string_id','category',*ORDER,'legacy_candidate_jp','proposed_jp','decision','confidence',
                      'upstream_class','upstream_classes','reason','related_ids','consistency_evidence',
                      'current_use_status','approval_status','reviewer','reviewer_decision',
                      'reviewer_proposed_jp','reviewer_notes','effective_decision','effective_proposed_jp',
                      'human_review_id','human_signature','human_evidence_status','original_candidate','signature','basis_sources'])


def render_evidence(report):
    unique = {}
    for row in report['rows'] + report['bugs']:
        for ref in row['related']:
            sid = ref['string_id']
            if sid not in unique:
                unique[sid] = dict(string_id=sid, candidate_ids=[], relation=ref['relation'], provenance=ref['datasets'],
                                   **{n:display_cell(ref['datasets'][n]) for n in ORDER})
            unique[sid]['candidate_ids'].append(row['string_id'])
    return tsv([unique[s] for s in sorted(unique,key=id_sort)],
               ['string_id','candidate_ids','relation',*ORDER,'provenance'])


def render_summary(report):
    def esc(v):
        return str(v if v is not None else '未決定').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('|','&#124;').replace('\n','<br>')
    lines=['# Phase 1B 採用候補レビュー','',
           'Decisionは元の自動提案。人間裁定はreviewer_*とeffective_*に分離し、原資料の指紋が一致するとき優先する。翻訳ファイルには未適用。',
           'Legacy英語と実ゲーム表示は未確認。用途はローカルHD/DEの関連Helpで確認し、数値や対象ユニットの変更と名称の意味を区別する。',
           '主表 review.tsv の related_ids は evidence.tsv の全出現・全文に対応。名称一致リンクはゲーム内部のオブジェクト参照を証明するものではない。','',
           '| Decision | 件数 |','|---|---:|']
    lines += [f'| {k} | {v} |' for k,v in report['counts'].items()]
    lines += ['', '## 人間裁定', '', json.dumps(report.get('human_counts',{}),ensure_ascii=False), '',
              '元の80候補: '+json.dumps(report.get('baseline_human_counts',{}),ensure_ascii=False), '',
              '追加ID: '+', '.join(report.get('human_review',{}).get('additional_ids',[])),
              '原資料再検証が必要なID: '+', '.join(report.get('human_review',{}).get('stale_ids',[])), '']
    lines += ['',f"名称とHelp見出しの不一致証拠を持つ候補: {report['consistency_rows']}件。",'',
              '## 全候補（有効な人間裁定を優先）','', '| ID | EN | DE JP | 採用/提案JP | Effective Decision | 承認状態 | 上流分類（自動） |','|---|---|---|---|---|---|---|']
    for r in report['rows']:
        lines.append('| '+' | '.join(esc(v) for v in (r['string_id'],display_cell(r['datasets']['de_en']),display_cell(r['datasets']['de_jp']),r['effective_proposed_jp'],r['effective_decision'],r['approval_status'],','.join(r['upstream_classes'])))+' |')
    lines += ['', '## 個別の判断理由と対応証拠', '']
    for r in report['rows']:
        lines += [f"### {r['string_id']} — {esc(display_cell(r['datasets']['de_en']))}", '',r['reason'], '',
                  '関連ID: '+', '.join(x['string_id'] for x in r['related']), '']
        if r.get('human_review_id'):
            lines += ['人間裁定: '+esc(r['reviewer_decision'])+' / '+esc(r['reviewer_proposed_jp'])+'。'+r['reviewer_notes'], '']
        if r['consistency_evidence']:
            lines += ['DE見出しの相違: '+esc(json.dumps(r['consistency_evidence'],ensure_ascii=False)), '']
    lines += ['', '## definite_bug：ID再利用による比較・復元の誤り', '']
    for bug in report['bugs']:
        lines += [f"- {bug['string_id']}: {bug['reason']}"]
    lines += ['', '## 再現性', '', '```json',json.dumps({k:v for k,v in report.items() if k not in ('rows','bugs')},ensure_ascii=False,indent=2),'```','']
    return '\n'.join(lines)
