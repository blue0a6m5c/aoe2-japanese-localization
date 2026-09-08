"""Synthetic editorial-review fixtures only."""
import contextlib
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_gameplay import synthetic, add, RULES
from tools.localization.gameplay import build_inventory
from tools.localization.adoption import (build_adoption, signature, render_review, render_evidence, render_summary)
from tools.localization.__main__ import main


def build(data=None, cases=None):
    data = synthetic() if data is None else data
    return build_adoption(data,build_inventory(data,RULES),{} if cases is None else cases)


def reviewed(data, decision='restore'):
    return {'5001':dict(signature=signature(data,'5001',['26001']),decision=decision,
                        confidence='high',upstream_class='legacy_restoration',reason='Synthetic source-role review')}


class AdoptionTests(unittest.TestCase):
    def test_no_automatic_adoption(self):
        report=build()
        self.assertEqual(report['total'],1)
        row=report['rows'][0]
        self.assertEqual(row['decision'],'manual_review')
        self.assertIsNone(row['proposed_jp'])
        self.assertEqual(row['legacy_candidate_jp'],'旧走者')
        self.assertEqual(row['approval_status'],'pending')

    def test_reviewed_restore_is_still_pending(self):
        data=synthetic()
        row=build(data,reviewed(data))['rows'][0]
        self.assertEqual(row['decision'],'restore')
        self.assertEqual(row['proposed_jp'],'旧走者')
        self.assertEqual(row['reviewer_decision'],'')
        self.assertEqual(row['approval_status'],'pending')

    def test_changed_help_invalidates_editorial_case(self):
        data=synthetic(); cases=reviewed(data)
        data['hd_en'].entries['26001']=[]
        add(data,'hd_en','26001','A changed purpose')
        row=build(data,cases)['rows'][0]
        self.assertEqual(row['decision'],'manual_review')
        self.assertIn('stale_editorial_review',row['flags'])

    def test_keep_de_uses_existing_value(self):
        data=synthetic()
        row=build(data,reviewed(data,'keep_de'))['rows'][0]
        self.assertEqual(row['proposed_jp'],'川の走者')

    def test_related_button_and_help_without_offset_guess(self):
        data=synthetic()
        add(data,'de_en','900001','Create River Runner')
        add(data,'de_jp','900001','川の走者を作成')
        add(data,'de_en','123456','River Runner','another.txt')
        row=build(data)['rows'][0]
        ids={r['string_id'] for r in row['related']}
        self.assertTrue({'5001','26001','900001'}.issubset(ids))
        self.assertNotIn('123456',ids)

    def test_consistency_evidence_is_separate_from_preference(self):
        data=synthetic()
        data['de_jp'].entries['26001']=[]
        add(data,'de_jp','26001',r'<b>別の走者<b>の作成')
        row=build(data)['rows'][0]
        self.assertIn('consistency_fix',row['upstream_classes'])
        self.assertEqual(row['upstream_class'],'subjective')
        self.assertTrue(row['consistency_evidence'])

    def test_round_trip_provenance_and_counts(self):
        report=build()
        rows=list(csv.DictReader(io.StringIO(render_review(report)),delimiter='\t'))
        self.assertEqual(json.loads(rows[0]['legacy_candidate_jp']),'旧走者')
        evidence=list(csv.DictReader(io.StringIO(render_evidence(report)),delimiter='\t'))
        self.assertTrue(all(json.loads(r['provenance']) for r in evidence))
        self.assertEqual(sum(report['counts'].values()),len(rows))
        self.assertIn('5001',render_summary(report))
        self.assertEqual(report,build())

    def test_cli_output_guard_and_preservation(self):
        Path('reports').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir='reports') as directory:
            with patch('tools.localization.__main__.load_datasets',return_value=synthetic()), contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                args=['adoption','--output-dir',directory]
                self.assertEqual(main(args),0)
                before={f.name:f.read_bytes() for f in Path(directory).iterdir()}
                self.assertEqual(main(args),2)
                self.assertEqual(before,{f.name:f.read_bytes() for f in Path(directory).iterdir()})
                self.assertEqual(len(before),5)
                self.assertEqual(main(['adoption','--output-dir','source/adoption-test']),2)
                self.assertFalse(Path('source/adoption-test').exists())


if __name__=='__main__':
    unittest.main()
