"""Policy tests use project-owned synthetic names, not official fixtures."""

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
from tools.localization.restoration import build_restoration, digest, render_tsv, render_markdown
from tools.localization.__main__ import main
from tools.localization.parser import ParsedFile, parse_text


def report(data=None, exceptions=None):
    data = synthetic() if data is None else data
    return build_restoration(data, build_inventory(data, RULES), exceptions or {})


def first(data=None, exceptions=None):
    return report(data, exceptions)['rows'][0]


class RestorationTests(unittest.TestCase):
    def test_stable_legacy_proposes_exact_value_and_provenance(self):
        row = first()
        self.assertEqual(row['classification'], 'restore_candidate')
        self.assertEqual(row['proposed_jp'], '旧走者')
        self.assertEqual(row['datasets']['aoc_jp']['state'], 'missing')
        self.assertTrue(row['basis_sources']['aok_jp']['occurrences'][0]['path'])
        self.assertIn('runtime_display_unverified', row['flags'])

    def test_legacy_conflict_never_chooses_generation(self):
        data = synthetic()
        add(data, 'aoc_jp', '5001', '別走者')
        self.assertEqual(first(data)['classification'], 'manual_review')
        self.assertIsNone(first(data)['proposed_jp'])

    def test_duplicate_same_or_different_value_is_ambiguous(self):
        for value in ('旧走者', '別走者'):
            with self.subTest(value=value):
                data = synthetic()
                add(data, 'aoc_jp', '5001', '旧走者', 'one.dll')
                add(data, 'aoc_jp', '5001', value, 'two.dll')
                row = first(data)
                self.assertEqual(row['classification'], 'manual_review')
                self.assertEqual(len(row['datasets']['aoc_jp']['occurrences']), 2)
                self.assertEqual(row['datasets']['aoc_jp']['state'], 'ambiguous')

    def test_english_change_is_not_automatically_reuse(self):
        data = synthetic()
        data['hd_en'].entries['5001'] = []
        add(data, 'hd_en', '5001', 'River Courier')
        self.assertEqual(first(data)['classification'], 'manual_review')

    def test_reviewed_reuse_requires_current_fingerprints(self):
        ev = {'5001': dict(hd_en_sha256=digest('River Runner'), de_en_sha256=digest('River Runner'), reason='Synthetic reviewed role change')}
        self.assertEqual(first(exceptions=ev)['classification'], 'id_reuse')
        ev['5001']['de_en_sha256'] = digest('Stale Name')
        row = first(exceptions=ev)
        self.assertEqual(row['classification'], 'manual_review')
        self.assertIn('stale_review_evidence', row['flags'])

    def test_new_content_provisional_and_missing_dataset_not_new(self):
        result = report()
        self.assertEqual(result['rows'][1]['classification'], 'new_content')
        self.assertIn('concept_novelty_unverified', result['rows'][1]['flags'])
        data = synthetic()
        del data['aok_jp']
        self.assertTrue(all(r['classification']=='manual_review' for r in report(data)['rows']))

    def test_unchanged_is_keep_and_hd_alone_is_not_legacy(self):
        data = synthetic()
        data['de_jp'].entries['5001'] = []
        add(data, 'de_jp', '5001', '旧走者')
        self.assertEqual(first(data)['classification'], 'keep_de_candidate')
        data['aok_jp'].entries['5001'] = []
        self.assertEqual(first(data)['classification'], 'manual_review')

    def test_context_and_syntax_require_review(self):
        data = synthetic()
        audit = build_inventory(data, RULES)
        audit['rows'][0]['content_family'] = 'chronicles'
        self.assertEqual(build_restoration(data, audit, {})['rows'][0]['classification'], 'manual_review')
        for n in ('aok_jp', 'hd_jp'):
            data[n].entries['5001'] = []
            add(data, n, '5001', r'旧走者\n%s')
        self.assertIn('technical_syntax_review', first(data)['flags'])

    def test_systematic_elite_name_is_not_forced_to_de(self):
        data = synthetic()
        for n,v in [('hd_en','Elite River Runner'), ('aoc_jp','川の達人'), ('hd_jp','川の達人')]:
            add(data,n,'5002',v)
        audit = build_inventory(data,RULES)
        audit['rows'][1]['content_family'] = 'core'
        row = build_restoration(data,audit,{})['rows'][1]
        self.assertEqual(row['classification'],'restore_candidate')
        self.assertEqual(row['proposed_jp'],'川の達人')

    def test_report_round_trip_and_determinism(self):
        result = report()
        self.assertEqual(result, report())
        parsed = list(csv.DictReader(io.StringIO(render_tsv(result)), delimiter='\t'))
        self.assertEqual(json.loads(parsed[0]['proposed_jp']), '旧走者')
        self.assertEqual(json.loads(parsed[0]['basis_sources'])['aoc_jp']['state'],'missing')
        self.assertIn(result['policy_sha256'],render_markdown(result))
        self.assertEqual(sum(result['counts'].values()),len(result['rows']))

    def test_malformed_id_never_proposed(self):
        data = synthetic()
        data['aoc_jp'].add(parse_text('5001 invalid', 'aoc_jp/synthetic.txt'))
        self.assertEqual(first(data)['classification'], 'manual_review')
        self.assertIsNone(first(data)['proposed_jp'])

    def test_existing_concept_at_another_hd_id_is_not_called_new(self):
        data = synthetic()
        add(data, 'hd_en', '999', 'Elite River Runner')
        self.assertEqual(report(data)['rows'][1]['classification'], 'manual_review')

    def test_cli_export_and_existing_output_protection(self):
        Path('reports').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir='reports') as directory:
            args=['restoration','--output-dir',directory]
            with patch('tools.localization.__main__.load_datasets',return_value=synthetic()), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(args),0)
                before=Path(directory,'candidates.tsv').read_bytes()
                self.assertEqual(main(args),2)
                self.assertEqual(before,Path(directory,'candidates.tsv').read_bytes())
                self.assertTrue(Path(directory,'summary.md').exists())


if __name__ == '__main__':
    unittest.main()
