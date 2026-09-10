import copy
import json
from pathlib import Path
import tempfile
import unittest

from tests.test_patch_plan import fixture
from tools.localization.blocked_audit import audit_blocked,serialize_json,verify_json
from tools.localization.layout_plan import (integrate,binding,record_signature,render_table,
                                             explicit_human_layout_safe)
from tools.localization.patch_plan import tokens


def human_for(f,replacement):
    d,l,s=f
    audit=audit_blocked(d,l,s['rows'],s)
    records=[]
    for item in audit['manual_review']:
        r={k:item[k] for k in ('source_path','source_line','string_id')}
        r.update(binding=binding(item),replacement=replacement)
        r['signature']=record_signature(r);records.append(r)
    return dict(schema_version=1,authority='explicit_user_layout_decisions',review_id='synthetic-layout',reviewer='user',records=records)


def run(f,h):
    d,l,s=f
    return integrate(d,l,s['rows'],s,{},h)


class LayoutPlanTests(unittest.TestCase):
    def test_explicit_human_layout_may_remove_only_newline(self):
        canonical='Iron Pagoda'
        before=r'Iron\nPagoda'
        self.assertTrue(explicit_human_layout_safe(before,canonical,canonical,canonical))
        for changed in ('Iron Pagoda %s','<b>Iron Pagoda','Iron-Pagoda','Steel Pagoda'):
            self.assertFalse(explicit_human_layout_safe(before,changed,changed,canonical))
        self.assertNotEqual(tokens(before),tokens(canonical))

    def test_human_layout_and_distinct_provenance(self):
        f=fixture('Synthetic Runner',r'旧甲\n走者','新甲走者')
        h=human_for(f,r'新甲\n走者')
        result=run(f,h)
        self.assertFalse(result['blocked'])
        self.assertEqual(result['statistics']['human_layout_locations'],2)
        for o in result['operations']:
            self.assertEqual(o['replacement'],r'新甲\n走者')
            self.assertEqual(o['layout_provenance']['kind'],'human_layout')
            self.assertEqual(tokens(o['before']),tokens(o['after']))

    def test_auto_provenance(self):
        f=fixture('Elite Runner',r'精鋭\n走者','エリート 走者')
        result=run(f,human_for(f,''))
        self.assertEqual(result['statistics']['automatic_layout_locations'],2)
        self.assertTrue(all(o['layout_provenance']['kind']=='automatic_layout' for o in result['operations']))

    def test_reject_noncanonical_or_changed_tokens(self):
        f=fixture('Synthetic Runner',r'旧甲\n走者','新甲走者')
        for replacement in [r'別訳\n走者',r'<b>新甲\n走者',r'新甲\n%s走者']:
            result=run(f,human_for(f,replacement))
            self.assertEqual(result['statistics']['human_layout_locations'],0)
            self.assertTrue(result['blocked'])
        allowed=run(f,human_for(f,'新甲走者'))
        self.assertEqual(allowed['statistics']['human_layout_locations'],2)
        self.assertFalse(allowed['blocked'])

    def test_stale_binding_and_signature(self):
        f=fixture('Synthetic Runner',r'旧甲\n走者','新甲走者')
        h=human_for(f,r'新甲\n走者')
        h['records'][0]['binding']['current']='wrong'
        h['records'][0]['signature']=record_signature(h['records'][0])
        self.assertTrue(run(f,h)['blocked'])
        h['records'][0]['signature']='bad'
        with self.assertRaises(ValueError):run(f,h)

    def test_duplicate_or_other_occurrence_not_applied(self):
        f=fixture('Synthetic Runner',r'旧甲\n走者','新甲走者')
        h=human_for(f,r'新甲\n走者')
        h['records'].append(copy.deepcopy(h['records'][0]))
        with self.assertRaises(ValueError):run(f,h)
        h['records'].pop()
        h['records'][0]['source_line']+=100
        h['records'][0]['signature']=record_signature(h['records'][0])
        with self.assertRaises(ValueError):run(f,h)

    def test_missing_decision_stays_blocked_and_no_mutation(self):
        f=fixture('Synthetic Runner',r'旧甲\n走者','新甲走者')
        h=human_for(f,r'新甲\n走者');h['records'].pop()
        snapshot=copy.deepcopy((f,h))
        a=run(f,h);b=run(f,h)
        self.assertEqual(a,b)
        self.assertEqual(render_table(a),render_table(b))
        self.assertEqual((f,h),snapshot)
        self.assertEqual(a['statistics']['blocked_locations'],1)

    def test_real_346_round_trip_and_preserved_baseline(self):
        from tools.localization.analysis import load_datasets
        from tools.localization.human_reviews import load_ledger,DEFAULT_LEDGER
        from tools.localization.patch_plan import read_audit,build_plan
        from tests.local_pipeline import inputs
        item=inputs(historical=True)
        data,ledger,rows,meta,hashes,h=(item[k] for k in ('data','ledger','rows','meta','hashes','human'))
        result=integrate(data,ledger,rows,meta,hashes,h)
        again=integrate(data,ledger,rows,meta,hashes,h)
        self.assertEqual(result,again)
        self.assertEqual(render_table(result),render_table(again))
        s=result['statistics']
        self.assertEqual((s['patch_operations'],s['layout_resolved_locations'],s['automatic_layout_locations'],s['human_layout_locations']),
                         (346,46,33,13))
        self.assertEqual((s['blocked_locations'],s['conflicts'],s['duplicate_id_patch_operations']),(0,0,0))
        byid={o['string_id']:o for o in result['operations']}
        for sid in ('14573','17375'):self.assertEqual(byid[sid]['replacement'],r'機動\nキャノン ガリオン船')
        self.assertEqual(byid['17415']['replacement'],r'パルティアン\n戦術')
        for o in result['operations']:self.assertEqual(tokens(o['before']),tokens(o['after']))
        baseline=build_plan(data,ledger,rows,meta,hashes)
        kept=[{k:v for k,v in o.items() if k!='layout_provenance'} for o in result['operations'] if o['layout_provenance']['kind']=='baseline_phase1d']
        self.assertEqual(sorted(kept,key=lambda o:o['operation_id']),sorted(baseline['operations'],key=lambda o:o['operation_id']))
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'plan.json';path.write_text(serialize_json(result),encoding='utf8')
            with path.open(encoding='utf8') as stream:self.assertEqual(json.load(stream),result)
            verify_json(path,result)
