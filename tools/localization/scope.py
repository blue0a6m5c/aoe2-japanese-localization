"""Read-only application-scope audit. No replacement or mod generation."""
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

from .adoption import build_adoption, tsv
from .analysis import id_sort, occurrence
from .gameplay import ACTION, build_inventory, normalized
from .human_reviews import implementation_ledger, load_ledger
from .restoration import digest
from .duplicate_audit import audit_duplicates
from . import context_overrides

CLASSES = ('required', 'recommended', 'review', 'unrelated', 'already_consistent')
FIELDS = ['decision_string_id','decision_en','current_jp','effective_jp','effective_decision',
          'related_string_id','related_type','related_en','related_jp','source_path','source_line',
          'relation','scope_class','confidence','reason','reviewer_decision','reviewer_notes',
          'start','end','matched_jp','excerpted','english_source','source_sha256',
          'decision_signature','evidence_status','change_candidate','conflict','match_basis']
FIELDS += ['literal_stored_value_equal','normalized_equal','normalized_equivalent',
           'normalized_matched_jp','normalized_effective_jp','comparison_result',
           'literal_scope_class','literal_change_candidate','normalization_rule']


def layout_key(value):
    """Comparison key only. Preserve punctuation, markup, unknown and escaped escapes."""
    if value is None: return None
    result=[]; i=0
    while i<len(value):
        c=value[i]
        if c=='\\' and i+1<len(value):
            if value[i+1] in 'nrt':
                i+=2; continue
            # A literal backslash or escaped quote is not a display newline.
            result.append(value[i:i+2]); i+=2; continue
        if not c.isspace(): result.append(c)
        i+=1
    return ''.join(result)


def comparison_fields(matched, canonical):
    literal=None if matched is None else matched==canonical
    key=layout_key(matched); adopted=layout_key(canonical)
    equivalent=None if key is None else key==adopted
    return dict(literal_stored_value_equal=literal,normalized_equal=equivalent,
                normalized_equivalent=equivalent is True and literal is False,
                normalized_matched_jp=key,normalized_effective_jp=adopted,
                comparison_result='unavailable' if matched is None else 'literal_equal' if literal else
                                  'normalized_equivalent' if equivalent else 'different',
                normalization_rule='layout_whitespace_v1')


def relation_statistics(rows):
    relations={'adjudicated_name','same_name_shared_help','same_name_action_button','same_name_action_help',
               'same_action_and_exact_name_prefix'}
    output={}
    for relation in sorted(relations):
        group=[r for r in rows if r['relation']==relation]
        output[relation]=dict(total=len(group),actual_change_candidates=sum(r['change_candidate'] for r in group),
            normalized_equivalent=sum(r['scope_class']=='already_consistent' and r['normalized_equivalent'] for r in group),
            already_consistent=sum(r['scope_class']=='already_consistent' and r['literal_stored_value_equal'] is True for r in group),
            review_or_other=sum(r['scope_class'] not in ('required','recommended','already_consistent') for r in group))
    return output


def variants(name):
    # Search morphology only; it never changes the adopted translation.
    out = {name, name+'s'}
    if name.endswith('man'): out.add(name[:-3]+'men')
    if name.endswith('y'): out.add(name[:-1]+'ies')
    return out


def excerpt(text, start=0, limit=180):
    if text is None: return None
    if len(text)<=limit: return text
    begin=max(0,start-60)
    return ('…' if begin else '')+text[begin:begin+limit]+('…' if begin+limit<len(text) else '')


def conflicts(rows):
    """Different concepts in distinct spans of the same Help are not conflicts."""
    by_location=defaultdict(list)
    for r in rows:
        r['conflict']=False
        if r['scope_class'] in ('required','recommended','already_consistent') and r['start'] is not None:
            by_location[(r['source_path'],r['source_line'])].append(r)
    found=[]
    for location, group in sorted(by_location.items()):
        ordered=sorted(group,key=lambda r:(r['start'],r['end'],id_sort(r['decision_string_id'])))
        for i,a in enumerate(ordered):
            for b in ordered[i+1:]:
                if b['start']>=a['end']: break
                if a['effective_jp']==b['effective_jp'] or a['decision_string_id']==b['decision_string_id']: continue
                a['conflict']=b['conflict']=True
                found.append(dict(source_path=location[0],source_line=location[1],
                                  related_string_id=a['related_string_id'],
                                  decisions=[a['decision_string_id'],b['decision_string_id']],
                                  spans=[[a['start'],a['end']],[b['start'],b['end']]],
                                  effective_jp=[a['effective_jp'],b['effective_jp']]))
    return found


def build_scope(data, ledger=None, inventory=None, adoption=None, context_path=None):
    from .source_states import evidence_data, project_scope
    original, states = evidence_data(data)
    if states:
        if inventory is not None or adoption is not None:
            raise ValueError('After-state scope requires freshly generated inventory/adoption')
        return project_scope(build_scope(original, ledger, context_path=context_path), states)
    if ledger is None and context_path is None:
        context_path=context_overrides.DEFAULT_PATH
    ledger=load_ledger() if ledger is None else ledger
    deferred_adjudications=[r['string_id'] for r in ledger['records']
                            if r.get('implementation_status')=='adjudicated_not_patch_enabled']
    if deferred_adjudications:
        # Phase 2A concept records are authoritative adjudications, but the existing
        # name-scope planner cannot consume their explicit role/span bindings yet.
        # Exclude them from implementation planning until that separate work is authorized.
        ledger=implementation_ledger(ledger)
    inventory=build_inventory(data) if inventory is None else inventory
    adoption=build_adoption(data,inventory,human_ledger=ledger) if adoption is None else adoption
    records={r['string_id']:r for r in ledger['records']}
    inventory_by_id={r['string_id']:r for r in inventory['rows']}
    adopted={r['string_id']:r for r in adoption['rows'] if r['string_id'] in records}
    known={(r['string_id'],r['related_id']):r['relation'] for r in adoption['human_review']['related_checks']
           if r['relation']!='unverified_name_or_series_link'}
    prior={s:{r['string_id'] for r in row['related']} for s,row in adopted.items()}
    names={s:r['expected_de_english'] for s,r in records.items()}
    aliases=defaultdict(set)
    english=defaultdict(set)
    for sid,rec in records.items():
        for spelling in variants(names[sid]): english[spelling].add(sid)
        row=adopted.get(sid,{})
        current=data['de_jp'].resolved(sid)
        if current: aliases[current.value].add(sid)
        aliases[rec['proposed_jp']].add(sid)
        # Observed alternate name headings (e.g. Siege Workshop), not guessed replacements.
        for h in rec['help_ids']:
            e=data['de_jp'].resolved(h)
            head=re.match(r'^\s*<b>(.*?)<b>',e.value) if e else None
            if head and len(head[1])<=80: aliases[head[1]].add(sid)
    # Explicitly requested search stem; detection only, always contextual review.
    for sid,name in names.items():
        if name=='Galleon': aliases['ガレオン'].add(sid)
    aliases={a:s for a,s in aliases.items() if a}
    jp_re=re.compile('|'.join(re.escape(a) for a in sorted(aliases,key=lambda a:(-len(a),a)))) if aliases else None
    en_re=re.compile(r'(?<![\w])(?:'+'|'.join(re.escape(a) for a in sorted(english,key=lambda a:(-len(a),a)))+r')(?![\w])') if english else None
    # Known longer labels prevent base-name restoration into a different named unit.
    label_owners=defaultdict(set)
    jp_owners=defaultdict(set)
    for row in inventory['rows']:
        for e in data['de_en'].entries.get(row['string_id'],[]): label_owners[(e.path,normalized(e.value))].add(row['string_id'])
        en_value=data['de_en'].resolved(row['string_id'])
        jp_value=data['de_jp'].resolved(row['string_id'])
        if en_value and jp_value and 1<len(jp_value.value)<=80:
            jp_owners[jp_value.value].add(normalized(en_value.value))
    protect_re=re.compile('|'.join(re.escape(a) for a in sorted(jp_owners,key=lambda a:(-len(a),a)))) if jp_owners else None
    inputs={f.path:f.sha256 for d in data.values() for f in d.files}
    rows=[]; duplicate_ids=set(); scanned=0
    pair_refs=defaultdict(set)
    for sid,related in prior.items():
        for other in related: pair_refs[other].add(sid)
    # Scan every JP occurrence; English-only and prior-evidence discoveries are included too.
    universe=set(data['de_jp'].entries)|set(data['de_en'].entries)
    for other in sorted(universe,key=id_sort):
        jps=data['de_jp'].entries.get(other,[])
        ens=data['de_en'].entries.get(other,[])
        for jp in jps or [None]:
            scanned+=1
            raw=jp.value if jp else ''
            # Require a same-file language pair; do not choose an occurrence by load order.
            paired=[e for e in ens if jp is None or Path(e.path).name==Path(jp.path).name]
            en=paired[0] if len(paired)==1 else None
            text=en.value if en else ''
            ematches=list(en_re.finditer(text)) if en_re else []
            etargets=defaultdict(list)
            for m in ematches:
                for s in english[m[0]]: etargets[s].append(m)
            jmatches=list(jp_re.finditer(raw)) if jp_re else []
            protected=list(protect_re.finditer(raw)) if protect_re else []
            jtargets=defaultdict(list)
            for m in jmatches:
                for s in aliases[m[0]]: jtargets[s].append(m)
            targets=set(jtargets)|set(etargets)|pair_refs[other]|({other} if other in records else set())
            header=re.match(r'^\s*<b>(.*?)<b>',raw)
            eheader=ACTION.match(text)
            ambiguous=(len(jps)>1 or len(ens)>1 or other in data['de_jp'].invalid_ids
                       or other in data['de_en'].invalid_ids or any(e.ambiguous for e in jps+ens))
            if ambiguous and targets: duplicate_ids.add(other)
            for s in sorted(targets,key=id_sort):
                rec=records[s]; row=adopted.get(s,{})
                valid=row.get('human_evidence_status')=='matches'
                current=data['de_jp'].resolved(s)
                same_file=bool(en and any(Path(e.path).name==Path(en.path).name for e in data['de_en'].entries.get(s,[])))
                trusted=known.get((s,other))
                plain_action=next((e['action'] for e in inventory_by_id.get(s,{}).get('evidence',[])
                                   if re.match(r'^'+re.escape(e['action']+' '+names[s])+r'(?:$| \()',text)),None)
                slots=[]
                if other==s or (trusted=='same_name_shared_help' and normalized(text)==normalized(names[s])):
                    slots.append((0,len(raw),'name',trusted or 'adjudicated_name'))
                elif trusted=='same_name_action_help' and header and eheader and normalized(eheader[2])==normalized(names[s]):
                    slots.append((header.start(1),header.end(1),'help_heading',trusted))
                elif trusted=='same_name_action_button':
                    matches=jtargets[s]
                    if len(matches)==1: slots.append((matches[0].start(),matches[0].end(),'button',trusted))
                elif plain_action:
                    boundary=min([raw.index(c) for c in ('(','（') if c in raw] or [len(raw)])
                    matches=[m for m in jtargets[s] if m.end()<=boundary]
                    if len(matches)==1:
                        slots.append((matches[0].start(),matches[0].end(),'button_with_description','same_action_and_exact_name_prefix'))
                for m in jtargets[s]:
                    if any(a<=m.start() and m.end()<=b for a,b,_,_ in slots): continue
                    slots.append((m.start(),m.end(),'help_body' if eheader else 'description_or_text','jp_alias_match'))
                if not slots: slots=[(None,None,'prior_evidence' if s in pair_refs[other] else 'english_reference','evidence_or_english_only')]
                for start,end,kind,basis in slots:
                    matched=raw[start:end] if start is not None else None
                    direct=basis!='jp_alias_match' and start is not None
                    english_body=[m for m in etargets[s] if not eheader or m.start()>=eheader.end()]
                    is_prior_different=(en is not None and not etargets[s] and (
                        (en.path,normalized(text)) in label_owners or
                        (eheader is not None and s in pair_refs[other] and not jtargets[s])))
                    cls='review'; confidence='low'
                    reason='語句または旧関連リンクを検出したが、同一概念・対象箇所の対応は未確定。'
                    if not valid:
                        reason='人間裁定の資料signatureが未一致または対象資料が欠損。裁定を保持して適用範囲を保留。'
                    elif ambiguous or en is None or jp is None:
                        reason='重複・不正入力または同ファイルの日英対応が曖昧。出現を選択せずレビュー。'
                    elif not same_file:
                        reason='裁定元と異なるコンテンツファイル。Chronicles・シナリオ等への波及を保留。'
                    elif direct:
                        cls='already_consistent' if matched==rec['proposed_jp'] else 'required'
                        confidence='high'; reason='人間裁定の名称、または既存evidenceで確認した同一名称用途の表示箇所。'
                    elif start is not None and any(m.start()<=start and end<=m.end() and m.end()-m.start()>end-start
                                                  and normalized(names[s]) not in jp_owners[m[0]] for m in protected):
                        cls='unrelated'; confidence='medium'
                        reason='別の既知名称の内部にある部分一致。対象語だけを取り出して置換しない。'
                    elif is_prior_different:
                        cls='unrelated'; confidence='medium'
                        reason='既知の別名称または別対象のHelpで、対象英語名の参照を確認できない。系列・日本語部分一致を適用しない。'
                    elif eheader and english_body and matched is not None:
                        # Cross-language co-occurrence is supporting evidence, not an alignment proof.
                        confidence='medium'
                        cls='recommended'
                        reason='同ファイルのゲームHelp本文に対象英語名と日本語名称が共存。文章内の対応・修飾範囲を人間が確認する。'
                        if matched==rec['proposed_jp'] and len(english_body)==1 and len(jtargets[s])==1:
                            cls='already_consistent'
                            reason='Help本文に対象英語名と採用訳が各1出現。表記は一致するが実ゲーム参照は未検証。'
                        elif matched==rec['proposed_jp']:
                            cls='review'
                            reason='採用訳と同じ表記が既にあるが、複数参照の意味対応は未確定。変更候補にはしない。'
                    elif etargets[s] and matched is not None:
                        reason='日英で語句が共存するが、ボタン/Helpの対応根拠または本文の意味対応が不足。'
                    comparison=comparison_fields(matched,rec['proposed_jp'])
                    literal_class=cls
                    if comparison['normalized_equivalent'] and cls in ('required','recommended'):
                        cls='already_consistent'
                        reason+=' 表示用改行・空白を除いた訳語は採用訳と一致。レイアウトを保持し変更不要。'
                    rows.append(dict(decision_string_id=s,decision_en=names[s],
                        current_jp=current.value if current else None,effective_jp=rec['proposed_jp'],effective_decision=rec['decision'],
                        related_string_id=other,related_type=kind,related_en=excerpt(text,etargets[s][0].start() if etargets[s] else 0),
                        related_jp=excerpt(raw,start or 0),source_path=jp.path if jp else (en.path if en else ''),source_line=jp.line if jp else None,
                        relation=basis,scope_class=cls,confidence=confidence,reason=reason,
                        reviewer_decision='',reviewer_notes='',start=start,end=end,matched_jp=matched,
                        excerpted=len(raw)>180 or len(text)>180,
                        english_source=occurrence(en) if en else [occurrence(e) for e in ens],
                        source_sha256=inputs.get(jp.path if jp else '',None),decision_signature=rec['signature'],
                        evidence_status='matches' if valid else 'stale_or_missing',change_candidate=cls in ('required','recommended'),
                        literal_scope_class=literal_class,literal_change_candidate=literal_class in ('required','recommended'),
                        **comparison,
                        conflict=False,match_basis=sorted(({'prior_evidence'} if s in pair_refs[other] else set()) |
                                                        ({'jp_alias'} if jtargets[s] else set()) | ({'english_name'} if etargets[s] else set()))))
    direct=context_overrides.load(context_path) if context_path is not None else None
    if direct and set(records)&{r['string_id'] for r in direct['records']}:
        raise ValueError('Decision ID occurs in both name and context ledgers; assign one authority')
    if direct: rows=context_overrides.merge_scope(rows,context_overrides.rows(data,direct))
    rows.sort(key=lambda r:(id_sort(r['decision_string_id']),id_sort(r['related_string_id']),r['source_path'],r['source_line'] or 0,r['start'] if r['start'] is not None else -1))
    found=conflicts(rows)
    multi=defaultdict(set)
    for r in rows: multi[r['related_string_id']].add(r['decision_string_id'])
    external={r['decision_string_id'] for r in rows if r['related_string_id']!=r['decision_string_id']}
    counts=Counter(r['scope_class'] for r in rows)
    report=dict(schema_version=2,decision_count=len(records),audited_decision_ids=sorted(records,key=id_sort),
        literal_scope_counts=dict(sorted(Counter(r['literal_scope_class'] for r in rows).items())),
        former_required_split={c:sum(r['literal_scope_class']=='required' and r['scope_class']==c for r in rows) for c in CLASSES},
        relation_statistics=relation_statistics(rows),duplicate_audit=audit_duplicates(data),
        total=len(rows),related_id_count=len(multi),scope_counts={c:counts[c] for c in CLASSES},
        no_related_decisions=sorted(set(records)-external,key=id_sort),
        no_occurrence_decisions=sorted(set(records)-{r['decision_string_id'] for r in rows},key=id_sort),
        duplicate_input_ids=sorted(duplicate_ids,key=id_sort),
        multiple_decision_references={s:sorted(v,key=id_sort) for s,v in sorted(multi.items(),key=lambda x:id_sort(x[0])) if len(v)>1},
        conflicts=found,conflict_count=len(found),scanned_jp_occurrences=scanned,
        stale_decisions=adoption['human_review']['stale_ids'],absent_source_decisions=adoption['human_review']['absent_source_ids'],
        ledger_sha256=digest(json.dumps(ledger,ensure_ascii=False,sort_keys=True)),
        aliases={s:sorted(a for a,ids in aliases.items() if s in ids) for s in sorted(records,key=id_sort)},
        deferred_adjudication_ids=sorted(deferred_adjudications,key=id_sort),
        inputs=adoption['inputs'],rows=rows)
    if direct:
        all_ids=set(records)|{r['string_id'] for r in direct['records']}
        report.update(context_override_ledger=dict(path=str(Path(context_path).resolve()),sha256=context_overrides.fingerprint(direct)),
            name_decision_count=len(records),context_decision_count=len(direct['records']),
            decision_count=len(records)+len(direct['records']),
            audited_decision_ids=sorted(set(records)|{r['string_id'] for r in direct['records']},key=id_sort),
            no_related_decisions=sorted(all_ids-external,key=id_sort),
            no_occurrence_decisions=sorted(all_ids-{r['decision_string_id'] for r in rows},key=id_sort),
            suppressed_name_rows=sum(bool(r.get('suppressed_by_context_override')) for r in rows))
    return report


def render_audit(report):
    extra=['context_signature','suppressed_by_context_override','suppression_signature'] if 'context_override_ledger' in report else []
    return tsv(report['rows'],FIELDS+extra)


def render_summary(report):
    lines=['# Phase 1C 適用範囲監査','',
           '人間裁定・source・Mod用翻訳は未変更。本文参照は日英の共存を根拠とする候補で、意味対応の最終確認は人間が行う。',
           f"裁定 {report['decision_count']}件 / 関連String ID {report['related_id_count']}件 / 出現行 {report['total']}件。",'',
           '| scope_class | 出現行数 |','|---|---:|']
    lines += [f'| {c} | {report["scope_counts"][c]} |' for c in CLASSES]
    if 'context_override_ledger' in report:
        lines += ['', '## 文脈付き全文裁定', '',
                  f"名称 {report['name_decision_count']}件 / 直接override {report['context_decision_count']}件。",
                  f"直接裁定の出現位置への名称伝播 {report['suppressed_name_rows']}行は適用せず、証拠として残す。",
                  'explicit_context_overrideのみ全文を裁定どおり使用する。他の出現へは伝播しない。',
                  '直接裁定正本: '+json.dumps(report['context_override_ledger'],ensure_ascii=False)]
    lines += ['', '## 保存値比較とレイアウト正規化', '',
              'literal比較結果・対象原文・位置を保持したまま表示用改行/空白だけを比較キーから除く。sourceのレイアウトは変更しない。',
              '保存値比較時のrequiredの再分類: '+json.dumps(report['former_required_split'],ensure_ascii=False), '',
              '| relation | 総数 | 実変更候補 | normalized-equivalent | literal already-consistent | その他 |',
              '|---|---:|---:|---:|---:|---:|']
    for relation,stats in report['relation_statistics'].items():
        lines.append('| '+relation+' | '+' | '.join(str(stats[k]) for k in ('total','actual_change_candidates','normalized_equivalent','already_consistent','review_or_other'))+' |')
    duplicates=report['duplicate_audit']
    lines += ['', '## 重複入力の監査', '',
              '値の分類: '+json.dumps(duplicates['value_counts'],ensure_ascii=False),
              '出現元の分類（値とは独立した軸）: '+json.dumps(duplicates['provenance_counts'],ensure_ascii=False),
              '同値でも優先順位を解決しない。全59組の出現位置・値の指紋・抜粋はduplicate-audit.json。', '',
              '| dataset | 内訳 |','|---|---|']
    lines += [f'| {n} | {json.dumps(v,ensure_ascii=False)} |' for n,v in duplicates['dataset_counts'].items()]
    lines += ['', '収録位置による内訳（発生理由やロード順は推測しない）:', '', '| dataset / source | 値の分類 | 組数 |', '|---|---|---:|']
    lines += [f"| {r['dataset']}: {', '.join(r['paths'])} | {r['classification']} | {r['count']} |" for r in duplicates['source_groups']]
    lines += ['', '異値を持つID（dataset単位）:','']
    for dataset in duplicates['dataset_counts']:
        ids=[r['string_id'] for r in duplicates['rows'] if r['dataset']==dataset and r['classification']=='different_values']
        if ids: lines.append('- '+dataset+': '+', '.join(ids))
    lines += ['',f"衝突 {report['conflict_count']}件。同一IDでも別の出現位置に異なる名称が必要なだけでは衝突に数えない。",
              '裁定自身以外の関連がないID: '+str(report['no_related_decisions']),
              '出現自体が見つからない裁定: '+str(report['no_occurrence_decisions']),
              'signature再確認が必要: '+str(report['stale_decisions']),
              'source欠損の裁定: '+str(report['absent_source_decisions']),
              f"複数裁定から参照される関連ID: {len(report['multiple_decision_references'])}件。全一覧はscope-metadata.json。",'',
              '## 人間が特に確認する箇所','',
              '- requiredは名称本体・確認済みHelp見出し・対応ボタン。見出しが一致しても本文が整合するとは限らない。',
              '- recommendedは同ファイルのHelp本文の日英共存。英語と日本語の各出現を自動整列したものではない。',
              '- 大学・騎兵・柵など一般名詞との重なり、複数回出現、別ユニットの修飾語はreviewで確認する。',
              '- Chronicles/キャンペーン等の別ファイルを通常名称へ自動統一しない。',
              '- ガレオン系列や通常/Royal/Eliteイェニチェリは長い名称を優先して照合し、別系列への部分置換を避ける。',
              '- 同値を含む重複入力はreview。日本語が未検出の英語参照もreviewとして残す。',
              '- 表の英文・和文は最大180文字の抜粋。start/endは原文のUnicode文字位置（半開区間）。全文はsource_path/lineまたはshow CLIで確認する。', '',
              '## 重複参照例（最大20 ID）','']
    lines += [f'- {s}: '+', '.join(ids) for s,ids in list(report['multiple_decision_references'].items())[:20]]
    lines += ['', '## 衝突', '', '```json',json.dumps(report['conflicts'],ensure_ascii=False,indent=2),'```','',
              '## 再現性', '', f"人間裁定SHA-256: {report['ledger_sha256']}",
              '入力SHA-256、全裁定ID、別名の検出規則、重複参照の全件はscope-metadata.jsonに記録。','']
    lines += ['## 裁定別の監査件数', '', '| 裁定ID | 名称 | required | recommended | review | unrelated | already_consistent |',
              '|---|---|---:|---:|---:|---:|---:|']
    groups=defaultdict(Counter); names={}
    for r in report['rows']:
        groups[r['decision_string_id']][r['scope_class']]+=1
        names[r['decision_string_id']]=r['decision_en']
    for sid in report['audited_decision_ids']:
        lines.append('| '+sid+' | '+names.get(sid,'資料欠損').replace('|','&#124;')+' | '+
                     ' | '.join(str(groups[sid][c]) for c in CLASSES)+' |')
    return '\n'.join(lines)
