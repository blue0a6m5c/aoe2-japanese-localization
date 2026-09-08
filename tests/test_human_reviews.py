"""Synthetic sources, explicit project-owned human decisions."""
import unittest
from pathlib import Path

from tests.test_gameplay import synthetic, add, RULES
from tools.localization.analysis import Dataset
from tools.localization.gameplay import build_inventory
from tools.localization.adoption import build_adoption, signature, render_review
from tools.localization.human_reviews import validate, load_ledger


def ledger(data, ids, decision='revise', jp='人間の指定訳', baseline=None):
    inv={r['string_id']:r for r in build_inventory(data,RULES)['rows']}
    records=[]
    for sid in ids:
        helps=sorted({e['help_id'] for e in inv[sid]['evidence']},key=int)
        records.append(dict(string_id=sid,expected_de_english=data['de_en'].resolved(sid).value,
                            proposed_jp=jp,decision=decision,notes='Explicit test adjudication',help_ids=helps,
                            signature=signature(data,sid,helps)))
    return dict(review_id='synthetic-review',reviewer='synthetic reviewer',baseline_ids=ids if baseline is None else baseline,records=records)


def build(data, human):
    return build_adoption(data,build_inventory(data,RULES),{},human)


class HumanReviewTests(unittest.TestCase):
    def test_human_overrides_auto_and_is_reproducible(self):
        data=synthetic(); human=ledger(data,['5001'])
        first=build(data,human); second=build(data,human)
        self.assertEqual(first,second)
        row=first['rows'][0]
        self.assertEqual(row['decision'],'manual_review')
        self.assertEqual(row['effective_decision'],'revise')
        self.assertEqual(row['reviewer_proposed_jp'],'人間の指定訳')
        self.assertEqual(row['approval_status'],'approved')
        self.assertEqual(row['signature'],row['human_signature'])

    def test_5455_7392_revise_never_reverts(self):
        data={n:Dataset(n) for n in ('de_en','de_jp','hd_en','hd_jp','aok_jp','aoc_jp')}
        for sid in ('5455','7392'):
            for n,text in [('de_en','Elite River Sentinel'),('hd_en','Elite River Sentinel'),
                           ('de_jp','新表記'),('hd_jp','旧表記'),('aok_jp','旧表記')]:
                add(data,n,sid,text)
        add(data,'de_en','26455',r'Create <b>Elite River Sentinel<b> (<cost>)\nUnique Infantry.')
        add(data,'de_en','28392',r'Upgrade to <b>Elite River Sentinel<b> (<cost>)\nImproves sentinels.')
        human=ledger(data,['5455','7392'],jp='エリート イェニチェリ')
        for _ in range(2):
            report=build(data,human)
            for row in report['rows']:
                self.assertEqual(row['effective_proposed_jp'],'エリート イェニチェリ')
                self.assertEqual(row['effective_decision'],'revise')
            self.assertIn('エリート イェニチェリ',render_review(report))
        # Same concept and shared Help, but conflicting human names must be reported.
        human['records'][1]['proposed_jp']='別の指定訳'
        self.assertIn('human_conflict',build(data,human)['human_review']['related_status_counts'])
        actual=load_ledger()
        for r in actual['records']:
            if r['string_id'] in ('5455','7392'):
                self.assertEqual((r['decision'],r['proposed_jp']),('revise','エリート イェニチェリ'))

    def test_stale_evidence_retains_adjudication_without_auto_fallback(self):
        data=synthetic(); human=ledger(data,['5001'])
        add(data,'hd_en','26001','Changed historical purpose')
        row=build(data,human)['rows'][0]
        self.assertEqual(row['reviewer_proposed_jp'],'人間の指定訳')
        self.assertEqual(row['approval_status'],'approved_requires_revalidation')
        self.assertIsNone(row['effective_proposed_jp'])

    def test_duplicate_and_empty_adopted_value_rejected(self):
        data=synthetic(); human=ledger(data,['5001'])
        human['records'].append(dict(human['records'][0]))
        with self.assertRaisesRegex(ValueError,'Duplicate'): validate(human)
        human['records'].pop(); human['records'][0]['proposed_jp']=''
        with self.assertRaisesRegex(ValueError,'Explicit'): validate(human)

    def test_extra_decision_is_preserved_and_missing_baseline_reported(self):
        data=synthetic(); human=ledger(data,['5002'],baseline=['5001'])
        report=build(data,human)
        self.assertEqual(report['human_review']['missing_baseline_ids'],['5001'])
        self.assertEqual(report['human_review']['additional_ids'],['5002'])
        self.assertEqual(next(r for r in report['rows'] if r['string_id']=='5002')['approval_status'],'approved')

    def test_missing_source_and_english_mismatch(self):
        data=synthetic(); human=ledger(data,['5001'])
        human['records'][0]['expected_de_english']='A different concept'
        self.assertEqual(build(data,human)['human_review']['stale_ids'],['5001'])
        data['de_en'].entries.pop('5001')
        self.assertEqual(build(data,human)['human_review']['absent_source_ids'],['5001'])

    def test_related_action_no_automatic_approval(self):
        data=synthetic()
        add(data,'de_en','9000','Create River Runner')
        report=build(data,ledger(data,['5001']))
        checks=report['human_review']['related_checks']
        check=next(r for r in checks if r['related_id']=='9000')
        self.assertEqual(check['status'],'linked_usage_requires_implementation_review')
        self.assertNotIn('9000',[r['string_id'] for r in report['rows']])

    def test_recorded_user_coverage_and_counts(self):
        human=load_ledger()
        records=human['records']; ids=[r['string_id'] for r in records]
        self.assertEqual(len(ids),85)
        self.assertEqual(len(set(ids)),85)
        self.assertEqual(len(human['baseline_ids']),80)
        self.assertTrue(set(human['baseline_ids']).issubset(ids))
        self.assertEqual(set(ids)-set(human['baseline_ids']),{'5115','5118','5130','5186','5205'})
        self.assertEqual([sum(r['decision']==d for r in records) for d in ('restore','keep_de','revise')],[81,2,2])


if __name__=='__main__': unittest.main()
