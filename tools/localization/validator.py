"""Decision-driven Production validation and final-value resolution."""

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import re

from .analysis import Dataset
from .parser import parse_file


DEFAULT_DECISIONS = Path('decisions/translations.json')
SOURCE_FILE = Path('de/{language}/key-value/key-value-strings-utf8.txt')
CATEGORIES = frozenset({'unit', 'technology', 'building', 'ui', 'description', 'other'})
DECISIONS = frozenset({'restore', 'keep_de', 'revise'})
ROLES = frozenset({'name', 'compact_name', 'action', 'help_heading', 'full_text'})
TOP_LEVEL_FIELDS = frozenset({'schema_version', 'records'})
RECORD_FIELDS = frozenset({'id', 'english', 'category', 'gameplay_object', 'translation',
                           'decision', 'reason', 'notes', 'targets'})
REQUIRED_RECORD_FIELDS = RECORD_FIELDS - {'gameplay_object'}
TARGET_FIELDS = frozenset({'string_id', 'role', 'text'})
REQUIRED_TARGET_FIELDS = TARGET_FIELDS - {'text'}
STRING_ID = re.compile(r'[A-Za-z0-9_]+')
TECHNICAL_TOKEN = re.compile(
    r'\\[\s\S]|\\$|<[^>]*>|[<>]|'
    r'%(?:\d+\$)?[-+#0 ]*(?:\d+|\*)?(?:\.(?:\d+|\*))?[hlLzjt]*[A-Za-z%]|%|'
    r'\{[^}]*\}|[{}"\r\n\t]')
KNOWN_ESCAPES = frozenset('nt"\\')


@dataclass(frozen=True)
class Diagnostic:
    message: str
    decision_id: str | None = None
    string_id: str | None = None
    role: str | None = None

    def render(self) -> str:
        context = ', '.join(f'{key}={value}' for key, value in (
            ('decision', self.decision_id), ('String ID', self.string_id), ('role', self.role))
                            if value is not None)
        return f'{context}: {self.message}' if context else self.message


class ValidationError(ValueError):
    def __init__(self, diagnostics: list[Diagnostic]):
        self.diagnostics = tuple(diagnostics)
        super().__init__('; '.join(item.render() for item in diagnostics))


@dataclass(frozen=True)
class ValidationResult:
    decisions: int
    targets: int
    resolved: dict[str, str]
    role_counts: dict[str, int]


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def load_decisions(path: Path = DEFAULT_DECISIONS) -> dict:
    def reject_constant(value):
        raise ValueError(f'Invalid JSON constant: {value}')

    with Path(path).open(encoding='utf-8-sig') as stream:
        return json.load(stream, object_pairs_hook=_strict_object, parse_constant=reject_constant)


def load_source(source_root: Path, language: str) -> Dataset:
    path = Path(source_root) / Path(str(SOURCE_FILE).format(language=language))
    parsed = parse_file(path, f'de_{language}/{path.name}')
    if parsed.issues:
        details = '; '.join(f'line {issue.line}: {issue.message}' for issue in parsed.issues[:5])
        raise ValueError(f'Invalid DE {language} source: {details}')
    dataset = Dataset(f'de_{language}')
    dataset.add(parsed)
    return dataset


def _technical_tokens(value: str, *, include_newlines: bool = True) -> list[str]:
    result = TECHNICAL_TOKEN.findall(value)
    return result if include_newlines else [token for token in result if token not in (r'\n', '\r', '\n')]


def _literal_issue(value: str) -> str | None:
    if '\r' in value or '\n' in value:
        return 'physical newlines are unsupported; use the literal game escape \\n'
    pos = 0
    while pos < len(value):
        if value[pos] == '\\':
            if pos + 1 >= len(value):
                return 'trailing backslash is not a valid game escape'
            if value[pos + 1] not in KNOWN_ESCAPES:
                return f'unknown game escape \\{value[pos + 1]}'
            pos += 2
        else:
            pos += 1
    return None


def _replace_span(value: str, start: int, end: int, replacement: str) -> str:
    return value[:start] + replacement + value[end:]


def _english_action_name(value: str) -> str | None:
    patterns = (
        r'Create (?P<name>.+)',
        r'Build (?P<name>.+)',
        r'Upgrade to (?P<name>.+)',
        r'Research (?P<name>.+?)(?: \(.+\))?',
    )
    matches = [match['name'] for pattern in patterns if (match := re.fullmatch(pattern, value))]
    return matches[0] if len(matches) == 1 else None


def _action_slot(value: str) -> tuple[int, int] | None:
    candidates = []
    for suffix in ('の作成', 'の建造', 'へのアップグレード', 'を建造する'):
        if value.endswith(suffix) and len(value) > len(suffix):
            candidates.append((0, len(value) - len(suffix)))
    for separator in ('の研究', 'を研究'):
        start = 0
        while (index := value.find(separator, start)) >= 0:
            after = index + len(separator)
            if index and (after == len(value) or value[after] in ' :('):
                candidates.append((0, index))
            start = index + 1
    unique = sorted(set(candidates))
    return unique[0] if len(unique) == 1 else None


def _bold_slot(value: str, *, japanese: bool = False) -> tuple[int, int] | None:
    markers = [match.start() for match in re.finditer(re.escape('<b>'), value)]
    if len(markers) < 2:
        return None
    if not japanese:
        start, end = markers[0] + 3, markers[1]
        return (start, end) if start < end else None
    if markers[0] == 0:
        return (3, markers[1]) if markers[1] > 3 else None
    # The current Dromon heading has its first opening marker after the name.
    # Its finite Japanese heading grammar still provides one unambiguous slot.
    between = value[markers[0] + 3:markers[1]]
    if '<' not in value[:markers[0]] and between in ('の作成', 'の建造', 'の研究', 'へのアップグレード'):
        return (0, markers[0])
    return None


def _resolve(record: dict, target: dict, en_value: str, jp_value: str) -> str:
    role = target['role']
    explicit = target.get('text')
    if role == 'name':
        return record['translation']
    if role == 'compact_name':
        return explicit if explicit is not None else record['translation']
    if role == 'full_text':
        if explicit is None:
            raise ValueError('expected target.text for full_text, but it is missing')
        return explicit
    if role == 'help_heading':
        en_slot = _bold_slot(en_value)
        if en_slot is None:
            raise ValueError('expected an unambiguous first English bold name slot')
        actual_english = en_value[slice(*en_slot)]
        if actual_english != record['english']:
            raise ValueError(f'expected English bold slot {record["english"]!r}, found {actual_english!r}')
        jp_slot = _bold_slot(jp_value, japanese=True)
        if jp_slot is None:
            raise ValueError('expected an unambiguous first Japanese bold name slot')
        return _replace_span(jp_value, *jp_slot, record['translation'])
    if role == 'action':
        if explicit is not None:
            return explicit
        action_name = _english_action_name(en_value)
        if action_name != record['english']:
            raise ValueError(f'expected English action name {record["english"]!r}, found {action_name!r}')
        slot = _action_slot(jp_value)
        if slot is None:
            raise ValueError('expected exactly one known Japanese action name structure')
        return _replace_span(jp_value, *slot, record['translation'])
    raise ValueError(f'unknown role {role!r}')


def _schema_diagnostics(data) -> list[Diagnostic]:
    errors = []
    if not isinstance(data, dict):
        return [Diagnostic('expected a JSON object at the top level')]
    missing = TOP_LEVEL_FIELDS - data.keys()
    unknown = data.keys() - TOP_LEVEL_FIELDS
    if missing:
        errors.append(Diagnostic('missing top-level field(s): ' + ', '.join(sorted(missing))))
    if unknown:
        errors.append(Diagnostic('unknown top-level field(s): ' + ', '.join(sorted(unknown))))
    if data.get('schema_version') != 1 or type(data.get('schema_version')) is not int:
        errors.append(Diagnostic('expected integer schema_version 1'))
    records = data.get('records')
    if not isinstance(records, list):
        errors.append(Diagnostic('expected records to be an array'))
        return errors
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(Diagnostic(f'expected record {index} to be an object'))
            continue
        decision_id = record.get('id') if isinstance(record.get('id'), str) else f'index {index}'
        missing = REQUIRED_RECORD_FIELDS - record.keys()
        unknown = record.keys() - RECORD_FIELDS
        if missing:
            errors.append(Diagnostic('missing record field(s): ' + ', '.join(sorted(missing)), decision_id))
        if unknown:
            errors.append(Diagnostic('unknown record field(s): ' + ', '.join(sorted(unknown)), decision_id))
        for field in ('id', 'english', 'translation', 'reason'):
            if not isinstance(record.get(field), str) or not record.get(field):
                errors.append(Diagnostic(f'expected non-empty string field {field}', decision_id))
        if record.get('category') not in CATEGORIES:
            errors.append(Diagnostic(f'unknown category {record.get("category")!r}', decision_id))
        if record.get('decision') not in DECISIONS:
            errors.append(Diagnostic(f'unknown decision {record.get("decision")!r}', decision_id))
        if record.get('notes') is not None and not isinstance(record.get('notes'), str):
            errors.append(Diagnostic('expected notes to be a string or null', decision_id))
        if 'gameplay_object' in record and not isinstance(record['gameplay_object'], str):
            errors.append(Diagnostic('expected gameplay_object to be a string', decision_id))
        targets = record.get('targets')
        if not isinstance(targets, list) or not targets:
            errors.append(Diagnostic('expected targets to be a non-empty array', decision_id))
            continue
        for target_index, target in enumerate(targets):
            if not isinstance(target, dict):
                errors.append(Diagnostic(f'expected target {target_index} to be an object', decision_id))
                continue
            sid, role = target.get('string_id'), target.get('role')
            missing = REQUIRED_TARGET_FIELDS - target.keys()
            unknown = target.keys() - TARGET_FIELDS
            if missing:
                errors.append(Diagnostic('missing target field(s): ' + ', '.join(sorted(missing)), decision_id,
                                         sid if isinstance(sid, str) else None,
                                         role if isinstance(role, str) else None))
            if unknown:
                errors.append(Diagnostic('unknown target field(s): ' + ', '.join(sorted(unknown)), decision_id,
                                         sid if isinstance(sid, str) else None,
                                         role if isinstance(role, str) else None))
            if not isinstance(sid, str) or STRING_ID.fullmatch(sid) is None:
                errors.append(Diagnostic(f'expected an ASCII alphanumeric/underscore String ID, found {sid!r}', decision_id,
                                         sid if isinstance(sid, str) else None,
                                         role if isinstance(role, str) else None))
            if role not in ROLES:
                errors.append(Diagnostic(f'unknown role {role!r}', decision_id,
                                         sid if isinstance(sid, str) else None,
                                         role if isinstance(role, str) else None))
            if 'text' in target and (not isinstance(target['text'], str) or not target['text']):
                errors.append(Diagnostic('expected target.text to be a non-empty string', decision_id,
                                         sid if isinstance(sid, str) else None,
                                         role if isinstance(role, str) else None))
            if role == 'name' and 'text' in target:
                errors.append(Diagnostic('name targets must not define target.text', decision_id,
                                         sid if isinstance(sid, str) else None, role))
    return errors


def validate(data: dict, en: Dataset, jp: Dataset) -> ValidationResult:
    errors = _schema_diagnostics(data)
    if errors:
        raise ValidationError(errors)

    records = data['records']
    ids = {}
    owners = {}
    for record_index, record in enumerate(records):
        decision_id = record['id']
        if decision_id in ids:
            errors.append(Diagnostic(f'duplicate decision ID; first used at record {ids[decision_id]}', decision_id))
        else:
            ids[decision_id] = record_index
        for target in record['targets']:
            sid, role = target['string_id'], target['role']
            if sid in owners:
                previous = owners[sid]
                errors.append(Diagnostic(
                    f'duplicate Production target; already owned by decision {previous[0]!r} as role {previous[1]!r}',
                    decision_id, sid, role))
            else:
                owners[sid] = (decision_id, role)
    if errors:
        raise ValidationError(errors)

    resolved = {}
    role_counts = Counter()
    for record in records:
        for target in record['targets']:
            sid, role = target['string_id'], target['role']
            context = dict(decision_id=record['id'], string_id=sid, role=role)
            en_entry, jp_entry = en.resolved(sid), jp.resolved(sid)
            if en_entry is None:
                state = 'missing' if sid not in en.entries else 'duplicate or otherwise ambiguous'
                errors.append(Diagnostic(f'English source String ID is {state}', **context))
                continue
            if jp_entry is None:
                state = 'missing' if sid not in jp.entries else 'duplicate or otherwise ambiguous'
                errors.append(Diagnostic(f'Japanese source String ID is {state}', **context))
                continue
            try:
                final = _resolve(record, target, en_entry.value, jp_entry.value)
            except ValueError as exc:
                errors.append(Diagnostic(str(exc), **context))
                continue
            literal_issue = _literal_issue(final)
            if literal_issue:
                errors.append(Diagnostic(literal_issue, **context))
                continue
            layout_value = 'text' in target or role == 'compact_name'
            before_tokens = _technical_tokens(jp_entry.value, include_newlines=not layout_value)
            after_tokens = _technical_tokens(final, include_newlines=not layout_value)
            if before_tokens != after_tokens:
                errors.append(Diagnostic(
                    f'technical structure changed; expected tokens {before_tokens!r}, found {after_tokens!r}',
                    **context))
                continue
            resolved[sid] = final
            role_counts[role] += 1
    if errors:
        raise ValidationError(errors)
    return ValidationResult(len(records), len(owners), resolved, dict(sorted(role_counts.items())))


def validate_repository(decisions_path: Path = DEFAULT_DECISIONS,
                        source_root: Path = Path('source')) -> ValidationResult:
    data = load_decisions(decisions_path)
    return validate(data, load_source(source_root, 'en'), load_source(source_root, 'jp'))
