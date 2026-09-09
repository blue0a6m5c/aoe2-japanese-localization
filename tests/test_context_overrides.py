"""Synthetic context ownership and optional current pipeline regressions."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from tests.test_patch_plan import fixture
from tools.localization import context_overrides as contexts, scope, patch_plan
from tools.localization.adoption import signature


def direct_ledger(data):
    sid='26001';current=data['de_jp'].resolved(sid).value
    record=dict(string_id=sid,expected_de_english=data['de_en'].resolved(sid).value,
                proposed_jp=current.replace('新走者','旧走者').replace('説明は保持。','人間の本文裁定。'),
                decision='revise',notes='Synthetic full-text human decision',help_ids=[],
                signature=signature(data,sid,[]),kind='context_full_value',context='Synthetic context')
    record['target']=contexts.binding(data,record)
    record['binding_signature']=contexts.record_signature(record)
    return dict(schema_version=1,authority='explicit_context_decisions',records=[record])


class ContextOverrideTests(unittest.TestCase):
    def setUp(self):
        self.data,self.names,_=fixture()
        self.direct=direct_ledger(self.data)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'contexts.json';self.save()

    def save(self):
        self.path.write_text(json.dumps(self.direct,ensure_ascii=False),encoding='utf8')

    def audit(self):
        return scope.build_scope(self.data,self.names,context_path=self.path)

    def test_full_value_owns_only_bound_occurrence_and_is_not_propagated(self):
        before=copy.deepcopy((self.data,self.names,self.direct))
        audit=self.audit();again=self.audit()
        self.assertEqual(scope.render_audit(audit),scope.render_audit(again))
        self.assertEqual(audit['conflict_count'],0)
        rows=audit['rows'];suppressed=[r for r in rows if r.get('suppressed_by_context_override')]
        self.assertTrue(suppressed)
        self.assertTrue(all(not r['change_candidate'] for r in suppressed))
        plan=patch_plan.build_plan(self.data,self.names,rows,audit)
        self.assertEqual(plan['statistics']['patch_operations'],2)
        self.assertEqual(plan['statistics']['conflicts'],0)
        help_op=next(o for o in plan['operations'] if o['string_id']=='26001')
        self.assertEqual(help_op['after'],self.direct['records'][0]['proposed_jp'])
        self.assertEqual(help_op['replacement_type'],'full_value')
        self.assertEqual(help_op['evidence'][0]['context_signature'],self.direct['records'][0]['binding_signature'])
        self.assertEqual(patch_plan.tokens(help_op['before']),patch_plan.tokens(help_op['after']))
        self.assertEqual((self.data,self.names,self.direct),before)

    def test_stale_source_english_signature_location_and_tokens_fail_closed(self):
        original=copy.deepcopy(self.direct)
        for field,value in [('signature','stale'),('expected_de_english','different'),('proposed_jp','invalid <cost>')]:
            with self.subTest(field=field):
                self.direct=copy.deepcopy(original);r=self.direct['records'][0];r[field]=value
                r['binding_signature']=contexts.record_signature(r);self.save()
                with self.assertRaises(ValueError):self.audit()
        for field,value in [('source_line',999),('source_sha256','stale'),('current_value_sha256','stale')]:
            with self.subTest(field=field):
                self.direct=copy.deepcopy(original);r=self.direct['records'][0];r['target'][field]=value
                r['binding_signature']=contexts.record_signature(r);self.save()
                with self.assertRaises(ValueError):self.audit()

    def test_duplicate_context_id_or_source_occurrence_fails_closed(self):
        self.direct['records']*=2;self.save()
        with self.assertRaises(ValueError):self.audit()
        self.direct['records']=self.direct['records'][:1];self.save()
        self.data['de_jp'].entries['26001']*=2
        with self.assertRaises(ValueError):self.audit()

    def test_ledger_namespaces_must_not_overlap(self):
        self.names['records'].append(copy.deepcopy(self.direct['records'][0]))
        with self.assertRaises(ValueError):self.audit()

    def test_scope_suppression_and_full_text_tampering_rejected(self):
        audit=self.audit()
        for change in ('suppression','text','omission','descriptor'):
            with self.subTest(change=change):
                bad=copy.deepcopy(audit)
                if change=='suppression':
                    next(r for r in bad['rows'] if r.get('suppressed_by_context_override'))['suppression_signature']='bad'
                elif change=='text':
                    next(r for r in bad['rows'] if r['relation']==contexts.RELATION)['effective_jp']='bad'
                elif change=='omission':bad['rows']=[r for r in bad['rows'] if r['relation']!=contexts.RELATION]
                else:bad['context_override_ledger']['sha256']='bad'
                with self.assertRaises(ValueError):patch_plan.build_plan(self.data,self.names,bad['rows'],bad)

    def test_record_change_after_audit_invalidates_plan(self):
        audit=self.audit();r=self.direct['records'][0];r['notes']='changed'
        r['binding_signature']=contexts.record_signature(r);self.save()
        with self.assertRaises(ValueError):patch_plan.build_plan(self.data,self.names,audit['rows'],audit)

    def test_keep_de_direct_record_and_explicit_layout_are_not_name_inference(self):
        r=self.direct['records'][0];current=self.data['de_jp'].resolved('26001').value
        r['decision']='keep_de';r['proposed_jp']=current
        r['binding_signature']=contexts.record_signature(r);self.save()
        audit=self.audit()
        row=next(r for r in audit['rows'] if r['relation']==contexts.RELATION)
        self.assertEqual(row['scope_class'],'already_consistent')
        plan=patch_plan.build_plan(self.data,self.names,audit['rows'],audit)
        self.assertEqual([o['string_id'] for o in plan['operations']],['5001'])
        r['decision']='revise';r['proposed_jp']=current.replace('説明','説 明')
        r['binding_signature']=contexts.record_signature(r);self.save()
        audit=self.audit();plan=patch_plan.build_plan(self.data,self.names,audit['rows'],audit)
        row=next(r for r in audit['rows'] if r['relation']==contexts.RELATION)
        self.assertTrue(row['normalized_equal'])
        self.assertEqual(row['scope_class'],'required')
        self.assertEqual(next(o['after'] for o in plan['operations'] if o['string_id']=='26001'),r['proposed_jp'])

    def test_missing_explicit_ledger_does_not_fall_back_to_names(self):
        self.path.unlink()
        with self.assertRaises(FileNotFoundError):self.audit()

    def test_current_28_targets_and_no_global_rocket_substitution(self):
        from tests.local_pipeline import inputs,payload
        item=inputs();audit=item['audit'];plan=item['plan']
        self.assertEqual((audit['name_decision_count'],audit['context_decision_count'],audit['decision_count']),(104,29,133))
        self.assertEqual((audit['conflict_count'],plan['statistics']['conflicts'],plan['statistics']['blocked_locations']),(0,0,0))
        expected_ids=set('5064 5065 6064 6065 7432 7470 8432 8438 8467 8470 14064 14065 17432 17470 19285 19476 26064 26065 28432 28438 28467 28470 46709 120155 120167 120201 170300 IDS_CIVTIPS_52_3'.split())
        records={r['string_id']:r for r in item['ledger']['records']+contexts.load()['records']}
        operations={o['string_id']:o for o in plan['operations']}
        self.assertTrue(expected_ids<=set(records))
        for sid in expected_ids:self.assertEqual(operations[sid]['after'],records[sid]['proposed_jp'])
        self.assertTrue({'7438','17438'}<=set(operations))
        from tools.localization.parser import parse_text
        bundle=payload()[0]
        parsed=parse_text(bundle['files']['resources/jp/strings/key-value/key-value-strings-utf8.txt'].decode('utf-8-sig'))
        output={(e.line,e.string_id):e.value for e in parsed.entries}
        for sid,entries in item['data']['de_jp'].entries.items():
            for e in entries:
                if e.path=='de_jp/key-value-strings-utf8.txt' and sid not in operations and 'ロケット' in e.value:
                    self.assertEqual(output[(e.line,sid)],e.value)
        # The current main-file inventory has no unpatched rocket occurrences;
        # synthetic coverage below protects unrelated references separately.

    def test_unrelated_rocket_occurrence_is_not_changed(self):
        from tools.localization.parser import Entry,ParsedFile
        from tools.localization.restoration import digest
        self.data,self.names,_=fixture('Synthetic Rocket','ロケット','火箭')
        for ds,text in [('de_en','An unrelated modern launch.'),('de_jp','別文脈のロケット')]:
            path=ds+'/scenario.txt';entry=Entry('120001',text,path,1)
            self.data[ds].add(ParsedFile(path,entries=[entry],sha256=digest(text)))
        self.direct=direct_ledger(self.data);r=self.direct['records'][0]
        r['proposed_jp']=r['proposed_jp'].replace('ロケット','火箭')
        r['binding_signature']=contexts.record_signature(r);self.save()
        audit=self.audit();plan=patch_plan.build_plan(self.data,self.names,audit['rows'],audit)
        self.assertEqual({o['string_id'] for o in plan['operations']},{'5001','26001'})
        self.assertEqual(self.data['de_jp'].resolved('120001').value,'別文脈のロケット')

    def test_shinkichon_name_adjudications_preserve_context_authority(self):
        from tests.local_pipeline import inputs,payload
        from tools.localization.parser import parse_text
        item=inputs();names={r['string_id']:r for r in item['ledger']['records']}
        direct={r['string_id']:r for r in contexts.load()['records']}
        ops={o['string_id']:o for o in item['plan']['operations']}
        for sid in ('7438','17438'):
            self.assertNotIn(sid,direct)
            self.assertEqual(names[sid]['expected_de_english'],'Shinkichon')
            self.assertEqual(names[sid]['proposed_jp'],'神機箭')
            self.assertEqual(names[sid]['signature'],signature(item['data'],sid,names[sid]['help_ids']))
            self.assertEqual(ops[sid]['after'],'神機箭')
            self.assertNotIn(contexts.RELATION,ops[sid]['relations'])
        for sid in ('8438','28438','120167'):
            self.assertNotIn(sid,names)
            self.assertEqual(ops[sid]['after'],direct[sid]['proposed_jp'])
            self.assertIn('神機箭',ops[sid]['after'])
            self.assertEqual(ops[sid]['relations'],[contexts.RELATION])
        suppressed=[r for r in item['rows'] if r['decision_string_id'] in ('7438','17438') and r.get('suppressed_by_context_override')]
        self.assertTrue(suppressed)
        self.assertTrue(all(not r['change_candidate'] for r in suppressed))
        output=parse_text(payload()[0]['files']['resources/jp/strings/key-value/key-value-strings-utf8.txt'].decode('utf-8-sig'))
        values={e.string_id:e.value for e in output.entries}
        for sid in ('7438','17438','8438','28438','120167'):
            self.assertEqual(values[sid],ops[sid]['after'])
        # Removing only the two Shinkichon authorities leaves the current remaining 385 operations.
        old_names=copy.deepcopy(item['ledger'])
        old_names['records']=[r for r in old_names['records'] if r['string_id'] not in ('7438','17438')]
        old_audit=scope.build_scope(item['data'],old_names,context_path=contexts.DEFAULT_PATH)
        from tools.localization.layout_plan import integrate
        old_plan=integrate(item['data'],old_names,old_audit['rows'],old_audit,{},item['human'])
        old_ops={o['string_id']:o for o in old_plan['operations']}
        self.assertEqual(set(ops)-set(old_ops),{'7438','17438'})
        self.assertEqual(len(old_ops),385)
        self.assertEqual({sid:ops[sid] for sid in old_ops},old_ops)
