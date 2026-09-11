import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools.localization import __main__ as localization_cli
from tools.localization import builder, validator
from tools.localization.parser import parse_text


ROOT = Path(__file__).resolve().parents[1]
SOURCE_EN = ROOT / 'source/de/en/key-value/key-value-strings-utf8.txt'
SOURCE_JP = ROOT / 'source/de/jp/key-value/key-value-strings-utf8.txt'


def record(decision_id='thing_unit', sid='1', translation='承認名', *, role='name', text=None,
           category='unit', notes=None):
    target = {'string_id': sid, 'role': role}
    if text is not None:
        target['text'] = text
    return {
        'id': decision_id,
        'english': 'Thing',
        'category': category,
        'translation': translation,
        'decision': 'revise',
        'reason': 'Human-approved fixture.',
        'notes': notes,
        'targets': [target],
    }


def decisions(*records):
    return {'schema_version': 1, 'records': list(records)}


class Fixture:
    def __init__(self, root: Path, data=None, en=None, jp=None):
        self.root = root
        self.source = root / 'source'
        self.decisions = root / 'decisions.json'
        self.output = root / 'dist/local-mod'
        self.glossary = root / 'glossary/terms.md'
        en = en or {'1': 'Thing', '2': 'Other'}
        jp = jp or {'1': '旧名', '2': '同じ'}
        for language, values in (('en', en), ('jp', jp)):
            path = self.source / f'de/{language}/key-value/key-value-strings-utf8.txt'
            path.parent.mkdir(parents=True)
            path.write_text(''.join(f'{sid} "{value}"\n' for sid, value in values.items()),
                            encoding='utf-8', newline='\n')
        payload = data or decisions(record(), record('same_other', '2', '同じ'))
        self.decisions.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')

    def build(self):
        return builder.build_repository(self.decisions, self.source, self.output, self.glossary)

    @property
    def delta(self):
        return self.output / builder.MOD_FOLDER / builder.DELTA_RELATIVE_PATH


class BuilderTests(unittest.TestCase):
    def test_build_succeeds_and_only_changed_values_are_emitted(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            result = fixture.build()
            self.assertEqual((result.decisions, result.targets, result.overrides, result.unchanged),
                             (2, 2, 1, 1))
            parsed = parse_text(fixture.delta.read_text(encoding='utf-8'))
            self.assertFalse(parsed.issues)
            self.assertEqual([(entry.string_id, entry.value) for entry in parsed.entries], [('1', '承認名')])

    def test_zero_overrides_succeeds_without_publishing_mod_and_removes_stale_mod(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            fixture.build()
            stale = fixture.output / builder.MOD_FOLDER / 'stale.txt'
            stale.write_text('old', encoding='utf-8')
            data = decisions(record(translation='旧名'), record('same_other', '2', '同じ'))
            fixture.decisions.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

            result = fixture.build()

            self.assertEqual((result.overrides, result.unchanged, result.mod_path), (0, 2, None))
            self.assertFalse(fixture.output.exists())
            self.assertIn('Decision records: **2**', fixture.glossary.read_text(encoding='utf-8'))

    def test_zero_override_cli_summary_is_explicit(self):
        result = builder.BuildResult(2, 2, 0, 2, None, Path('glossary/terms.md'))
        output = io.StringIO()
        with mock.patch.object(builder, 'build_repository', return_value=result), redirect_stdout(output):
            self.assertEqual(localization_cli.main(['build']), 0)
        self.assertIn('overrides: 0', output.getvalue())
        self.assertIn('unchanged: 2', output.getvalue())
        self.assertIn('No overrides required', output.getvalue())

    def test_invalid_decisions_are_rejected_before_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            fixture.output.mkdir(parents=True)
            marker = fixture.output / 'existing.txt'
            marker.write_text('complete', encoding='utf-8')
            data = json.loads(fixture.decisions.read_text(encoding='utf-8'))
            del data['records'][0]['reason']
            fixture.decisions.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            with self.assertRaises(validator.ValidationError):
                fixture.build()
            self.assertEqual(marker.read_text(encoding='utf-8'), 'complete')

    def test_source_is_immutable_and_unrelated_dist_output_is_untouched(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            unrelated = fixture.root / 'dist/historical/result.txt'
            unrelated.parent.mkdir(parents=True)
            unrelated.write_text('keep', encoding='utf-8')
            source_before = {path: path.read_bytes() for path in fixture.source.rglob('*') if path.is_file()}
            fixture.build()
            self.assertEqual({path: path.read_bytes() for path in fixture.source.rglob('*') if path.is_file()},
                             source_before)
            self.assertEqual(unrelated.read_text(encoding='utf-8'), 'keep')

    def test_output_paths_inside_source_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            source_before = {path: path.read_bytes() for path in fixture.source.rglob('*') if path.is_file()}
            with self.assertRaisesRegex(builder.BuildError, 'read-only source'):
                builder.build_repository(fixture.decisions, fixture.source,
                                         fixture.source / 'dist/local-mod', fixture.glossary)
            self.assertEqual({path: path.read_bytes() for path in fixture.source.rglob('*') if path.is_file()},
                             source_before)

    def test_non_production_output_root_is_rejected_without_changing_existing_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            fixture.build()
            before = (fixture.delta.read_bytes(), fixture.glossary.read_bytes())
            with self.assertRaisesRegex(builder.BuildError, 'dist/local-mod'):
                builder.build_repository(fixture.decisions, fixture.source,
                                         fixture.root / 'dist/not-production', fixture.glossary)
            self.assertEqual((fixture.delta.read_bytes(), fixture.glossary.read_bytes()), before)

    def test_overlapping_output_and_glossary_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            fixture.build()
            before = (fixture.delta.read_bytes(), fixture.glossary.read_bytes())
            overlapping_output = fixture.root / 'glossary/dist/local-mod'
            overlapping_glossary = overlapping_output / 'glossary/terms.md'
            with self.assertRaisesRegex(builder.BuildError, 'must not overlap'):
                builder.build_repository(fixture.decisions, fixture.source,
                                         overlapping_output, overlapping_glossary)
            self.assertEqual((fixture.delta.read_bytes(), fixture.glossary.read_bytes()), before)

    def test_same_input_produces_byte_identical_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            fixture.build()
            first = (fixture.delta.read_bytes(),
                     (fixture.output / builder.MOD_FOLDER / 'info.json').read_bytes(),
                     fixture.glossary.read_bytes())
            fixture.build()
            second = (fixture.delta.read_bytes(),
                      (fixture.output / builder.MOD_FOLDER / 'info.json').read_bytes(),
                      fixture.glossary.read_bytes())
            self.assertEqual(first, second)

    def test_delta_verifier_detects_extra_missing_duplicate_and_wrong_value(self):
        cases = {
            'extra': b'1 "one"\n2 "two"\n',
            'missing': b'',
            'duplicate': b'1 "one"\n1 "one"\n',
            'wrong': b'1 "wrong"\n',
        }
        for label, payload in cases.items():
            with self.subTest(label=label), self.assertRaises(builder.BuildError):
                builder.verify_delta(payload, {'1': 'one'})

    def test_delta_encoding_order_and_final_newline(self):
        payload = builder.serialize_delta({'10': '十', '2': '二', 'IDS_Z': '記号'})
        self.assertFalse(payload.startswith(b'\xef\xbb\xbf'))
        self.assertNotIn(b'\r', payload)
        self.assertTrue(payload.endswith(b'\n'))
        self.assertEqual(payload.decode('utf-8').splitlines(), ['2 "二"', '10 "十"', 'IDS_Z "記号"'])
        builder.verify_delta(payload, {'10': '十', '2': '二', 'IDS_Z': '記号'})

    def test_delta_verifier_rejects_bom_and_cr_newlines(self):
        cases = {
            'bom': b'\xef\xbb\xbf1 "one"\n',
            'cr': b'1 "one"\r',
            'crlf': b'1 "one"\r\n',
        }
        for label, payload in cases.items():
            with self.subTest(label=label), self.assertRaises(builder.BuildError):
                builder.verify_delta(payload, {'1': 'one'})

    def test_game_escapes_quotes_markup_and_placeholders_are_preserved(self):
        value = r'<b>承認名<b> \"quoted\"\n (%s)'
        data = decisions(record(translation='unused', role='full_text', text=value))
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary), data=data,
                              en={'1': r'<b>Thing<b> \"quoted\"\n (%s)'},
                              jp={'1': r'<b>旧名<b> \"quoted\"\n (%s)'})
            fixture.build()
            parsed = parse_text(fixture.delta.read_text(encoding='utf-8'))
            self.assertEqual(parsed.entries[0].value, value)

    def test_stale_output_is_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            fixture.build()
            stale = fixture.output / builder.MOD_FOLDER / 'stale.txt'
            stale.write_text('old', encoding='utf-8')
            fixture.build()
            self.assertFalse(stale.exists())

    def test_failed_publication_restores_previous_complete_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            fixture.build()
            old_delta = fixture.delta.read_bytes()
            old_glossary = fixture.glossary.read_bytes()
            data = json.loads(fixture.decisions.read_text(encoding='utf-8'))
            data['records'][0]['translation'] = '新しい承認名'
            fixture.decisions.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            real_replace = builder.os.replace

            def fail_glossary_publish(source, destination):
                if Path(source).name == 'terms.md' and Path(destination) == fixture.glossary.resolve():
                    raise OSError('injected failure')
                return real_replace(source, destination)

            with mock.patch.object(builder.os, 'replace', side_effect=fail_glossary_publish):
                with self.assertRaises(builder.BuildError):
                    fixture.build()
            self.assertEqual(fixture.delta.read_bytes(), old_delta)
            self.assertEqual(fixture.glossary.read_bytes(), old_glossary)

    def test_glossary_render_failure_leaves_existing_artifact_pair_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            fixture.build()
            before = (fixture.delta.read_bytes(), fixture.glossary.read_bytes())
            with mock.patch.object(builder, 'render_glossary', side_effect=ValueError('injected failure')):
                with self.assertRaisesRegex(ValueError, 'injected failure'):
                    fixture.build()
            self.assertEqual((fixture.delta.read_bytes(), fixture.glossary.read_bytes()), before)

    def test_glossary_is_deterministic_and_contains_every_decision(self):
        data = decisions(record('zeta', notes='Useful note.'),
                         record('alpha', '2', '同じ', category='other'))
        first = builder.render_glossary(data)
        second = builder.render_glossary(copy.deepcopy(data))
        self.assertEqual(first, second)
        self.assertIn('AUTO-GENERATED — DO NOT EDIT', first)
        self.assertIn('Source: `decisions/translations.json`', first)
        for item in data['records']:
            self.assertIn(item['id'], first)
            self.assertIn(item['reason'], first)
        self.assertIn('Useful note.', first)

    def test_info_json_matches_expected_minimal_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            fixture.build()
            info = json.loads((fixture.output / builder.MOD_FOLDER / 'info.json').read_text(encoding='utf-8'))
            self.assertEqual(info, builder.INFO)
            self.assertEqual(info['Title'], 'AoE2 Japanese Localization')
            self.assertIsInstance(info['CacheStatus'], int)

    @unittest.skipUnless(SOURCE_EN.is_file() and SOURCE_JP.is_file(), 'local DE source is not installed')
    def test_current_decisions_build_and_delta_exactly_match_resolution(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_before = (SOURCE_EN.read_bytes(), SOURCE_JP.read_bytes())
            result = builder.build_repository(ROOT / 'decisions/translations.json', ROOT / 'source',
                                              root / 'dist/local-mod', root / 'glossary/terms.md')
            validation = validator.validate_repository(ROOT / 'decisions/translations.json', ROOT / 'source')
            jp = validator.load_source(ROOT / 'source', 'jp')
            expected = {sid: value for sid, value in validation.resolved.items()
                        if value != jp.resolved(sid).value}
            delta_path = result.mod_path / builder.DELTA_RELATIVE_PATH
            builder.verify_delta(delta_path.read_bytes(), expected)
            parsed = parse_text(delta_path.read_text(encoding='utf-8'))
            actual = {entry.string_id: entry.value for entry in parsed.entries}
            self.assertEqual(actual, expected)
            self.assertEqual((result.decisions, result.targets, result.overrides, result.unchanged),
                             (195, 480, len(expected), 480 - len(expected)))
            glossary = (root / 'glossary/terms.md').read_text(encoding='utf-8')
            data = validator.load_decisions(ROOT / 'decisions/translations.json')
            self.assertEqual(sum(record['id'] in glossary for record in data['records']), 195)
            self.assertEqual((SOURCE_EN.read_bytes(), SOURCE_JP.read_bytes()), source_before)


if __name__ == '__main__':
    unittest.main()
