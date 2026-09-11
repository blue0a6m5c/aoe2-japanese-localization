"""Read-only real-source regressions: all patching is in-memory, never Mod output."""
import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from tests.local_pipeline import inputs
from tools.localization import context_overrides, layout_plan, patch_plan, phase2a_patch_plan, scope
from tools.localization.analysis import Dataset
from tools.localization.parser import HEADER, parse_text
from tools.localization.source_states import (evidence_data, evidence_entry, fingerprint, _certificate,
                                               VALID_BEFORE, ALREADY_APPLIED)


class SyntheticStateTests(unittest.TestCase):
    def test_certificate_format_is_portable_but_content_tamper_rejected(self):
        from tools.localization.source_states import CERTIFICATE
        original=json.loads(CERTIFICATE.read_text(encoding='utf8'))
        try:
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'certificate.json'
                with patch('tools.localization.source_states.CERTIFICATE',path):
                    for newline in ('\n','\r\n'):
                        path.write_bytes(json.dumps(original,ensure_ascii=False,indent=1).replace('\n',newline).encode('utf8'))
                        _certificate.cache_clear()
                        self.assertEqual(len(_certificate()[1]),528)
                    original['records'][0]['after_sha256']='0'*64
                    path.write_text(json.dumps(original),encoding='utf8')
                    _certificate.cache_clear()
                    with self.assertRaisesRegex(ValueError,'certificate hash mismatch'):
                        _certificate()
        finally:
            _certificate.cache_clear()

    def test_exact_span_after_preserves_surroundings_and_technical_tokens(self):
        from tools.localization.parser import Entry
        from tools.localization.restoration import digest
        before = r'<b>Old<b> %s\nSuffix'
        after = r'<b>New<b> %s\nSuffix'
        record = dict(string_id='synthetic',source_path='synthetic.txt',source_line=1,
                      before_sha256=digest(before),after_sha256=digest(after),reverse_edits=[[3,6,'Old']])
        with patch('tools.localization.source_states._certificate', return_value=({}, {'synthetic':record})):
            original = Entry('synthetic',before,'synthetic.txt',1)
            self.assertEqual(evidence_entry(original),(original,VALID_BEFORE))
            self.assertEqual(evidence_entry(replace(original,value=after)),(original,ALREADY_APPLIED))
            for drift in (after.replace('%s','%d'),after.replace('<b>','<i>',1),
                          after.replace(r'\n',r'\t'),after+'X','X'+after,after.replace('New','Other')):
                with self.subTest(drift=drift), self.assertRaisesRegex(ValueError,'STALE_OR_CONFLICT'):
                    evidence_entry(replace(original,value=drift))


def virtual_values(data, changes, dataset='de_jp'):
    """Replace specified whole values at exact occurrences in memory, then reparse."""
    result = {**data, dataset: Dataset(dataset)}
    for source in data[dataset].files:
        lines = re.split(r'(\r\n|\n|\r)', source.raw_bytes.decode('utf-8'))
        for entry in source.entries:
            if entry.string_id not in changes:
                continue
            index = 2 * (entry.line - 1)
            raw = lines[index]
            offset = 1 if index == 0 and raw.startswith('\ufeff') else 0
            start = HEADER.match(raw, offset).end()
            lines[index] = raw[:start] + changes[entry.string_id] + raw[start + len(entry.value):]
        raw = ''.join(lines).encode('utf8')
        parsed = parse_text(raw.decode('utf-8-sig'), source.path)
        parsed.raw_bytes = raw
        parsed.sha256 = hashlib.sha256(raw).hexdigest()
        parsed.size_bytes = len(raw)
        parsed.bom = source.bom
        result[dataset].add(parsed)
    return result


def pipeline(data, item, wording=None, layout=None):
    wording = item['formal_ledger'] if wording is None else wording
    layout = item['human'] if layout is None else layout
    audit = scope.build_scope(data, item['ledger'], context_path=context_overrides.DEFAULT_PATH)
    baseline = layout_plan.integrate(data, item['ledger'], audit['rows'],
                                    {k:v for k,v in audit.items() if k != 'rows'}, {}, layout)
    phase2a = phase2a_patch_plan.build_plan(data, wording, layout)
    return audit, baseline, phase2a


class SourceStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.item = inputs()
        cls.data = cls.item['data']
        cls.before = cls.item['plan']
        cls.phase2a = phase2a_patch_plan.build_plan(cls.data, cls.item['formal_ledger'], cls.item['human'])
        cls.ops = cls.before['operations'] + cls.phase2a['operations']
        cls.after = virtual_values(cls.data, {o['string_id']:o['after'] for o in cls.ops})

    def test_before_all_fields_match_pre_fix_certificate(self):
        _, records = _certificate()
        self.assertEqual((len(self.before['operations']), len(self.ops)), (387,528))
        self.assertEqual(len({o['string_id'] for o in self.ops}), 528)
        self.assertFalse(self.before['blocked'] or self.phase2a['blocked'])
        self.assertEqual(self.before['statistics']['conflicts'], 0)
        self.assertEqual(self.before['statistics']['duplicate_id_patch_operations'], 0)
        for op in self.ops:
            self.assertEqual(fingerprint(op), records[op['string_id']]['operation_sha256'])

    def test_after_two_plans_are_zero_and_do_not_mutate_input(self):
        before_hashes = [(f.path, f.sha256, hashlib.sha256(f.raw_bytes).hexdigest())
                         for f in self.after['de_jp'].files]
        before_entries = copy.deepcopy(self.after['de_jp'].entries)
        for _ in range(2):
            audit, baseline, phase2a = pipeline(self.after, self.item)
            self.assertFalse(audit['stale_decisions'])
            self.assertEqual(audit['conflict_count'], 0)
            self.assertFalse(baseline['operations'] or phase2a['operations'])
            self.assertFalse(baseline['blocked'] or phase2a['blocked'])
            self.assertEqual(baseline['statistics']['already_applied'], 387)
            self.assertEqual(baseline['statistics']['conflicts'], 0)
            self.assertEqual(baseline['statistics']['duplicate_id_patch_operations'], 0)
            self.assertEqual(phase2a['statistics']['already_matching'], 249)
            self.assertTrue(all(t['status']=='already_matching' for t in phase2a['targets']))
        self.assertEqual(before_entries, self.after['de_jp'].entries)
        self.assertEqual(before_hashes, [(f.path,f.sha256,hashlib.sha256(f.raw_bytes).hexdigest())
                                        for f in self.after['de_jp'].files])

    def test_mixed_state_remaining_operations_exact_and_third_value_rejected(self):
        selected = self.ops[::2]
        mixed = virtual_values(self.data, {o['string_id']:o['after'] for o in selected})
        _, baseline, phase2a = pipeline(mixed, self.item)
        remaining = baseline['operations'] + phase2a['operations']
        self.assertEqual(remaining, [o for o in self.ops if o not in selected])
        self.assertEqual(len(remaining),264)
        self.assertFalse(baseline['blocked'] or phase2a['blocked'])
        bad = virtual_values(mixed, {remaining[0]['string_id']:remaining[0]['before']+'X'})
        with self.assertRaisesRegex(ValueError, 'STALE_OR_CONFLICT'):
            evidence_data(bad)

    def test_context_and_phase1b_and_phase2a_validators_accept_after(self):
        from tools.localization.adoption import signature
        from tools.localization.human_reviews import source_bindings_match
        ledger = context_overrides.load()
        context_overrides.validate_source(self.after, ledger)
        self.assertTrue(all(r['scope_class']=='already_consistent'
                            for r in context_overrides.rows(self.after, ledger)))
        for record in self.item['formal_ledger']['records']:
            self.assertEqual(signature(self.after, record['string_id'], record['help_ids']), record['signature'])
            if record.get('binding_mode'):
                self.assertTrue(source_bindings_match(record, self.after))
        layouts = phase2a_patch_plan.validate_layout_records(self.after, self.item['formal_ledger'], self.item['human'])
        self.assertEqual(len(layouts),17)
        for sid in ('14594','17481'):
            self.assertEqual(self.after['de_jp'].resolved(sid).value,layouts[sid]['replacement'])

    def test_negative_after_value_drift(self):
        full = next(o for o in self.ops if o['replacement_type']=='full_value')
        span = next(o for o in self.ops if o['replacement_type']=='span'
                    and o['matched_span'][0]>0 and o['matched_span'][1]<len(o['before']))
        start = span['matched_span'][0]
        end = start + len(span['replacement'])
        cases = {
            'full_one_character': (full, 'X'+full['after'][1:]),
            'span_target': (span, span['after'][:start]+'X'+span['after'][start+1:]),
            'span_prefix': (span, 'X'+span['after'][1:]),
            'span_suffix': (span, span['after'][:end]+'X'+span['after'][end+1:]),
            'placeholder': (span, span['after']+'%s'),
            'markup': (span, span['after']+'<b>'),
            'technical_escape': (span, span['after']+r'\n'),
        }
        markup = next(o for o in self.ops if '<b>' in o['after'])
        escape = next(o for o in self.ops if r'\n' in o['after'])
        cases['existing_markup_change'] = (markup, markup['after'].replace('<b>','<i>',1))
        cases['existing_escape_change'] = (escape, escape['after'].replace(r'\n',r'\t',1))
        for name, (op, value) in cases.items():
            with self.subTest(name=name):
                bad = virtual_values(self.after, {op['string_id']:value})
                with self.assertRaisesRegex(ValueError, 'STALE_OR_CONFLICT'):
                    pipeline(bad, self.item)

    def test_third_value_in_otherwise_before_snapshot_rejected(self):
        op=next(o for o in self.ops if o['replacement_type']=='span')
        bad=virtual_values(self.data,{op['string_id']:op['before']+'X'})
        with self.assertRaisesRegex(ValueError,'STALE_OR_CONFLICT'):
            pipeline(bad,self.item)

    def test_after_scope_tampering_rejected(self):
        audit=scope.build_scope(self.after,self.item['ledger'],context_path=context_overrides.DEFAULT_PATH)
        raw_plan=patch_plan.build_plan(self.after,self.item['ledger'],audit['rows'],audit)
        self.assertFalse(raw_plan['operations'])
        self.assertTrue(all(b['reasons']==['technical_structure_changed'] for b in raw_plan['blocked']))
        row=next(r for r in audit['rows'] if r.get('source_state')==ALREADY_APPLIED)
        row['effective_jp']='unapproved'
        with self.assertRaisesRegex(ValueError,'scope audit mismatch'):
            layout_plan.integrate(self.after,self.item['ledger'],audit['rows'],audit,{},self.item['human'])

    def test_context_after_must_match_current_proposal(self):
        ledger=copy.deepcopy(context_overrides.load())
        record=next(r for r in ledger['records'] if r['string_id'] in {o['string_id'] for o in self.ops})
        record['proposed_jp']+='X'
        record['binding_signature']=context_overrides.record_signature(record)
        with self.assertRaisesRegex(ValueError,'Context expected after value mismatch'):
            context_overrides.validate_source(self.after,ledger)

    def test_negative_english_identity_concept_and_occurrence(self):
        target = self.phase2a['operations'][0]['string_id']
        en = self.after['de_en'].resolved(target)
        bad = virtual_values(self.after, {target:en.value+'X'}, 'de_en')
        with self.assertRaisesRegex(ValueError, 'STALE_OR_CONFLICT'):
            pipeline(bad,self.item)
        for mutation in ('duplicate','line','path','index'):
            with self.subTest(mutation=mutation):
                bad = copy.deepcopy(self.after)
                entry = bad['de_jp'].entries[target][0]
                if mutation=='duplicate': bad['de_jp'].entries[target].append(entry)
                elif mutation=='line': bad['de_jp'].entries[target][0]=replace(entry,line=entry.line+1)
                elif mutation=='path': bad['de_jp'].entries[target][0]=replace(entry,path='de_jp/wrong.txt')
                else: bad['de_jp'].entries['unexpected']=[entry]
                with self.assertRaisesRegex(ValueError,'STALE_OR_CONFLICT'):
                    evidence_data(bad)
        wording=copy.deepcopy(self.item['formal_ledger'])
        record=next(r for r in wording['records'] if r.get('binding_mode'))
        record['concept_id']='wrong-concept'
        with self.assertRaises(ValueError):
            phase2a_patch_plan.build_plan(self.after,wording,self.item['human'])
        from tools.localization.human_reviews import source_bindings_match, target_scope_signature
        record['target_scope_signature']=target_scope_signature(record)
        self.assertFalse(source_bindings_match(record,self.after))
        with self.assertRaises(ValueError):
            phase2a_patch_plan.build_plan(self.after,wording,self.item['human'])

    def test_unrelated_file_bytes_drift_rejected(self):
        bad=copy.deepcopy(self.after)
        source=bad['de_jp'].files[0]
        source.raw_bytes += b'\r\n// unexpected comment\r\n'
        source.sha256=hashlib.sha256(source.raw_bytes).hexdigest()
        with self.assertRaisesRegex(ValueError,'restored source hash'):
            evidence_data(bad)


if __name__ == '__main__':
    unittest.main()
