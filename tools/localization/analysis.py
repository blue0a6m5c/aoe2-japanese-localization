"""Dataset inventory and exact, conservative String ID comparisons."""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .parser import Entry, Issue, ParsedFile, parse_file


DEFAULT_DATASETS = {'hd_en': 'hd/en', 'hd_jp': 'hd/jp',
                    'de_en': 'de/en/key-value', 'de_jp': 'de/jp/key-value'}
ROLES = tuple(DEFAULT_DATASETS)
CATEGORIES = ('all_four', 'en_changed', 'jp_changed', 'jp_only_changed',
              'de_added', 'hd_only', 'missing', 'duplicate', 'parse_error', 'ambiguous')


def id_sort(key: str) -> tuple:
    return (0, int(key), key) if key.isascii() and key.isdecimal() else (1, key)


@dataclass
class Dataset:
    name: str
    files: list[ParsedFile] = field(default_factory=list)
    entries: dict[str, list[Entry]] = field(default_factory=lambda: defaultdict(list))
    issues: list[Issue] = field(default_factory=list)
    invalid_ids: set[str] = field(default_factory=set)

    def add(self, parsed: ParsedFile) -> None:
        self.files.append(parsed)
        for entry in parsed.entries:
            self.entries[entry.string_id].append(entry)
        self.issues.extend(parsed.issues)
        self.invalid_ids.update(i.string_id for i in parsed.issues if i.string_id is not None)

    def resolved(self, sid: str) -> Entry | None:
        entries = self.entries.get(sid, [])
        if len(entries) == 1 and sid not in self.invalid_ids and not entries[0].ambiguous:
            return entries[0]
        return None

    def stats(self) -> dict:
        return {'files': len(self.files), 'entries': sum(map(len, self.entries.values())),
                'unique_ids': len(self.entries),
                'numeric_ids': sum(k.isascii() and k.isdecimal() for k in self.entries),
                'symbolic_ids': sum(not (k.isascii() and k.isdecimal()) for k in self.entries),
                'comparable_ids': sum(self.resolved(k) is not None for k in self.entries),
                'duplicate_ids': sum(len(v) > 1 for v in self.entries.values()),
                'duplicate_extra_entries': sum(len(v) - 1 for v in self.entries.values()),
                'issues': dict(sorted(Counter(i.kind for i in self.issues).items()))}


def load_datasets(root: Path, mapping: dict[str, str] | None = None) -> dict[str, Dataset]:
    mapping = DEFAULT_DATASETS if mapping is None else mapping
    if not isinstance(mapping, dict) or not all(isinstance(k, str) and isinstance(v, str)
                                               for k, v in mapping.items()):
        raise ValueError('Dataset configuration must map names to directory strings')
    if not set(ROLES).issubset(mapping):
        raise ValueError('Dataset configuration must include: ' + ', '.join(ROLES))
    datasets = {}
    for name, relative in sorted(mapping.items()):
        directory = root / relative
        if not directory.is_dir():
            raise ValueError(f'Missing dataset directory: {directory}')
        # Every .txt in the selected directory, recursively; no basename assumptions.
        files = sorted((p for p in directory.rglob('*') if p.is_file() and p.suffix.lower() == '.txt'),
                       key=lambda p: p.relative_to(directory).as_posix())
        if not files:
            raise ValueError(f'No .txt files in dataset: {directory}')
        dataset = Dataset(name)
        for path in files:
            label = f'{name}/{path.relative_to(directory).as_posix()}'
            dataset.add(parse_file(path, label))
        datasets[name] = dataset
    return datasets


def classify(sid: str, datasets: dict[str, Dataset]) -> list[str]:
    present = {role for role in ROLES if sid in datasets[role].entries}
    flags = set()
    if len(present) == 4:
        flags.add('all_four')
    else:
        flags.add('missing')
    hd = bool(present & {'hd_en', 'hd_jp'})
    de = bool(present & {'de_en', 'de_jp'})
    if de and not hd:
        flags.add('de_added')
    if hd and not de:
        flags.add('hd_only')
    values = {r: datasets[r].resolved(sid) for r in ROLES}
    for lang in ('en', 'jp'):
        old, new = values[f'hd_{lang}'], values[f'de_{lang}']
        if old is not None and new is not None and old.value != new.value:
            flags.add(f'{lang}_changed')
    if ('jp_changed' in flags and values['hd_en'] is not None and values['de_en'] is not None
            and values['hd_en'].value == values['de_en'].value):
        flags.add('jp_only_changed')
    if any(len(d.entries.get(sid, [])) > 1 for d in datasets.values()):
        flags.update(('duplicate', 'ambiguous'))
    if any(sid in d.invalid_ids for d in datasets.values()):
        flags.add('ambiguous')
    if any(i.string_id == sid and i.kind == 'malformed' for d in datasets.values() for i in d.issues):
        flags.add('parse_error')
    return [c for c in CATEGORIES if c in flags]


def all_ids(datasets: dict[str, Dataset]) -> list[str]:
    return sorted(set().union(*(set(d.entries) | d.invalid_ids for d in datasets.values())), key=id_sort)


def summary(datasets: dict[str, Dataset]) -> dict:
    core = {r: datasets[r] for r in ROLES}
    counts = Counter(c for sid in all_ids(core) for c in classify(sid, core))
    hd = set(datasets['hd_en'].entries) | set(datasets['hd_jp'].entries)
    de = set(datasets['de_en'].entries) | set(datasets['de_jp'].entries)
    return {'datasets': {n: d.stats() for n, d in datasets.items()},
            'comparison': {'union_ids': len(hd | de), 'hd_de_common_ids': len(hd & de),
                           **{c: counts[c] for c in CATEGORIES}},
            'duplicate_dataset_id_pairs': sum(d.stats()['duplicate_ids'] for d in datasets.values()),
            'duplicate_distinct_ids': len({k for d in datasets.values() for k,v in d.entries.items() if len(v)>1}),
            'malformed_entries': sum(i.kind == 'malformed' for d in datasets.values() for i in d.issues),
            'encoding_errors': sum(i.kind == 'encoding_error' for d in datasets.values() for i in d.issues)}


def row(sid: str, datasets: dict[str, Dataset], include_values: bool = False) -> dict:
    cells = {}
    for name, dataset in datasets.items():
        entries = dataset.entries.get(sid, [])
        cells[name] = {'state': ('missing' if not entries else
                                'resolved' if dataset.resolved(sid) is not None else 'ambiguous'),
                       'occurrences': [dict(path=e.path, line=e.line,
                                            **({'value': e.value} if include_values else {})) for e in entries]}
    return {'string_id': sid, 'categories': classify(sid, datasets), 'datasets': cells}
