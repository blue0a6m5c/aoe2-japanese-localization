"""Build the Production delta Mod and generated glossary from decisions."""

from dataclasses import dataclass
import html
import json
import os
from pathlib import Path
import shutil
import tempfile

from .parser import parse_text
from . import validator


DEFAULT_OUTPUT_ROOT = Path('dist/local-mod')
DEFAULT_GLOSSARY = Path('glossary/terms.md')
MOD_FOLDER = 'AoE2-DE-Japanese-Localization'
DELTA_RELATIVE_PATH = Path('resources/jp/strings/key-value/key-value-modded-strings-utf8.txt')
INFO = {
    'Author': 'AoE2 Japanese Localization Project',
    'CacheStatus': 0,
    'Title': 'AoE2 Japanese Localization',
    'Description': 'Japanese localization overrides generated from approved project decisions.',
}


class BuildError(ValueError):
    """Raised before an unverified build can be published."""


@dataclass(frozen=True)
class BuildResult:
    decisions: int
    targets: int
    overrides: int
    unchanged: int
    mod_path: Path | None
    glossary_path: Path


def _string_id_key(string_id: str) -> tuple[int, int | str, str]:
    if string_id.isascii() and string_id.isdecimal():
        return (0, int(string_id), string_id)
    return (1, string_id, string_id)


def serialize_delta(values: dict[str, str]) -> bytes:
    text = ''.join(f'{sid} "{values[sid]}"\n' for sid in sorted(values, key=_string_id_key))
    return text.encode('utf-8')


def verify_delta(payload: bytes, expected: dict[str, str]) -> None:
    if payload.startswith(b'\xef\xbb\xbf'):
        raise BuildError('generated delta unexpectedly contains a UTF-8 BOM')
    if b'\r' in payload or not payload.endswith(b'\n'):
        raise BuildError('generated delta must use LF and end with a newline')
    try:
        text = payload.decode('utf-8', errors='strict')
    except UnicodeDecodeError as exc:
        raise BuildError(f'generated delta is not valid UTF-8: {exc}') from exc
    parsed = parse_text(text, '<generated delta>')
    if parsed.issues:
        details = '; '.join(f'line {issue.line}: {issue.message}' for issue in parsed.issues[:5])
        raise BuildError(f'generated delta does not parse cleanly: {details}')
    actual: dict[str, str] = {}
    duplicates = []
    for entry in parsed.entries:
        if entry.string_id in actual:
            duplicates.append(entry.string_id)
        else:
            actual[entry.string_id] = entry.value
    if duplicates:
        raise BuildError('generated delta contains duplicate String IDs: ' + ', '.join(sorted(set(duplicates))))
    missing = expected.keys() - actual.keys()
    extra = actual.keys() - expected.keys()
    if missing or extra:
        parts = []
        if missing:
            parts.append('missing: ' + ', '.join(sorted(missing, key=_string_id_key)))
        if extra:
            parts.append('extra: ' + ', '.join(sorted(extra, key=_string_id_key)))
        raise BuildError('generated delta String ID set mismatch (' + '; '.join(parts) + ')')
    wrong = [sid for sid in expected if actual[sid] != expected[sid]]
    if wrong:
        raise BuildError('generated delta value mismatch: ' + ', '.join(sorted(wrong, key=_string_id_key)))


def _markdown_cell(value: object) -> str:
    if value is None:
        return ''
    return html.escape(str(value), quote=False).replace('|', r'\|').replace('\r\n', '<br>').replace('\n', '<br>').replace('\r', '<br>')


def render_glossary(data: dict) -> str:
    records = data['records']
    categories = sorted({record['category'] for record in records})
    lines = [
        '# 翻訳裁定一覧',
        '',
        '> **AUTO-GENERATED — DO NOT EDIT**',
        '>',
        '> Source: `decisions/translations.json`. This is a generated view; `decisions/` is the source of truth.',
        '',
        f'Decision records: **{len(records)}**',
        '',
    ]
    for category in categories:
        selected = sorted((record for record in records if record['category'] == category),
                          key=lambda record: record['id'])
        lines.extend((f'## {category} ({len(selected)})', '',
                      '| Decision ID | English | Approved Japanese | Type | Reason | Targets | Notes |',
                      '|---|---|---|---|---|---|---|'))
        for record in selected:
            targets = ', '.join(f'{target["string_id"]} ({target["role"]})'
                                for target in sorted(record['targets'], key=lambda item: _string_id_key(item['string_id'])))
            cells = (record['id'], record['english'], record['translation'], record['decision'],
                     record['reason'], targets, record.get('notes'))
            lines.append('| ' + ' | '.join(_markdown_cell(value) for value in cells) + ' |')
        lines.append('')
    return '\n'.join(lines)


def _info_payload() -> bytes:
    return (json.dumps(INFO, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def _write_staging(staging: Path, delta: bytes | None, glossary: bytes) -> tuple[Path | None, Path]:
    staged_root = None
    if delta is not None:
        mod = staging / 'local-mod' / MOD_FOLDER
        delta_path = mod / DELTA_RELATIVE_PATH
        delta_path.parent.mkdir(parents=True)
        delta_path.write_bytes(delta)
        (mod / 'info.json').write_bytes(_info_payload())
        staged_root = staging / 'local-mod'
    glossary_path = staging / 'terms.md'
    glossary_path.write_bytes(glossary)
    return staged_root, glossary_path


def _replace_pair(staged_root: Path | None, output_root: Path,
                  staged_glossary: Path, glossary_path: Path) -> None:
    output_root.parent.mkdir(parents=True, exist_ok=True)
    glossary_path.parent.mkdir(parents=True, exist_ok=True)
    staging = staged_glossary.parent
    backup_root = staging / 'previous-local-mod'
    backup_glossary = staging / 'previous-terms.md'
    root_backed_up = glossary_backed_up = root_published = glossary_published = False
    try:
        if output_root.exists():
            os.replace(output_root, backup_root)
            root_backed_up = True
        if glossary_path.exists():
            os.replace(glossary_path, backup_glossary)
            glossary_backed_up = True
        if staged_root is not None:
            os.replace(staged_root, output_root)
            root_published = True
        os.replace(staged_glossary, glossary_path)
        glossary_published = True
    except OSError as exc:
        if glossary_published and glossary_path.exists():
            glossary_path.unlink()
        if root_published and output_root.exists():
            shutil.rmtree(output_root)
        if glossary_backed_up and backup_glossary.exists():
            os.replace(backup_glossary, glossary_path)
        if root_backed_up and backup_root.exists():
            os.replace(backup_root, output_root)
        raise BuildError(f'could not publish complete build: {exc}') from exc
    if backup_root.exists():
        shutil.rmtree(backup_root)
    if backup_glossary.exists():
        backup_glossary.unlink()


def _validate_output_paths(source_root: Path, output_root: Path, glossary_path: Path) -> None:
    source = source_root.resolve()
    output = output_root.resolve()
    glossary = glossary_path.resolve()
    if output.name != 'local-mod' or output.parent.name != 'dist':
        raise BuildError('Production output root must be a dist/local-mod directory')
    if glossary.name != 'terms.md' or glossary.parent.name != 'glossary':
        raise BuildError('generated glossary path must be a glossary/terms.md file')
    if output.is_relative_to(source) or glossary.is_relative_to(source):
        raise BuildError('build outputs must not be inside the read-only source root')
    if glossary.is_relative_to(output) or output.is_relative_to(glossary):
        raise BuildError('Mod output and generated glossary paths must not overlap')


def build_repository(decisions_path: Path = validator.DEFAULT_DECISIONS,
                     source_root: Path = Path('source'),
                     output_root: Path = DEFAULT_OUTPUT_ROOT,
                     glossary_path: Path = DEFAULT_GLOSSARY) -> BuildResult:
    decisions_path = Path(decisions_path)
    source_root = Path(source_root)
    output_root = Path(output_root)
    glossary_path = Path(glossary_path)
    _validate_output_paths(source_root, output_root, glossary_path)

    data = validator.load_decisions(decisions_path)
    en = validator.load_source(source_root, 'en')
    jp = validator.load_source(source_root, 'jp')
    result = validator.validate(data, en, jp)
    canonical = {}
    for sid in result.resolved:
        entry = jp.resolved(sid)
        if entry is None:
            raise BuildError(f'Japanese source resolution failed for String ID {sid}')
        canonical[sid] = entry.value
    overrides = {sid: value for sid, value in result.resolved.items() if value != canonical[sid]}
    delta = serialize_delta(overrides) if overrides else None
    if delta is not None:
        verify_delta(delta, overrides)
    glossary = render_glossary(data).encode('utf-8')
    if glossary.startswith(b'\xef\xbb\xbf') or b'\r' in glossary or not glossary.endswith(b'\n'):
        raise BuildError('generated glossary encoding or newline validation failed')

    output_root_parent = output_root.parent.resolve()
    output_root_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.localization-build-', dir=output_root_parent) as temporary:
        staged_root, staged_glossary = _write_staging(Path(temporary), delta, glossary)
        if staged_root is not None:
            verify_delta((staged_root / MOD_FOLDER / DELTA_RELATIVE_PATH).read_bytes(), overrides)
            if json.loads((staged_root / MOD_FOLDER / 'info.json').read_text(encoding='utf-8')) != INFO:
                raise BuildError('staged info.json validation failed')
        if staged_glossary.read_bytes() != glossary:
            raise BuildError('staged glossary validation failed')
        _replace_pair(staged_root, output_root.resolve(), staged_glossary, glossary_path.resolve())

    mod_path = output_root / MOD_FOLDER if overrides else None
    return BuildResult(result.decisions, result.targets, len(overrides),
                       result.targets - len(overrides), mod_path, glossary_path)
