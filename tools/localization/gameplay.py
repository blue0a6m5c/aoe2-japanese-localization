"""Evidence-linked name inventory, not a game-data roster or translation engine."""

from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import re

from .analysis import classify, id_sort, occurrence


ORDER = ('de_en', 'de_jp', 'hd_en', 'hd_jp', 'aoc_jp', 'aok_jp')
NAME_CATEGORIES = ('unit', 'building', 'technology', 'age', 'unknown')
FAMILIES = ('core', 'dlc', 'chronicles', 'scenario/hero', 'review-needed')
ACTION = re.compile(r'^(Create|Train|Build|Research|Upgrade(?: to)?|Advance to(?: the)?)\s+<b>(.*?)<b>')
FLAGS = ('jp_only_changed', 'legacy_stable_de_changed', 'de_new_id', 'history_incomplete',
         'missing_de_jp', 'input_ambiguity', 'short_jp', 'latin_remaining', 'same_as_english',
         'jp_collision', 'jp_label_variation', 'name_help_jp_mismatch', 'english_name_help_mismatch',
         'classification_review', 'content_family_review', 'series_review', 'series_stem_review')
FLAGS += ('historical_english_changed', 'de_name_not_in_hd_en', 'jp_heading_structure_review')
SUSPICIOUS = {'missing_de_jp', 'short_jp', 'latin_remaining', 'same_as_english', 'jp_collision',
              'jp_label_variation', 'name_help_jp_mismatch', 'english_name_help_mismatch', 'series_stem_review',
              'jp_heading_structure_review'}


def normalized(value: str) -> str:
    """For evidence linking only. Stored values and historical comparison stay raw."""
    return ' '.join(re.sub(r'<[^>]*>', '', value.replace('\\n', ' ')).split())


def jp_key(value: str) -> str:
    return re.sub(r'\s+', '', normalized(value))


def short_label(value: str) -> bool:
    plain = normalized(value)
    return (bool(plain) and len(plain) <= 80 and len(plain.split()) <= 12
            and not re.search(r'[<>%{}]|[.!?;:=]', plain)
            and not value.startswith(('Create ', 'Build ', 'Research ', 'Upgrade ', 'Train '))
            and not plain.isdecimal())


def load_rules(path: Path | None = None) -> tuple[dict, str]:
    data = (path or Path(__file__).with_name('gameplay_rules.json')).read_bytes()
    return json.loads(data), hashlib.sha256(data).hexdigest()


def action_category(action: str, text: str) -> tuple[str, str | None]:
    body = text.split('\\n', 1)[-1].split('\\n', 1)[0].split('. ', 1)[0]
    if action.startswith('Advance to'):
        return 'age', None
    if action in ('Create', 'Train'):
        return 'unit', 'hero/scenario_unit' if re.search(r'\bHero\b', body) else (
            'unique_unit' if re.search(r'\bunique\b', body, re.I) else None)
    if action == 'Build':
        # Rams/ships are built too: the verb alone is insufficient.
        if re.match(r'Used to (?:train|research|build|deposit)', body, re.I):
            return 'building', None
        if re.search(r'\b(Siege Weapon|Ship|Warship|Boat|Unit)\b|^Gathers food', body, re.I):
            return 'unit', None
        if re.search(r'\b(Used to|building|structure|gathering point|Constructed|Construct over|tower|wall|gate|Wonder of the World|food source)\b', body, re.I):
            return 'building', None
        return 'unknown', None
    if action.startswith('Upgrade'):
        return 'technology', 'upgrade'
    if action == 'Research':
        return 'technology', None
    return 'unknown', None


def cell(dataset, sid: str) -> dict:
    if dataset is None:
        return dict(state='dataset_unavailable', occurrences=[])
    entries = dataset.entries.get(sid, [])
    state = 'missing' if not entries else 'resolved' if dataset.resolved(sid) else 'ambiguous'
    return dict(state=state, occurrences=[occurrence(e, True) for e in entries],
                empty_resource_slots=[occurrence(e, False) for e in dataset.empty_slots.get(sid, [])])


def build_inventory(datasets, rules=None):
    if any(i.kind in ('encoding_error', 'pe_error') for d in datasets.values() for i in d.issues):
        raise ValueError('Incomplete input cannot produce a gameplay inventory; inspect issues')
    if rules is None:
        rules, rule_hash = load_rules()
    else:
        rule_hash = hashlib.sha256(json.dumps(rules, sort_keys=True).encode()).hexdigest()
    en = datasets['de_en']
    historical_names = {normalized(e.value) for v in datasets['hd_en'].entries.values() for e in v if short_label(e.value)}
    headings, labels = [], defaultdict(list)
    unique_techs = defaultdict(list)
    for sid in sorted(en.entries, key=id_sort):
        for entry in en.entries[sid]:
            tech_section = re.search(r'<b>Unique Techs:<b>\\n(.*?)(?:\\n\\n|$)', entry.value)
            if tech_section:
                for tech in re.findall(r'(?:^|\\n)• (.*?) \(', tech_section[1]):
                    unique_techs[(entry.path, normalized(tech))].append(entry)
            match = ACTION.match(entry.value)
            if match:
                heading = normalized(match[2])
                heading = rules.get('heading_aliases', {}).get(heading, heading)
                category, subtype = action_category(match[1], entry.value)
                headings.append(dict(id=sid, entry=entry, name=heading, action=match[1],
                                     category=category, subtype=subtype))
            elif short_label(entry.value):
                labels[(entry.path, normalized(entry.value))].append(entry)

    evidence = defaultdict(list)
    unmatched = []
    for h in headings:
        matches = labels.get((h['entry'].path, h['name']), [])
        # Exact same-file name matches cover full labels and compact aliases.
        for entry in matches:
            direct = (h['id'].isdecimal() and entry.string_id.isdecimal()
                      and int(h['id']) - int(entry.string_id) in rules['name_to_help_offsets'])
            evidence[entry.string_id].append(dict(h, relation='verified_offset_and_label' if direct else 'same_file_label'))
        # Observed full-label offset is a candidate only when text does NOT agree.
        if h['id'].isdecimal():
            candidate = str(int(h['id']) - rules['name_to_help_offsets'][0])
            for entry in en.entries.get(candidate, []):
                if entry.path == h['entry'].path and short_label(entry.value) and normalized(entry.value) != h['name']:
                    evidence[candidate].append(dict(h, relation='unverified_offset_candidate'))
        if not matches:
            unmatched.append(dict(help_id=h['id'], path=h['entry'].path, line=h['entry'].line,
                                  heading=h['name'], reason='No exact same-file short label'))
    for relation in rules.get('review_links', []):
        for h in headings:
            if h['id'] == relation['help_id']:
                for entry in en.entries.get(relation['name_id'], []):
                    if entry.path == h['entry'].path and short_label(entry.value):
                        evidence[entry.string_id].append(dict(h, relation='reviewed_layout_candidate'))

    rows = []
    for sid in sorted(evidence, key=id_sort):
        links = evidence[sid]
        verified = [h for h in links if h['relation'] == 'verified_offset_and_label']
        matched = [h for h in links if h['relation'] in ('verified_offset_and_label', 'same_file_label')]
        chosen = verified or matched or links
        categories = {h['category'] for h in chosen}
        category = next(iter(categories)) if len(categories) == 1 and matched else 'unknown'
        flags = set()
        if any(h['relation'] in ('unverified_offset_candidate', 'reviewed_layout_candidate') for h in links):
            flags.add('english_name_help_mismatch')
        if category == 'unknown' or not verified:
            flags.add('classification_review')
        subtypes = sorted({h['subtype'] for h in chosen if h['subtype']})
        entry = en.resolved(sid)
        label = normalized(entry.value) if entry else ''
        tech_refs = unique_techs.get((entry.path, label), []) if entry else []
        if category == 'technology' and tech_refs:
            subtypes.append('unique_technology')
        if category == 'technology' and label.endswith(' Age'):
            category, subtypes = 'age', []
        if 'upgrade' in subtypes:
            target_categories = {h['category'] for h in matched if not h['action'].startswith('Upgrade')}
            if target_categories == {'unit'}:
                subtypes = ['unit_upgrade']
            elif target_categories == {'building'}:
                subtypes = ['building_upgrade']

        paths = {Path(h['entry'].path).name for h in chosen}
        family_candidates = {rules.get('file_families', {}).get(p,
                             'scenario/hero' if '-campaign-' in p else 'review-needed') for p in paths}
        packs = sorted({pack for pack, ids in rules.get('dlc_help_ids', {}).items()
                        if any(h['id'] in ids and Path(h['entry'].path).name == 'key-value-strings-utf8.txt' for h in chosen)})
        packs = sorted(set(packs) | {pack for pack, ids in rules.get('dlc_civ_ids', {}).items()
                                   if any(e.string_id in ids for e in tech_refs)})
        if packs:
            family = 'dlc'
        elif len(family_candidates) == 1 and 'review-needed' not in family_candidates:
            family = next(iter(family_candidates))
        elif paths == {'key-value-strings-utf8.txt'} and verified:
            family = 'scenario/hero' if 'hero/scenario_unit' in subtypes else 'core'
        else:
            family = 'review-needed'
            flags.add('content_family_review')
        values = {n: cell(datasets.get(n), sid) for n in ORDER}
        resolved = {n: datasets[n].resolved(sid) if n in datasets else None for n in ORDER}
        if any(c['state'] == 'ambiguous' for c in values.values()):
            flags.add('input_ambiguity')
        if values['de_jp']['state'] == 'missing':
            flags.add('missing_de_jp')
        if 'jp_only_changed' in classify(sid, datasets):
            flags.add('jp_only_changed')
        history = ('hd_en', 'hd_jp', 'aoc_jp', 'aok_jp')
        complete_history = all(n in datasets for n in history)
        if not complete_history:
            flags.add('history_incomplete')
        if complete_history and all(not datasets[n].entries.get(sid) and sid not in datasets[n].invalid_ids for n in history):
            flags.add('de_new_id')
        if label and label not in historical_names:
            flags.add('de_name_not_in_hd_en')
        stable_english = (resolved['hd_en'] and resolved['de_en'] and resolved['hd_en'].value == resolved['de_en'].value)
        if resolved['hd_en'] and resolved['de_en'] and not stable_english:
            flags.add('historical_english_changed')
        legacy = [n for n in ('aok_jp', 'aoc_jp') if resolved[n] is not None]
        if (legacy and stable_english and resolved['hd_jp'] and resolved['de_jp']
                and not any(values[n]['state'] == 'ambiguous' for n in ('aok_jp', 'aoc_jp'))
                and all(resolved[n].value == resolved['hd_jp'].value for n in legacy)
                and resolved['hd_jp'].value != resolved['de_jp'].value):
            flags.add('legacy_stable_de_changed')
        jp = resolved['de_jp']
        disagreements = []
        if jp:
            clean = jp_key(jp.value)
            if len(clean) <= 1:
                flags.add('short_jp')
            if re.search('[A-Za-z]{3,}', clean):
                flags.add('latin_remaining')
            if label and normalized(jp.value) == label:
                flags.add('same_as_english')
            for h in chosen:
                help_jp = datasets['de_jp'].resolved(h['id'])
                title = re.match(r'<b>(.*?)<b>', help_jp.value.lstrip()) if help_jp else None
                if help_jp and not title and h['relation'] in ('verified_offset_and_label', 'same_file_label'):
                    flags.add('jp_heading_structure_review')
                if title and jp_key(title[1]) != clean and h['relation'] != 'unverified_offset_candidate':
                    disagreements.append(dict(help_id=h['id'], jp_heading=title[1], path=help_jp.path, line=help_jp.line))
            if disagreements:
                flags.add('name_help_jp_mismatch')
        full_name = any(h['relation'] == 'verified_offset_and_label' and h['id'].isdecimal() and sid.isdecimal()
                        and int(h['id']) - int(sid) == 21000 for h in links)
        rows.append(dict(string_id=sid, category=category, subcategories=subtypes,
                         content_family=family, content_packs=packs,
                         content_family_confidence='source-profile' if family == 'core' else
                             'review-needed' if family == 'review-needed' else 'reviewed-source-context',
                         gameplay_availability='review-needed',
                         confidence='corroborated' if verified and category != 'unknown' else 'review-needed',
                         label_role='full_name' if full_name else 'compact_name' if verified else 'alias_or_unverified',
                         datasets=values, flags=flags, series=[], related_ids=[], legacy_basis=legacy,
                         unique_technology_evidence=[dict(id=e.string_id, path=e.path, line=e.line) for e in tech_refs],
                         evidence=[dict(help_id=h['id'], path=h['entry'].path, line=h['entry'].line,
                                        action=h['action'], category=h['category'], relation=h['relation']) for h in links],
                         jp_heading_disagreements=disagreements))

    by_id = {r['string_id']: r for r in rows}
    collisions, variations = defaultdict(list), defaultdict(list)
    for r in rows:
        sid = r['string_id']
        e, j = en.resolved(sid), datasets['de_jp'].resolved(sid)
        if e and j and r['category'] != 'unknown' and r['content_family'] != 'review-needed':
            context = (r['content_family'], e.path, r['category'])
            collisions[(*context, jp_key(j.value))].append(r)
            variations[(*context, normalized(e.value))].append(r)
    for group in collisions.values():
        if len({normalized(en.resolved(r['string_id']).value) for r in group}) > 1:
            for r in group:
                r['flags'].add('jp_collision')
                r['related_ids'] += [s['string_id'] for s in group if s is not r]
    for group in variations.values():
        if len({jp_key(datasets['de_jp'].resolved(r['string_id']).value) for r in group}) > 1:
            for r in group:
                r['flags'].add('jp_label_variation')
                r['related_ids'] += [s['string_id'] for s in group if s is not r]

    series = dict(rules.get('series', {}))
    primary_units = {(r['content_family'], en.resolved(r['string_id']).path, normalized(en.resolved(r['string_id']).value)): r
                     for r in rows if r['category'] == 'unit' and r['confidence'] == 'corroborated'
                     and en.resolved(r['string_id']) and r['string_id'].isdecimal()
                     and any(h['relation'] == 'verified_offset_and_label' and int(h['help_id']) - int(r['string_id']) == 21000 for h in r['evidence'])}
    for (family, path, name), r in sorted(primary_units.items()):
        if name.startswith('Elite ') and (family, path, name[6:]) in primary_units:
            base = primary_units[(family, path, name[6:])]
            series[f'elite:{family}:{base["string_id"]}'] = [base['string_id'], r['string_id']]
    for name, ids in series.items():
        members = [by_id[sid] for sid in ids if sid in by_id]
        if (len(members) < 2 or len({r['content_family'] for r in members}) != 1
                or len({en.resolved(r['string_id']).path for r in members if en.resolved(r['string_id'])}) != 1):
            continue
        for r in members:
            r['series'].append(name)
            r['flags'].add('series_review')
        if name.startswith('elite:'):
            a, b = (datasets['de_jp'].resolved(r['string_id']) for r in members)
            if a and b and jp_key(a.value) not in jp_key(b.value):
                for r in members:
                    r['flags'].add('series_stem_review')
    for r in rows:
        r['flags'] = sorted(r['flags'])
        r['related_ids'] = sorted(set(r['related_ids']), key=id_sort)
        r['series'].sort()
        r['review_candidate'] = bool(set(r['flags']) - {'de_new_id', 'de_name_not_in_hd_en', 'series_review'})
        r['suspicious_candidate'] = bool(set(r['flags']) & SUSPICIOUS)
        r['priority'] = ('high' if set(r['flags']) & (SUSPICIOUS - {'short_jp'}) else
                         'medium' if set(r['flags']) & {'jp_only_changed', 'legacy_stable_de_changed'} else 'low')
    return dict(schema_version=1, rules_sha256=rule_hash, rows=rows,
                coverage=dict(action_headings=len(headings), unmatched_action_headings=unmatched,
                              scope='Source-evidenced candidates; not a complete skirmish roster'),
                statistics=inventory_stats(rows))


def inventory_stats(rows):
    return dict(total=len(rows), categories=dict(sorted(Counter(r['category'] for r in rows).items())),
                subcategories=dict(sorted(Counter(s for r in rows for s in r['subcategories']).items())),
                families=dict(sorted(Counter(r['content_family'] for r in rows).items())),
                label_roles=dict(sorted(Counter(r['label_role'] for r in rows).items())),
                full_name_categories=dict(sorted(Counter(r['category'] for r in rows if r['label_role']=='full_name').items())),
                review_candidates=sum(r['review_candidate'] for r in rows),
                suspicious_candidates=sum(r['suspicious_candidate'] for r in rows),
                flags=dict(sorted(Counter(f for r in rows for f in r['flags']).items())))


def filter_rows(rows, *, category=None, family=None, flag=None, pack=None, series=None, primary=False,
                review=False, suspicious=False, string_id=None):
    return [r for r in rows if (not category or r['category'] == category)
            and (not family or r['content_family'] == family) and (not flag or flag in r['flags'])
            and (not pack or pack in r['content_packs']) and (not series or series in r['series'])
            and (not primary or r['label_role'] == 'full_name')
            and (not review or r['review_candidate']) and (not suspicious or r['suspicious_candidate'])
            and (string_id is None or r['string_id'] == string_id)]


def render_tsv(rows):
    """Quoted JSON values / ambiguity objects; provenance in a separate column."""
    output = io.StringIO(newline='')
    writer = csv.writer(output, delimiter='\t', lineterminator='\n')
    fields = ['String ID', 'Category', 'Subcategories', 'Content Family', 'Content Packs', 'Confidence',
              *[n.upper().replace('_', ' ') for n in ORDER], 'Flags', 'Priority', 'Label Role', 'Series', 'Related IDs', 'Evidence', 'Provenance']
    writer.writerow(fields)
    for r in rows:
        cells = []
        for n in ORDER:
            c = r['datasets'][n]
            # JSON strings/objects or fixed status words, never spreadsheet formulas.
            cells.append(json.dumps(c['occurrences'][0]['value'], ensure_ascii=False) if c['state']=='resolved'
                         else c['state'] if not c['occurrences'] else json.dumps(c, ensure_ascii=False, separators=(',', ':')))
        writer.writerow([r['string_id'], r['category'], ','.join(r['subcategories']), r['content_family'],
                         ','.join(r['content_packs']), r['confidence'], *cells, ','.join(r['flags']), r['priority'], r['label_role'],
                         ','.join(r['series']), ','.join(r['related_ids']),
                         json.dumps(r['evidence'], ensure_ascii=False, separators=(',', ':')),
                         json.dumps({n:[{k:v for k,v in e.items() if k!='value'} for e in r['datasets'][n]['occurrences']] for n in ORDER},ensure_ascii=False,separators=(',',':'))])
    return output.getvalue()
