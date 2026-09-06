import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from tools.localization.parser import parse_file, parse_text
from tools.localization.analysis import Dataset, classify, load_datasets, row, summary, id_sort
from tools.localization.__main__ import main, write_report


FIXTURES = Path(__file__).parent / 'fixtures'


class ParserTests(unittest.TestCase):
    def test_unicode_empty_and_syntax_preserved(self):
        text = '\ufeff// fixture\r\n1 "Plain"\r\n2 "日本語😀 %s <b>"\n3 ""\n'
        parsed = parse_text(text)
        self.assertEqual([e.value for e in parsed.entries], ['Plain', '日本語😀 %s <b>', ''])
        self.assertEqual([e.line for e in parsed.entries], [2, 3, 4])
        self.assertFalse(parsed.issues)

    def test_escaped_quotes_backslashes_and_literal_newline(self):
        value = r'quote: \"word\" path: \\ literal: \n\t'
        parsed = parse_text('7 "' + value + '" // trailing comment')
        self.assertEqual(parsed.entries[0].value, value)
        self.assertFalse(parsed.issues)
        self.assertFalse(parse_text('1 "ends in \\\\"').issues)

    def test_symbols_and_leading_zero_ids_are_not_normalized(self):
        parsed = parse_text('001 "a"\n1 "b"\nIDS_TEST "c"\n9_future "d"')
        self.assertEqual([e.string_id for e in parsed.entries], ['001', '1', 'IDS_TEST', '9_future'])

    def test_unicode_separators_are_not_physical_lines(self):
        value = 'a\u2028b\u0085c\u2029d'
        self.assertEqual(parse_text(f'1 "{value}"').entries[0].value, value)

    def test_malformed_never_discarded(self):
        lines = ['garbage', '1 unquoted', '2 "open', '3 "ok" junk', '4 "inner "quote"',
                 '5 "dangling' + '\\', '6 "multiline', 'continuation"', 'bad-key "x"']
        parsed = parse_text('\n'.join(lines) + '\n99 "recovered"')
        self.assertEqual(len(parsed.issues), len(lines))
        self.assertEqual([i.raw for i in parsed.issues], lines)
        self.assertEqual(parsed.entries[0].string_id, '99')

    def test_unknown_escape_retained_but_unresolved(self):
        parsed = parse_text(r'1 "unknown \q"')
        dataset = Dataset('test')
        dataset.add(parsed)
        self.assertEqual(parsed.entries[0].value, r'unknown \q')
        self.assertEqual(parsed.issues[0].kind, 'unknown_escape')
        self.assertIsNone(dataset.resolved('1'))

    def test_duplicates_same_and_cross_file_keep_all_occurrences(self):
        dataset = Dataset('test')
        dataset.add(parse_text('1 "a"\n1 "a"', 'first'))
        dataset.add(parse_text('1 "b"', 'second'))
        self.assertEqual(len(dataset.entries['1']), 3)
        self.assertIsNone(dataset.resolved('1'))
        self.assertEqual(dataset.stats()['duplicate_ids'], 1)
        self.assertEqual(dataset.stats()['duplicate_extra_entries'], 2)

    def test_invalid_utf8_and_read_only(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'invalid.txt'
            original = b'1 "valid"\n2 "\xff"'
            path.write_bytes(original)
            parsed = parse_file(path)
            self.assertEqual(parsed.issues[0].kind, 'encoding_error')
            self.assertFalse(parsed.entries)
            self.assertEqual(path.read_bytes(), original)


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.data = load_datasets(FIXTURES)

    def test_categories(self):
        self.assertIn('jp_only_changed', classify('1', self.data))
        self.assertIn('en_changed', classify('2', self.data))
        self.assertNotIn('jp_changed', classify('2', self.data))
        self.assertIn('hd_only', classify('3', self.data))
        self.assertIn('de_added', classify('5', self.data))
        self.assertIn('missing', classify('6', self.data))
        self.assertNotIn('jp_only_changed', classify('6', self.data))
        self.assertEqual(classify('4', self.data), ['all_four'])

    def test_multiple_files_and_stats(self):
        self.assertIn('7_test', self.data['de_en'].entries)
        stats = summary(self.data)
        self.assertEqual(stats['comparison']['hd_de_common_ids'], 5)
        self.assertEqual(stats['comparison']['de_added'], 2)
        self.assertEqual(stats['comparison']['hd_only'], 1)
        self.assertEqual(stats['comparison']['jp_only_changed'], 1)

    def test_duplicate_never_resolved_even_if_identical(self):
        self.data['hd_en'].add(parse_text('1 "Example"', 'duplicate'))
        flags = classify('1', self.data)
        self.assertIn('duplicate', flags)
        self.assertIn('jp_changed', flags)
        self.assertNotIn('jp_only_changed', flags)
        self.assertEqual(len(row('1', self.data, True)['datasets']['hd_en']['occurrences']), 2)

    def test_malformed_id_blocks_otherwise_valid_value(self):
        self.data['hd_en'].add(parse_text('1 "missing end', 'broken'))
        self.assertIn('parse_error', classify('1', self.data))
        self.assertNotIn('jp_only_changed', classify('1', self.data))

    def test_raw_comparison_does_not_normalize(self):
        self.data['hd_en'].add(parse_text('99 "a "'))
        self.data['de_en'].add(parse_text('99 "a"'))
        self.assertIn('en_changed', classify('99', self.data))
        self.assertEqual(sorted(['TOKEN', '10', '2', '02'], key=id_sort), ['02', '2', '10', 'TOKEN'])

    def test_missing_input_is_error(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, 'Missing dataset'):
                load_datasets(Path(temp))

    def test_additional_generation_does_not_change_hd_de_stats(self):
        from tools.localization.analysis import all_ids
        before = summary(self.data)['comparison']
        extra = Dataset('aoc_jp')
        extra.add(parse_text('EXTRA "追加世代の例"'))
        self.data['aoc_jp'] = extra
        self.assertIn('EXTRA', all_ids(self.data))
        self.assertEqual(summary(self.data)['comparison'], before)


class CLITests(unittest.TestCase):
    def run_cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = main(['--source-root', str(FIXTURES), *args])
        return status, json.loads(stdout.getvalue()) if stdout.getvalue() else None, stderr.getvalue()

    def test_search_show_filters_and_paging(self):
        status, data, _ = self.run_cli('search', '新しい', '--dataset', 'de_jp', '--values')
        self.assertEqual(status, 0)
        self.assertEqual([r['string_id'] for r in data['rows']], ['1'])
        self.assertEqual(self.run_cli('show', '4')[1]['datasets']['hd_en']['occurrences'][0]['value'], '')
        data = self.run_cli('changes', '--category', 'jp_only_changed')[1]
        self.assertEqual(data['total'], 1)
        self.assertNotIn('value', data['rows'][0]['datasets']['hd_en']['occurrences'][0])
        self.assertEqual(self.run_cli('compare', '--missing', 'hd_jp')[1]['total'], 3)
        self.assertEqual(self.run_cli('compare', '--limit', '1', '--offset', '1')[1]['rows'][0]['string_id'], '2')

    def test_invalid_options_and_determinism(self):
        self.assertEqual(self.run_cli('compare', '--values', '--limit', '201')[0], 2)
        self.assertEqual(self.run_cli('search', 'x', '--dataset', 'typo')[0], 2)
        self.assertEqual(self.run_cli('compare', '--offset', '-1')[0], 2)
        self.assertEqual(self.run_cli('stats'), self.run_cli('stats'))

    def test_diagnostics_exit_status_and_content(self):
        from unittest.mock import patch
        data = load_datasets(FIXTURES)
        data['hd_en'].add(parse_text('1 "duplicate"\n9 "unclosed\n??', 'problem'))
        with patch('tools.localization.__main__.load_datasets', return_value=data):
            status, result, err = self.run_cli('issues')
        self.assertEqual(status, 1)
        self.assertEqual(result['total'], 3)
        self.assertTrue(err)
        self.assertNotIn('raw', result['items'][0])

    def test_report_cli_is_bounded_and_contains_provenance(self):
        with tempfile.TemporaryDirectory(dir=self.ensure_reports()) as temp:
            target = Path(temp) / 'limited.json'
            status, result, _ = self.run_cli('report', '--category', 'jp_only_changed',
                                           '--values', '--limit', '1', '--output', str(target))
            self.assertEqual(status, 0)
            self.assertEqual(result['rows_written'], 1)
            report = json.loads(target.read_text(encoding='utf-8'))
            self.assertEqual(len(report['inventory']), 6)
            self.assertIn('sha256', report['inventory'][0])
            self.assertEqual(len(report['rows']), 1)

    def test_output_guard_and_no_overwrite(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            outside = Path(temp) / 'blocked.json'
            with self.assertRaises(ValueError):
                write_report(outside, '{}', FIXTURES)
            with tempfile.TemporaryDirectory(dir=self.ensure_reports()) as report_dir:
                target = Path(report_dir) / 'report.json'
                write_report(target, '{}', FIXTURES)
                with self.assertRaises(FileExistsError):
                    write_report(target, '{"changed": true}', FIXTURES)
                self.assertEqual(target.read_text(encoding='utf-8'), '{}\n')
                with self.assertRaises(ValueError):
                    write_report(Path(report_dir) / 'source.json', '{}', Path(report_dir))

    @staticmethod
    def ensure_reports():
        path = Path.cwd() / 'reports'
        path.mkdir(exist_ok=True)
        return path


if __name__ == '__main__':
    unittest.main()
