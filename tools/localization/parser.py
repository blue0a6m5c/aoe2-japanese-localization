"""Lossless value parsing; no game loading-order or rendering assumptions."""

from dataclasses import dataclass, field
from pathlib import Path
import hashlib
import re


KEY = re.compile(r'[A-Za-z0-9_]+')
HEADER = re.compile(r'[ \t]*([A-Za-z0-9_]+)[ \t]+"')
KNOWN_ESCAPES = frozenset('nt"\\')


@dataclass(frozen=True)
class Entry:
    string_id: str
    value: str  # Exact text inside quotes, including literal backslashes.
    path: str
    line: int | None
    ambiguous: bool = False
    generation: str | None = None
    language: str | None = None
    resource: dict | None = None
    value_format: str = 'key_value_raw'


@dataclass(frozen=True)
class Issue:
    kind: str
    path: str
    line: int
    message: str
    string_id: str | None = None
    raw: str = ''  # Available for local investigation, omitted from reports.


@dataclass
class ParsedFile:
    path: str
    entries: list[Entry] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    sha256: str = ''
    size_bytes: int = 0
    bom: bool = False
    format: str = 'key_value'
    metadata: dict = field(default_factory=dict)
    empty_slots: list[Entry] = field(default_factory=list)
    raw_bytes: bytes | None = field(default=None, repr=False, compare=False)


def parse_text(text: str, path: str = '<memory>') -> ParsedFile:
    result = ParsedFile(path)
    # Only physical CRLF/LF/CR delimit records; Unicode separators are value data.
    for number, raw in enumerate(re.split(r'\r\n|\n|\r', text.removeprefix('\ufeff')), 1):
        if not raw.strip(' \t') or raw.lstrip(' \t').startswith('//'):
            continue
        match = HEADER.match(raw)
        token = raw.lstrip(' \t').split(maxsplit=1)[0] if raw.strip() else ''
        sid = token if KEY.fullmatch(token) else None

        def malformed(message: str) -> None:
            result.issues.append(Issue('malformed', path, number, message, sid, raw))

        if not match:
            malformed('Expected ASCII key, whitespace, and opening double quote')
            continue
        sid = match[1]
        start = pos = match.end()
        unknown = set()
        while pos < len(raw):
            if raw[pos] == '\\':
                if pos + 1 == len(raw):
                    break
                if raw[pos + 1] not in KNOWN_ESCAPES:
                    unknown.add(raw[pos:pos + 2])
                pos += 2
            elif raw[pos] == '"':
                break
            else:
                pos += 1
        if pos >= len(raw) or raw[pos] != '"':
            malformed('Missing closing quote (physical multiline values are unsupported)')
            continue
        tail = raw[pos + 1:].strip(' \t')
        if tail and not tail.startswith('//'):
            malformed('Unexpected content after closing quote')
            continue
        result.entries.append(Entry(sid, raw[start:pos], path, number, bool(unknown)))
        if unknown:
            result.issues.append(Issue('unknown_escape', path, number,
                                       'Uninterpreted escapes: ' + ', '.join(sorted(unknown)), sid, raw))
    return result


def parse_file(path: Path, label: str | None = None) -> ParsedFile:
    data = path.read_bytes()
    name = label if label is not None else path.as_posix()
    try:
        text = data.decode('utf-8-sig', errors='strict')
    except UnicodeDecodeError as exc:
        # Reject the whole file rather than silently replacing corrupt bytes.
        result = ParsedFile(name, issues=[Issue('encoding_error', name, 0,
                            f'Invalid UTF-8 at byte {exc.start}; whole file excluded')])
    else:
        result = parse_text(text, name)
    result.sha256 = hashlib.sha256(data).hexdigest()
    result.raw_bytes = data
    result.size_bytes = len(data)
    result.bom = data.startswith(b'\xef\xbb\xbf')
    return result
