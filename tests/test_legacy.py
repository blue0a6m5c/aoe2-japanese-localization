import contextlib
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest

from tests.pe_fixture import make_pe
from tools.localization.legacy import parse_legacy_bytes, parse_legacy_file
from tools.localization.analysis import Dataset, legacy_summary, load_datasets, pair_summary, row, summary
from tools.localization.__main__ import main


FIXTURES = Path(__file__).parent / 'fixtures'


class LegacyParserTests(unittest.TestCase):
    def test_unicode_multiple_ids_and_provenance(self):
        parsed = parse_legacy_bytes(make_pe([(2, 0x411, {0: '日本語😀', 15: 'sample\n%s <b>'}),
                                            (10, 0x411, {7: '別ブロック'})]), 'test.dll', 'aoc')
        self.assertFalse(parsed.issues)
        self.assertEqual([e.string_id for e in parsed.entries], ['16', '31', '151'])
        entry = parsed.entries[0]
        self.assertEqual(entry.value, '日本語😀')
        self.assertEqual((entry.generation, entry.language, entry.path), ('aoc', 'jp', 'test.dll'))
        self.assertIsNone(entry.line)
        self.assertEqual(entry.resource['length_utf16'], 5)
        self.assertEqual(entry.resource['block_id'], 2)
        self.assertEqual(entry.resource['language_id'], 0x411)

    def test_empty_slots_are_retained_but_not_claimed_as_strings(self):
        parsed = parse_legacy_bytes(make_pe([(1, 0x411, {1: '', 2: 'value'})]))
        self.assertEqual(len(parsed.entries), 1)
        self.assertEqual(len(parsed.empty_slots), 15)
        self.assertEqual(parsed.empty_slots[1].value, '')
        self.assertTrue(parsed.empty_slots[1].resource['zero_length'])
        data = load_datasets(FIXTURES)
        dataset = Dataset('aok_jp')
        dataset.add(parsed)
        data['aok_jp'] = dataset
        self.assertIsNone(dataset.resolved('1'))
        self.assertIsNone(dataset.resolved('999'))
        self.assertEqual(row('1', data, True)['datasets']['aok_jp']['state'], 'empty_resource_slot')
        self.assertEqual(row('999', data)['datasets']['aok_jp']['state'], 'missing')

    def test_pe32_plus(self):
        parsed = parse_legacy_bytes(make_pe(pe_plus=True))
        self.assertFalse(parsed.issues)
        self.assertEqual(parsed.metadata['pe_kind'], 'PE32+')

    def test_resource_languages_preserved_without_fallback(self):
        parsed = parse_legacy_bytes(make_pe([(1, 0x411, {1: '日本語'}), (1, 0x409, {1: 'English'})]))
        dataset = Dataset('mixed')
        dataset.add(parsed)
        self.assertEqual({e.language for e in dataset.entries['1']}, {'jp', 'en'})
        self.assertIsNone(dataset.resolved('1'))

    def test_literal_backslashes_quotes_and_embedded_nul(self):
        value = '"quote" \\n real\n\t\0end'
        parsed = parse_legacy_bytes(make_pe([(1, 0x411, {0: value})]))
        self.assertEqual(parsed.entries[0].value, value)

    def test_file_read_only_and_missing_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'test.dll'
            original = make_pe()
            path.write_bytes(original)
            parsed = parse_legacy_file(path, 'aok')
            self.assertEqual(parsed.sha256, hashlib.sha256(original).hexdigest())
            self.assertEqual(path.read_bytes(), original)
            with self.assertRaises(FileNotFoundError):
                parse_legacy_file(Path(temp) / 'absent.dll', 'aok')

    def test_bad_headers_bounds_and_no_resource(self):
        cases = [b'', b'not a DLL', make_pe()[:100], make_pe()[:-1]]
        for offset, value in [(0x3c, 0xffffffff), (0x98 + 112, 0xffffffff),
                              (0x98 + 112, 0), (0x214, 0x80000000)]:
            blob = bytearray(make_pe())
            struct.pack_into('<I', blob, offset, value)
            cases.append(bytes(blob))
        no_strings = bytearray(make_pe())
        struct.pack_into('<I', no_strings, 0x210, 16)
        cases.append(bytes(no_strings))
        for blob in cases:
            with self.subTest(size=len(blob)):
                parsed = parse_legacy_bytes(blob)
                self.assertEqual(parsed.issues[0].kind, 'pe_error')
                self.assertFalse(parsed.entries)
                self.assertFalse(parsed.empty_slots)

    def test_invalid_utf16_and_lengths_reject_whole_file(self):
        blob = make_pe([(1, 0x411, {0: 'A'})])
        entry = parse_legacy_bytes(blob).entries[0]
        offset = entry.resource['byte_offset']
        for delta, word in [(2, 0xd800), (0, 0xffff)]:
            broken = bytearray(blob)
            struct.pack_into('<H', broken, offset + delta, word)
            parsed = parse_legacy_bytes(bytes(broken))
            self.assertEqual(parsed.issues[0].kind, 'pe_error')
            self.assertFalse(parsed.entries)

    def test_overlapping_rva_sections_rejected(self):
        blob = bytearray(make_pe())
        section = 0x98 + 224
        blob[section + 40:section + 80] = blob[section:section + 40]
        struct.pack_into('<H', blob, 0x86, 2)
        self.assertTrue(parse_legacy_bytes(bytes(blob)).issues)


class LegacyIntegrationTests(unittest.TestCase):
    def test_two_dlls_same_and_conflicting_values_remain_ambiguous(self):
        left, right = Dataset('one'), Dataset('two')
        left.add(parse_legacy_bytes(make_pe([(1, 0x411, {1: 'same', 2: 'old', 3: 'only1'})]), 'one.dll', 'aoc'))
        right.add(parse_legacy_bytes(make_pe([(1, 0x411, {1: 'same', 2: 'new', 4: 'only2'})]), 'two.dll', 'aoc'))
        dataset = Dataset('aoc_jp')
        for f in left.files + right.files:
            dataset.add(f)
        self.assertIsNone(dataset.resolved('1'))
        self.assertIsNone(dataset.resolved('2'))
        self.assertEqual(dataset.stats()['duplicate_same_value_ids'], 1)
        self.assertEqual(dataset.stats()['duplicate_conflicting_ids'], 1)
        self.assertEqual(pair_summary(left, right)['common_ids'], 2)
        data = load_datasets(FIXTURES)
        data['aoc_jp'] = dataset
        info = legacy_summary(data)['within_generation_file_pairs'][0]
        self.assertEqual(info['same_literal_value_ids'], 1)
        self.assertEqual(info['different_literal_value_ids'], 1)
        self.assertEqual(info['common_resource_slot_ids'], 16)
        self.assertEqual(info['left_value_right_zero_ids'], 1)
        self.assertEqual(info['left_zero_right_value_ids'], 1)

    def make_source(self, root):
        # Copy no fixtures: create a tiny independent source layout on the fly.
        for directory in ('hd/en', 'hd/jp', 'de/en/key-value', 'de/jp/key-value'):
            path = root / directory
            path.mkdir(parents=True)
            (path / 'sample.txt').write_text('1 "比較資料"\n2 "second"', encoding='utf-8')
        for directory in ('legacy/aok/jp', 'legacy/aoc/jp'):
            path = root / directory
            path.mkdir(parents=True)
            (path / 'first.DLL').write_bytes(make_pe([(1, 0x411, {1: '比較資料', 3: 'legacy'})]))
        (root / 'legacy/aoc/jp/second.dll').write_bytes(make_pe([(1, 0x411, {1: '別資料'})]))

    def run_cli(self, root, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(['--source-root', str(root), *args])
        return code, json.loads(out.getvalue()) if out.getvalue() else None, err.getvalue()

    def test_auto_discovery_search_show_stats_and_phase0_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_source(root)
            datasets = load_datasets(root)
            baseline = load_datasets(root, {n: p for n, p in
                                     [('hd_en','hd/en'), ('hd_jp','hd/jp'), ('de_en','de/en/key-value'), ('de_jp','de/jp/key-value')]})
            self.assertEqual(summary(datasets)['comparison'], summary(baseline)['comparison'])
            code, result, _ = self.run_cli(root, 'search', '比較資料', '--values')
            self.assertEqual(code, 1)
            self.assertEqual(len(result['rows'][0]['datasets']), 6)
            self.assertEqual(result['rows'][0]['datasets']['aoc_jp']['state'], 'ambiguous')
            self.assertEqual(self.run_cli(root, 'legacy-stats')[1]['datasets']['aok_jp']['unique_ids'], 2)
            self.assertEqual(self.run_cli(root, 'show', '1')[1]['datasets']['aok_jp']['occurrences'][0]['value'], '比較資料')
            self.assertEqual(self.run_cli(root, 'compare', '--missing', 'aoc_jp')[1]['total'], 1)
            self.assertEqual(self.run_cli(root, 'legacy-stats'), self.run_cli(root, 'legacy-stats'))

    def test_bad_pe_blocks_comparison_and_remains_visible(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_source(root)
            (root / 'legacy/aok/jp/first.DLL').write_bytes(b'invalid')
            code, result, _ = self.run_cli(root, 'legacy-stats')
            self.assertEqual(code, 1)
            self.assertTrue(result['incomplete'])
            self.assertEqual(self.run_cli(root, 'show', '1')[0], 2)
            items = self.run_cli(root, 'issues')[1]['items']
            self.assertTrue(any(i.get('kind') == 'pe_error' for i in items))

    def test_explicit_format_config_and_missing_optional_legacy(self):
        data = load_datasets(FIXTURES)
        self.assertNotIn('aok_jp', data)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_source(root)
            from tools.localization.analysis import DEFAULT_DATASETS
            config = {**DEFAULT_DATASETS, 'reference': {'path': 'legacy/aok/jp',
                      'format': 'pe_rt_string', 'generation': 'aok'}}
            data = load_datasets(root, config)
            self.assertEqual(data['reference'].resolved('1').generation, 'aok')
            with self.assertRaisesRegex(ValueError, 'Unsupported dataset format'):
                load_datasets(root, {**DEFAULT_DATASETS, 'other': {'path': '.', 'format': 'guess'}})


if __name__ == '__main__':
    unittest.main()
