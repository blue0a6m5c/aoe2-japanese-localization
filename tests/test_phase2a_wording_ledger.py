"""Formal Phase 2A wording adjudications and their concept-scoped source bindings."""
from collections import Counter
import csv
import json
from pathlib import Path
import unittest

from tools.localization.analysis import load_datasets
from tools.localization.human_reviews import implementation_ledger, load_ledger, source_bindings_match
from tools.localization.restoration import digest


ROOT = Path(__file__).resolve().parents[1]
FINAL = ROOT / 'reports/phase2a/adjudication-final-set-20260910'
HUMAN = ROOT / 'reviews/human/wording-review_reviewed.tsv'


class Phase2AWordingLedgerTests(unittest.TestCase):
    def setUp(self):
        self.ledger = load_ledger()
        self.old = self.ledger['records'][:104]
        self.new = self.ledger['records'][104:]

    def test_prior_104_are_preserved_and_new_set_is_unique(self):
        self.assertEqual(digest(json.dumps(self.old,sort_keys=True,ensure_ascii=False,separators=(',',':'))),
                         'b3902acf9a7c8dafee30ec8ffe3b4147f791e8477613c42063c9a880aaffe4dd')
        self.assertEqual(len(self.new),64)
        self.assertEqual(len({r['string_id'] for r in self.ledger['records']}),168)
        targets=[b['string_id'] for r in self.new for b in r['target_bindings']]
        self.assertEqual((len(targets),len(set(targets))),(249,249))
        self.assertEqual(Counter(b['change_required'] for r in self.new for b in r['target_bindings']),
                         Counter({True:141,False:108}))
        self.assertEqual(Counter(r['provenance']['kind'] for r in self.new),Counter({
            'wording_review_human_adjudication':52,
            'family_derived_safe_explicit_approval':11,
            'family_derived_needs_human_review_explicit_adjudication':1,
        }))
        self.assertEqual({r['implementation_status'] for r in self.new},
                         {'adjudicated_not_patch_enabled'})
        self.assertEqual(len(implementation_ledger(self.ledger)['records']),104)

    def test_protected_and_cross_concept_ids_are_excluded(self):
        targets={b['string_id'] for r in self.new for b in r['target_bindings']}
        self.assertFalse(targets & {'5350','5105','5455','7392','7432','17432'})
        self.assertFalse(targets & {'5087','14087','6087','26087','5190','14190','6190','26190'})
        by_english={}
        for r in self.new: by_english.setdefault(r['expected_de_english'],[]).append(r)
        for english in ('Elite Iron Pagoda','Heavy Hei Guang Cavalry','Elite Fire Lancer','Savar',
                        'Elite Serjeant','Winged Hussar','Elite Magyar Huszar','Elite Steppe Lancer','Elite Obuch'):
            pair=by_english[english]
            self.assertEqual({r['category'] for r in pair},{'unit','technology'})
            self.assertFalse(set(b['string_id'] for b in pair[0]['target_bindings']) &
                             set(b['string_id'] for b in pair[1]['target_bindings']))
        eagle=next(r for r in self.new if r['expected_de_english']=='Eagle Warrior')
        self.assertEqual({b['string_id'] for b in eagle['target_bindings']},{'5671','14671','6671','26671'})

    def test_latest_52_and_approved_12_match_final_set(self):
        if not (FINAL / 'final-adjudication-set.tsv').exists() or not HUMAN.exists():
            self.skipTest('Local copyrighted/provenance review inputs are intentionally untracked')
        with (FINAL/'final-adjudication-set.tsv').open(encoding='utf-8') as f:
            final=list(csv.DictReader(f,delimiter='\t'))
        with HUMAN.open(encoding='utf-8') as f:
            human=list(csv.DictReader(f,delimiter='\t'))
        records={(r['concept_id'],r['category']):r for r in self.new}
        for row in final:
            record=records[(row['concept_id'],row['category'])]
            self.assertEqual((record['proposed_jp'],record['decision'],record['notes']),
                             (row['adopted_japanese'],row['decision'],row['human_reason']))
        category={'ユニット':'unit','テクノロジー':'technology','建物':'building'}
        originals=[r for r in self.new if r['provenance']['kind']=='wording_review_human_adjudication']
        original_by_row={r['provenance']['source_row']:r for r in originals}
        for source_row,row in enumerate(human,2):
            record=original_by_row[source_row]
            self.assertEqual(record['category'],category[row['種別']])
            self.assertEqual((record['proposed_jp'],record['decision'],record['notes']),
                             (row['採用する日本語'],row['裁定'],row['判断理由']))
        timurid=next(r for r in originals if r['expected_de_english']=='Timurid Siegecraft')
        self.assertIn('それを踏襲した技術',timurid['notes'])
        savar=next(r for r in self.new if r['expected_de_english']=='Savar' and r['category']=='unit')
        self.assertEqual(savar['proposed_jp'],'サヴァール')
        self.assertEqual({b['role'] for b in savar['target_bindings']},
                         {'full_name','compact_name','action_display','help_heading'})

    def test_all_signatures_and_source_bindings_match_current_source(self):
        if not (ROOT/'source/de').exists():
            self.skipTest('Local copyrighted source is intentionally untracked')
        data=load_datasets(ROOT/'source')
        self.assertEqual([r['string_id'] for r in self.new if not source_bindings_match(r,data)],[])


if __name__=='__main__': unittest.main()
