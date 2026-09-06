"""Policy-based review proposals. Never produces translation overrides."""

from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import re

from .gameplay import ORDER, build_inventory, normalized, short_label


CLASSES = ('restore_candidate', 'manual_review', 'keep_de_candidate', 'new_content', 'id_reuse')


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def load_exceptions():
    return json.loads(Path(__file__).with_name('restoration_evidence.json').read_text(encoding='utf-8'))


def assess(name, datasets, exceptions, historical_names):
    sid = name['string_id']
    entries = {n: datasets[n].resolved(sid) if n in datasets else None for n in ORDER}
    values = {n: e.value if e else None for n, e in entries.items()}
    flags = set(name['flags'])
    flags.update(('human_approval_required', 'legacy_english_unavailable', 'runtime_display_unverified'))
    legacy = [values[n] for n in ('aok_jp', 'aoc_jp') if values[n] is not None]
    proposed = None
    confidence = 'review-needed'
    classification = 'manual_review'
    reason = 'Legacy対応または名称の用途を確定できないため、個別判断が必要。'
    evidence = exceptions.get(sid)
    evidence_valid = bool(evidence and all(values[n] is not None and digest(values[n]) == evidence[n + '_sha256']
                                         for n in ('hd_en', 'de_en')))
    if evidence and not evidence_valid:
        flags.add('stale_review_evidence')
    if 'input_ambiguity' in flags or any(sid in d.invalid_ids for d in datasets.values()):
        reason = '重複・不正入力がある。DLL優先順位や同値重複を解決せず、全出現を確認する。'
    elif evidence_valid:
        classification, confidence = 'id_reuse', 'source-corroborated'
        reason = evidence['reason']
        flags.add('reviewed_id_reuse')
    elif evidence:
        reason = '登録したID再利用根拠と現在の英語値が一致しない。根拠の再検証が必要。'
    elif any(n not in datasets for n in ORDER):
        reason = '比較データセットが未配置。欠損を新規コンテンツとみなさない。'
    elif values['de_en'] is None or values['de_jp'] is None:
        reason = 'DEの日英いずれかが欠けている。'
    elif 'de_new_id' in flags and normalized(values['de_en']) not in historical_names:
        classification, confidence = 'new_content', 'provisional'
        flags.add('concept_novelty_unverified')
        reason = '収録Legacy/HDに同IDがなく、HD英語名称にも同名を確認できない。新規方針の調査候補であり、別ID・別名の既存概念がないことまでは未証明。'
    elif name['content_family'] != 'core' or name['category'] == 'unknown' or 'english_name_help_mismatch' in flags:
        reason = 'Chronicles等の別文脈、内容分類または名称と説明の対応を先に確認する。'
    elif values['hd_en'] != values['de_en']:
        flags.add('semantic_continuity_review')
        reason = 'HDとDEの英語名称が不一致または欠損。単なる改名か、意味変更・ID再利用かを用途とともに確認する。'
    elif not legacy:
        reason = '同IDの非空Legacy訳がない。HDのみをAoK/AoCの基準訳として補完しない。'
    elif len(set(legacy)) != 1 or values['hd_jp'] != legacy[0]:
        flags.add('unstable_legacy_hd')
        reason = 'AoK/AoC/HDの収録訳が競合、変化または欠損している。採用する世代を推測しない。'
    elif any(re.search(r'[\\<>%{}]', v) for v in (legacy[0], values['de_jp'])):
        flags.add('technical_syntax_review')
        reason = '構文・エスケープの世代間解釈を個別検証する。'
    elif legacy[0] == values['de_jp']:
        classification, confidence = 'keep_de_candidate', 'source-corroborated'
        reason = '収録Legacy・HD・DEの日本語が一致。既に基準訳を維持しており、復元変更は不要。'
    else:
        classification, confidence = 'restore_candidate', 'source-corroborated'
        proposed = legacy[0]
        reason = '非空で一意なLegacy訳がHD日本語と一致し、HD/DE英語名称も一致。DE日本語のみ変更されているため、原則復元を推奨する候補。意味・実ゲーム表示・例外の最終確認は未完了。'
    return dict(string_id=sid, category=name['category'], content_family=name['content_family'],
                classification=classification, proposed_jp=proposed, confidence=confidence,
                flags=sorted(flags), review_reason=reason, datasets=name['datasets'],
                basis_sources={n: name['datasets'][n] for n in ORDER},
                name_evidence=name['evidence'], related_ids=name['related_ids'], series=name['series'],
                exception_evidence=evidence if evidence else None)


def build_restoration(datasets, audit=None, exceptions=None):
    audit = audit if audit is not None else build_inventory(datasets)
    exceptions = exceptions if exceptions is not None else load_exceptions()
    historical_names = {normalized(e.value) for d in ('hd_en',) if d in datasets
                        for entries in datasets[d].entries.values() for e in entries if short_label(e.value)}
    primary = [r for r in audit['rows'] if r['label_role'] == 'full_name']
    rows = [assess(r, datasets, exceptions, historical_names) for r in primary]
    counts = Counter(r['classification'] for r in rows)
    return dict(schema_version=1, scope='Phase 1A full_name candidates; not a complete gameplay roster',
                total=len(rows), excluded_compact_or_unverified=len(audit['rows']) - len(rows),
                counts={c: counts[c] for c in CLASSES}, rows=rows,
                rules_sha256=audit['rules_sha256'],
                exceptions_sha256=digest(json.dumps(exceptions, sort_keys=True, ensure_ascii=False)),
                policy_sha256=hashlib.sha256((Path(__file__).resolve().parents[2] / 'docs/localization-policy.md').read_bytes()).hexdigest(),
                inputs=[dict(dataset=n, path=f.path, sha256=f.sha256) for n,d in datasets.items() for f in d.files])


def display_cell(cell):
    if cell['state'] == 'resolved':
        return cell['occurrences'][0]['value']
    return cell['state']


def render_tsv(report):
    fields = ['string_id', 'category', 'content_family', 'classification', *ORDER,
              'proposed_jp', 'confidence', 'flags', 'review_reason', 'basis_sources', 'name_evidence',
              'exception_evidence', 'related_ids', 'series']
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fields, delimiter='\t', lineterminator='\n')
    writer.writeheader()
    for row in report['rows']:
        out = {k: row[k] for k in fields if k in row}
        out.update({n: display_cell(row['datasets'][n]) if row['datasets'][n]['state'] != 'ambiguous'
                    else row['datasets'][n] for n in ORDER})
        # JSON scalar quoting prevents formula execution and retains literal syntax.
        writer.writerow({k: json.dumps(v, ensure_ascii=False) if k != 'string_id' else v for k,v in out.items()})
    return stream.getvalue()


def render_markdown(report):
    def esc(text):
        return str(text).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('|','&#124;').replace('\n','<br>')
    lines = ['# Phase 1B 復元候補レビュー', '', '翻訳未変更。採用・ゲーム内の意味と表示は未確定。', '',
             f"対象: {report['scope']} / {report['total']}件。compact等除外: {report['excluded_compact_or_unverified']}件。", '',
             '| Classification | Count |', '|---|---:|']
    lines += [f'| {k} | {v} |' for k,v in report['counts'].items()]
    lines += ['', 'keep_de_candidate は今回、Legacy/HD/DE既一致の維持候補。new_content は資料上の新規候補で、概念の新規性は未証明。',
              'Legacy英語は未収集。AoC欠損にAoKを補完せず、DLLの実ロード順も確定していない。', '',
              '## 復元候補例（String ID順、最大25件）', '', '| ID | DE EN | DE JP | proposed JP |', '|---|---|---|---|']
    for r in [r for r in report['rows'] if r['classification']=='restore_candidate'][:25]:
        lines.append('| '+' | '.join(esc(v) for v in (r['string_id'],display_cell(r['datasets']['de_en']),display_cell(r['datasets']['de_jp']),r['proposed_jp']))+' |')
    lines += ['', '## ID再利用の確認済み候補', '']
    for r in report['rows']:
        if r['classification']=='id_reuse':
            lines.append(f"- {r['string_id']}: {esc(r['review_reason'])}")
    lines += ['', '## 再現用メタデータ', '', '```json', json.dumps({k:v for k,v in report.items() if k!='rows'},ensure_ascii=False,indent=2), '```', '']
    return '\n'.join(lines)
