"""Phase 2A explicit occurrence and compact-layout dry-run validation."""
import copy
import json
from pathlib import Path
import unittest

from tests.local_pipeline import inputs
from tools.localization.human_reviews import load_ledger
from tools.localization.layout_plan import record_signature
from tools.localization.phase2a_patch_plan import build_plan, validate_layout_records
from tools.localization.restoration import digest


LAYOUT = Path('reviews/phase1d-layout-decisions.json')
EXPECTED_LAYOUT_IDS = {
    '14010','14048','14162','14254','14540','14594','14595','14600','14672',
    '14717','14730','17310','17311','17344','17464','17471','17481'}


class Phase2APatchPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.item = inputs()
        cls.wording = load_ledger()
        cls.layout = json.loads(LAYOUT.read_text(encoding='utf8'))

    def test_formal_layout_ledger_preserves_13_and_adds_17(self):
        records=self.layout['records']
        self.assertEqual(len(records),30)
        self.assertEqual({r['string_id'] for r in records[13:]},EXPECTED_LAYOUT_IDS)
        self.assertEqual(len({r['string_id'] for r in records}),30)
        self.assertEqual(digest(json.dumps(records[:13],ensure_ascii=False,sort_keys=True)),
                         '7d4ce7038a68071ff05cecbbb6787612908a7f0c16ade498fda73effe6308c04')
        self.assertTrue(all(r['signature']==record_signature(r) for r in records))
        byid={r['string_id']:r for r in records}
        self.assertEqual((byid['14594']['binding']['layout_before'],byid['14594']['replacement']),
                         (r'鉄\n浮屠','鉄浮屠'))
        self.assertEqual((byid['17481']['binding']['layout_before'],byid['17481']['replacement']),
                         (r'虎蹲\n砲','虎蹲砲'))
        self.assertEqual(byid['14595']['replacement'],byid['17464']['replacement'])
        self.assertEqual(byid['14600']['replacement'],byid['17471']['replacement'])

    def test_plan_counts_layout_and_no_overlap(self):
        plan=build_plan(self.item['data'],self.wording,self.layout)
        self.assertFalse(plan['blocked'])
        self.assertEqual(plan['statistics']['concepts'],64)
        self.assertEqual(plan['statistics']['target_bindings'],249)
        self.assertEqual(plan['statistics']['changed_ids'],141)
        self.assertEqual(plan['statistics']['already_matching'],108)
        self.assertEqual((plan['statistics']['full'],plan['statistics']['span']),(58,83))
        self.assertEqual(plan['statistics']['layout_records'],17)
        baseline=self.item['plan']['operations']
        self.assertEqual(len(baseline),387)
        self.assertFalse({o['string_id'] for o in baseline}&{o['string_id'] for o in plan['operations']})
        merged=baseline+plan['operations']
        self.assertEqual((len(merged),len({o['string_id'] for o in merged})),(528,528))
        self.assertEqual((sum(o['replacement_type']=='full_value' for o in merged),
                          sum(o['replacement_type']=='span' for o in merged)),(287,241))

    def test_14594_17481_are_layout_not_wording_records(self):
        records=validate_layout_records(self.item['data'],self.wording,self.layout)
        for sid,expected in (('14594','鉄浮屠'),('17481','虎蹲砲')):
            record=records[sid]
            owner=next(r for r in self.wording['records']
                       if r['string_id']==record['binding']['wording_decision_string_id'])
            self.assertEqual(record['replacement'],expected)
            self.assertEqual(record['binding']['canonical'],owner['proposed_jp'])

    def test_special_concept_boundaries_do_not_propagate(self):
        records={(r['expected_de_english'],r.get('category'),r['string_id']):
                 {b['string_id'] for b in r.get('target_bindings',[])}
                 for r in self.wording['records'] if r.get('binding_mode')}
        self.assertEqual(records[('Eagle Scout','unit','5672')],
                         {'5672','14672','6672','26672'})
        self.assertEqual(records[('Eagle Warrior','unit','5671')],
                         {'5671','14671','6671','26671'})
        all_targets=set().union(*records.values())
        self.assertTrue({'5673','7433','14673','5190','6190','7300','8300','26190','28300'}
                        .isdisjoint(all_targets))
        self.assertEqual(records[('Heavy Hei Guang Cavalry','unit','5600')],
                         {'5600','14600','6600','26600'})
        self.assertEqual(records[('Heavy Hei Guang Cavalry','technology','7471')],
                         {'7471','17471','8471','28471'})
        self.assertEqual(records[('Iron Pagoda','unit','5594')],
                         {'5594','14594','6594','6595','26594'})
        self.assertEqual(records[('Elite Iron Pagoda','unit','5595')],
                         {'5595','14595','26595'})
        self.assertEqual(records[('Elite Iron Pagoda','technology','7464')],
                         {'7464','17464','8464','28464'})
        self.assertEqual(records[('Fire Lancer','unit','5066')],
                         {'5066','14066','6066','26066'})
        self.assertEqual(records[('Elite Fire Lancer','unit','5717')],
                         {'5717','14717','6717','26717'})
        self.assertEqual(records[('Elite Fire Lancer','technology','7463')],
                         {'7463','17463','8463','28463'})
        self.assertEqual(records[('Savar','unit','5703')],
                         {'5703','14703','6703','26703'})
        self.assertEqual(records[('Savar','technology','7442')],
                         {'7442','8442','28442'})

    def test_explicit_layout_rejects_nonlayout_changes(self):
        for replacement in ('鉄浮屠%s','<b>鉄浮屠','鉄-浮屠','鋼浮屠'):
            ledger=copy.deepcopy(self.layout)
            record=next(r for r in ledger['records'] if r['string_id']=='14594')
            record['replacement']=replacement
            record['signature']=record_signature(record)
            with self.assertRaisesRegex(ValueError,'Unsafe Phase 2A human layout'):
                validate_layout_records(self.item['data'],self.wording,ledger)

    def test_existing_baseline_operations_are_exact(self):
        saved=json.loads(Path('reports/final/historical-restore-r7-ui-170300-final-repro/layout/patch-plan.json').read_text(encoding='utf8'))
        fields=('string_id','source_path','source_line','before','after','replacement_type','matched_span')
        actual=sorted(({k:o[k] for k in fields} for o in self.item['plan']['operations']),
                      key=lambda o:(o['source_path'],o['source_line'],o['string_id'],o['matched_span']))
        expected=sorted(({k:o[k] for k in fields} for o in saved['operations']),
                        key=lambda o:(o['source_path'],o['source_line'],o['string_id'],o['matched_span']))
        self.assertEqual(actual,expected)


if __name__=='__main__': unittest.main()
