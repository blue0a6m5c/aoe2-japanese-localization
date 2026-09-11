"""Source apply executor tests; the real source tree is never written."""
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.localization import source_apply
from tools.localization.mod_build import patch_bytes, safe_source, sha


class SourceApplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Path('source/de/jp/key-value/key-value-strings-utf8.txt').exists():
            raise unittest.SkipTest('Optional local official data unavailable')
        cls.temp = tempfile.TemporaryDirectory()
        cls.before_root = Path(cls.temp.name) / 'before'
        shutil.copytree('source', cls.before_root)
        cls.before_bundle = source_apply.prepare(cls.before_root)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def copy_source(self, name):
        root = Path(self.temp.name) / name
        shutil.copytree(self.before_root, root)
        return root

    def test_clean_before_after_and_second_apply(self):
        root = self.copy_source('clean')
        bundle = source_apply.prepare(root)
        self.assertEqual((bundle['summary']['planned'], bundle['summary']['already_applied']),
                         (528, 0))
        self.assertEqual(len({op['string_id'] for op in bundle['operations']}), 528)
        self.assertEqual((sum(op['replacement_type'] == 'full_value' for op in bundle['operations']),
                          sum(op['replacement_type'] == 'span' for op in bundle['operations'])),
                         (287, 241))
        dry = source_apply.execute(bundle, dry_run=True)
        self.assertEqual((dry['applied'], dry['changed_files']), (0, 0))
        result = source_apply.execute(bundle)
        self.assertEqual((result['applied'], result['already_applied'], result['changed_files']),
                         (528, 0, 1))
        second = source_apply.prepare(root)
        self.assertEqual((second['summary']['planned'], second['summary']['already_applied'],
                          second['summary']['would_change_files']), (0, 528, 0))
        self.assertEqual(source_apply.execute(second)['applied'], 0)

    def test_mixed_state_applies_only_remaining_operations(self):
        root = self.copy_source('mixed')
        selected = self.before_bundle['operations'][::2]
        by_path = {}
        for operation in selected:
            by_path.setdefault(operation['source_path'], []).append(operation)
        for label, operations in by_path.items():
            path = safe_source(root, label)
            raw = path.read_bytes()
            executable = [dict(op, expected_source_sha256=sha(raw)) for op in operations]
            token_changes = {op['operation_id'] for op in operations
                             if op.get('layout_provenance', {}).get('kind') == 'human_layout'}
            path.write_bytes(patch_bytes(raw, label, executable,
                                         authorized_token_changes=token_changes))
        mixed = source_apply.prepare(root)
        self.assertEqual((mixed['summary']['planned'], mixed['summary']['already_applied']),
                         (264, 264))
        result = source_apply.execute(mixed)
        self.assertEqual((result['applied'], result['already_applied']), (264, 264))
        final = source_apply.prepare(root)
        self.assertEqual((final['summary']['planned'], final['summary']['already_applied']),
                         (0, 528))

    def test_stale_rejected_before_any_write(self):
        root = self.copy_source('stale')
        operation = self.before_bundle['operations'][0]
        path = safe_source(root, operation['source_path'])
        raw = path.read_bytes()
        start, end = operation['matched_span']
        replacement = operation['replacement'] + 'X'
        drift = dict(operation, replacement=replacement,
                     after=operation['before'][:start] + replacement + operation['before'][end:],
                     expected_source_sha256=sha(raw))
        token_changes = ({operation['operation_id']}
                         if operation.get('layout_provenance', {}).get('kind') == 'human_layout'
                         else set())
        path.write_bytes(patch_bytes(raw, operation['source_path'], [drift],
                                     authorized_token_changes=token_changes))
        before = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
        with self.assertRaisesRegex(ValueError, 'STALE_OR_CONFLICT'):
            source_apply.prepare(root)
        self.assertEqual(before, {p.relative_to(root): p.read_bytes()
                                  for p in root.rglob('*') if p.is_file()})

    def test_span_prefix_and_suffix_are_preserved(self):
        operation = next(op for op in self.before_bundle['operations']
                         if op['replacement_type'] == 'span'
                         and op['matched_span'][0] > 0
                         and op['matched_span'][1] < len(op['before']))
        start, end = operation['matched_span']
        self.assertEqual(operation['after'][:start], operation['before'][:start])
        self.assertEqual(operation['after'][start + len(operation['replacement']):],
                         operation['before'][end:])
        output = self.before_bundle['outputs'][operation['source_path']]
        from tools.localization.parser import parse_text
        entry = next(e for e in parse_text(output.decode('utf-8-sig'),
                                           operation['source_path']).entries
                     if e.line == operation['source_line'] and e.string_id == operation['string_id'])
        self.assertEqual(entry.value, operation['after'])


if __name__ == '__main__':
    unittest.main()
