import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools.localization.analysis import Dataset
from tools.localization.parser import Entry, ParsedFile
from tools.localization.validator import (ValidationError, load_decisions, validate,
                                          validate_repository)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_EN = ROOT / 'source/de/en/key-value/key-value-strings-utf8.txt'
SOURCE_JP = ROOT / 'source/de/jp/key-value/key-value-strings-utf8.txt'


def dataset(name, values):
    result = Dataset(name)
    entries = [Entry(sid, value, f'{name}.txt', line) for line, (sid, value) in enumerate(values.items(), 1)]
    result.add(ParsedFile(f'{name}.txt', entries=entries))
    return result


def sources(values=None):
    values = values or {'1': ('Thing', '旧名')}
    return (dataset('de_en', {sid: pair[0] for sid, pair in values.items()}),
            dataset('de_jp', {sid: pair[1] for sid, pair in values.items()}))


def record(*, decision_id='thing_unit', sid='1', role='name', text=None):
    target = {'string_id': sid, 'role': role}
    if text is not None:
        target['text'] = text
    return {
        'id': decision_id,
        'english': 'Thing',
        'category': 'unit',
        'translation': '承認名',
        'decision': 'revise',
        'reason': 'Human-approved fixture.',
        'notes': None,
        'targets': [target],
    }


def decision_data(*records):
    return {'schema_version': 1, 'records': list(records or (record(),))}


class DecisionValidatorTests(unittest.TestCase):
    @unittest.skipUnless(SOURCE_EN.is_file() and SOURCE_JP.is_file(), 'local DE source is not installed')
    def test_current_decisions_all_pass(self):
        result = validate_repository(ROOT / 'decisions/translations.json', ROOT / 'source')
        self.assertEqual((result.decisions, result.targets, len(result.resolved)), (195, 869, 869))

    def assert_rejected(self, data, en=None, jp=None, contains=None):
        en, jp = (en, jp) if en is not None else sources()
        with self.assertRaises(ValidationError) as caught:
            validate(data, en, jp)
        if contains:
            self.assertIn(contains, str(caught.exception))
        return caught.exception

    def test_duplicate_decision_id_rejected(self):
        second = record(sid='2')
        en, jp = sources({'1': ('Thing', '旧名'), '2': ('Thing', '旧名')})
        self.assert_rejected(decision_data(record(), second), en, jp, 'duplicate decision ID')

    def test_duplicate_target_rejected_even_when_value_would_match(self):
        second = record(decision_id='other_unit')
        self.assert_rejected(decision_data(record(), second), contains='duplicate Production target')

    def test_missing_string_id_rejected(self):
        en, jp = sources({'2': ('Other', '別')})
        error = self.assert_rejected(decision_data(), en, jp, 'English source String ID is missing')
        self.assertIn('String ID=1', str(error))

    def test_unknown_role_rejected(self):
        self.assert_rejected(decision_data(record(role='mystery')), contains="unknown role 'mystery'")

    def test_full_text_requires_explicit_text(self):
        self.assert_rejected(decision_data(record(role='full_text')), contains='target.text for full_text')

    def test_empty_target_text_rejected(self):
        self.assert_rejected(decision_data(record(role='compact_name', text='')),
                             contains='target.text to be a non-empty string')

    def test_name_target_text_rejected(self):
        self.assert_rejected(decision_data(record(role='name', text='明示値')),
                             contains='name targets must not define target.text')

    def test_compact_name_text_override_and_literal_newline(self):
        en, jp = sources({'1': ('Thing', r'旧\n名')})
        result = validate(decision_data(record(role='compact_name', text=r'承認\n名')), en, jp)
        self.assertEqual(result.resolved['1'], r'承認\n名')
        self.assertNotIn('\n', result.resolved['1'])

    def test_action_text_override(self):
        en, jp = sources({'1': ('Research Thing (effect)', '旧名の研究 (効果)')})
        result = validate(decision_data(record(role='action', text=r'承認名\n(承認済み効果)')), en, jp)
        self.assertEqual(result.resolved['1'], r'承認名\n(承認済み効果)')

    def test_normal_action_is_resolved_from_known_structure(self):
        en, jp = sources({'1': ('Create Thing', '食い違う旧訳の作成')})
        result = validate(decision_data(record(role='action')), en, jp)
        self.assertEqual(result.resolved['1'], '承認名の作成')

    def test_action_english_anchor_mismatch_rejected(self):
        en, jp = sources({'1': ('Create Other', '食い違う旧訳の作成')})
        self.assert_rejected(decision_data(record(role='action')), en, jp,
                             "expected English action name 'Thing', found 'Other'")

    def test_ambiguous_action_structure_rejected(self):
        en, jp = sources({'1': ('Create Thing', '食い違う旧訳の研究 の作成')})
        self.assert_rejected(decision_data(record(role='action')), en, jp,
                             'exactly one known Japanese action name structure')

    def test_unknown_action_structure_rejected(self):
        en, jp = sources({'1': ('Create Thing', '食い違う旧訳を用意')})
        self.assert_rejected(decision_data(record(role='action')), en, jp,
                             'exactly one known Japanese action name structure')

    def test_help_heading_resolves_only_first_bold_name_slot(self):
        en, jp = sources({'1': ('Create <b>Thing<b> (<cost>)\\nEnglish body',
                                  '<b>食い違う旧訳<b>の作成 (<cost>)\\n日本語本文')})
        result = validate(decision_data(record(role='help_heading')), en, jp)
        self.assertEqual(result.resolved['1'], '<b>承認名<b>の作成 (<cost>)\\n日本語本文')

    def test_help_heading_english_anchor_mismatch_rejected(self):
        en, jp = sources({'1': ('Create <b>Other<b> (<cost>)', '<b>旧名<b>の作成 (<cost>)')})
        self.assert_rejected(decision_data(record(role='help_heading')), en, jp,
                             "expected English bold slot 'Thing', found 'Other'")

    def test_known_reversed_japanese_build_heading_has_one_name_slot(self):
        en, jp = sources({'1': ('Build <b>Thing<b> (<cost>)', '食い違う旧訳<b>の建造<b> (<cost>)')})
        result = validate(decision_data(record(role='help_heading')), en, jp)
        self.assertEqual(result.resolved['1'], '承認名<b>の建造<b> (<cost>)')

    def test_malformed_help_heading_rejected(self):
        en, jp = sources({'1': ('Create <b>Thing<b> (<cost>)', '食い違う旧訳の作成 (<cost>)')})
        self.assert_rejected(decision_data(record(role='help_heading')), en, jp,
                             'Japanese bold name slot')

    def test_json_decode_preserves_game_newline_escape(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'decisions.json'
            payload = decision_data(record(role='compact_name', text=r'承認\n名'))
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
            loaded = load_decisions(path)
        self.assertEqual(loaded['records'][0]['targets'][0]['text'], r'承認\n名')

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'decisions.json'
            path.write_text('{"schema_version":1,"schema_version":1,"records":[]}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Duplicate JSON key'):
                load_decisions(path)

    def test_placeholder_markup_and_escape_corruption_rejected(self):
        en, jp = sources({'1': ('Description', '<b>旧名<b> (<cost>)')})
        cases = {
            'placeholder': '<b>承認名<b>',
            'markup': '承認名 (<cost>)',
            'escape': r'<b>承認名<b> (<cost>)\q',
        }
        for label, text in cases.items():
            with self.subTest(label=label):
                data = decision_data(record(role='full_text', text=text))
                self.assert_rejected(data, en, jp)

    def test_physical_newline_is_rejected(self):
        data = decision_data(record(role='full_text', text='line one\nline two'))
        self.assert_rejected(data, contains='physical newlines are unsupported')

    def test_validation_does_not_modify_source_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            en_path = root / 'source/de/en/key-value/key-value-strings-utf8.txt'
            jp_path = root / 'source/de/jp/key-value/key-value-strings-utf8.txt'
            decisions_path = root / 'decisions.json'
            en_path.parent.mkdir(parents=True)
            jp_path.parent.mkdir(parents=True)
            en_path.write_text('1 "Thing"\n', encoding='utf-8')
            jp_path.write_text('1 "旧名"\n', encoding='utf-8')
            decisions_path.write_text(json.dumps(decision_data(), ensure_ascii=False), encoding='utf-8')
            before = (en_path.read_bytes(), jp_path.read_bytes())
            validate_repository(decisions_path, root / 'source')
            self.assertEqual((en_path.read_bytes(), jp_path.read_bytes()), before)


if __name__ == '__main__':
    unittest.main()
