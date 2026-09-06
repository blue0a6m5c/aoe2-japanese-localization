"""Dataset inventory and exact, conservative String ID comparisons."""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .parser import Entry, Issue, ParsedFile, parse_file
from .legacy import parse_legacy_file


DEFAULT_DATASETS = {'hd_en': 'hd/en', 'hd_jp': 'hd/jp',
                    'de_en': 'de/en/key-value', 'de_jp': 'de/jp/key-value'}
ROLES = tuple(DEFAULT_DATASETS)
LEGACY_DATASETS = {'aok_jp': 'legacy/aok/jp', 'aoc_jp': 'legacy/aoc/jp'}
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
    empty_slots: dict[str, list[Entry]] = field(default_factory=lambda: defaultdict(list))

    def add(self, parsed: ParsedFile) -> None:
        self.files.append(parsed)
        for entry in parsed.entries:
            self.entries[entry.string_id].append(entry)
        for entry in parsed.empty_slots:
            self.empty_slots[entry.string_id].append(entry)
        self.issues.extend(parsed.issues)
        self.invalid_ids.update(i.string_id for i in parsed.issues if i.string_id is not None)

    def resolved(self, sid: str) -> Entry | None:
        entries = self.entries.get(sid, [])
        if len(entries) == 1 and sid not in self.invalid_ids and not entries[0].ambiguous:
            return entries[0]
        return None

    def stats(self) -> dict:
        numeric = [int(k) for k in self.entries if k.isascii() and k.isdecimal()]
        return {'files': len(self.files), 'entries': sum(map(len, self.entries.values())),
                'unique_ids': len(self.entries),
                'numeric_ids': sum(k.isascii() and k.isdecimal() for k in self.entries),
                'symbolic_ids': sum(not (k.isascii() and k.isdecimal()) for k in self.entries),
                'comparable_ids': sum(self.resolved(k) is not None for k in self.entries),
                'duplicate_ids': sum(len(v) > 1 for v in self.entries.values()),
                'duplicate_extra_entries': sum(len(v) - 1 for v in self.entries.values()),
                'duplicate_same_value_ids': sum(len(v) > 1 and len({e.value for e in v}) == 1 for v in self.entries.values()),
                'duplicate_conflicting_ids': sum(len({e.value for e in v}) > 1 for v in self.entries.values()),
                'min_numeric_id': min(numeric, default=None), 'max_numeric_id': max(numeric, default=None),
                'empty_resource_slots': sum(map(len, self.empty_slots.values())),
                'issues': dict(sorted(Counter(i.kind for i in self.issues).items()))}


def load_datasets(root: Path, mapping: dict | None = None) -> dict[str, Dataset]:
    if mapping is None:
        mapping = {**DEFAULT_DATASETS,
                   **{n: p for n, p in LEGACY_DATASETS.items() if (root / p).exists()}}
    if not isinstance(mapping, dict) or not all(isinstance(k, str) for k in mapping):
        raise ValueError('Dataset configuration must map names to directories or format objects')
    if not set(ROLES).issubset(mapping):
        raise ValueError('Dataset configuration must include: ' + ', '.join(ROLES))
    datasets = {}
    for name, spec in sorted(mapping.items()):
        if isinstance(spec, str):
            spec = dict(path=spec, format='pe_rt_string' if name in LEGACY_DATASETS else 'key_value',
                        generation=name.split('_')[0])
        if not isinstance(spec, dict) or not isinstance(spec.get('path'), str):
            raise ValueError(f'Invalid dataset configuration: {name}')
        relative = spec['path']
        file_format = spec.get('format', 'key_value')
        if file_format not in ('key_value', 'pe_rt_string'):
            raise ValueError(f'Unsupported dataset format: {file_format}')
        generation = spec.get('generation', name.split('_')[0])
        if not isinstance(generation, str):
            raise ValueError(f'Generation must be a string: {name}')
        directory = root / relative
        if not directory.is_dir():
            raise ValueError(f'Missing dataset directory: {directory}')
        # Every .txt in the selected directory, recursively; no basename assumptions.
        suffix = '.dll' if file_format == 'pe_rt_string' else '.txt'
        files = sorted((p for p in directory.rglob('*') if p.is_file() and p.suffix.lower() == suffix),
                       key=lambda p: p.relative_to(directory).as_posix())
        if not files:
            raise ValueError(f'No {suffix} files in dataset: {directory}')
        dataset = Dataset(name)
        for path in files:
            label = f'{name}/{path.relative_to(directory).as_posix()}'
            dataset.add(parse_legacy_file(path, generation, label) if file_format == 'pe_rt_string'
                        else parse_file(path, label))
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
            'encoding_errors': sum(i.kind == 'encoding_error' for d in datasets.values() for i in d.issues),
            'pe_errors': sum(i.kind == 'pe_error' for d in datasets.values() for i in d.issues)}


def occurrence(entry: Entry, include_values: bool = False) -> dict:
    result = dict(path=entry.path, line=entry.line, value_format=entry.value_format)
    if entry.resource is not None:
        result.update(generation=entry.generation, language=entry.language, resource=entry.resource)
    if include_values:
        result['value'] = entry.value
    return result


def row(sid: str, datasets: dict[str, Dataset], include_values: bool = False) -> dict:
    cells = {}
    for name, dataset in datasets.items():
        entries = dataset.entries.get(sid, [])
        cells[name] = {'state': (('empty_resource_slot' if sid in dataset.empty_slots else 'missing') if not entries else
                                'resolved' if dataset.resolved(sid) is not None else 'ambiguous'),
                       'occurrences': [occurrence(e, include_values) for e in entries]}
        if sid in dataset.empty_slots:
            cells[name]['empty_resource_slots'] = [occurrence(e, include_values) for e in dataset.empty_slots[sid]]
    return {'string_id': sid, 'categories': classify(sid, datasets), 'datasets': cells}


def pair_summary(left: Dataset, right: Dataset) -> dict:
    """Nonempty resource IDs / parsed text IDs; no inheritance or fallback assumed."""
    a, b = set(left.entries), set(right.entries)
    same = different = unresolved = 0
    for sid in sorted(a & b, key=id_sort):
        old, new = left.resolved(sid), right.resolved(sid)
        if old is None or new is None:
            unresolved += 1
        elif old.value == new.value:
            same += 1
        else:
            different += 1
    return dict(left=left.name, right=right.name, common_ids=len(a & b),
                left_only_ids=len(a - b), right_only_ids=len(b - a),
                same_literal_value_ids=same, different_literal_value_ids=different,
                unresolved_common_ids=unresolved)


def legacy_summary(datasets: dict[str, Dataset]) -> dict:
    from itertools import combinations
    legacy = {n: d for n, d in datasets.items() if any(f.format == 'pe_rt_string' for f in d.files)}
    file_stats, overlaps = [], []
    for name, dataset in legacy.items():
        files = []
        for parsed in dataset.files:
            single = Dataset(parsed.path)
            single.add(parsed)
            files.append(single)
            file_stats.append(dict(dataset=name, path=parsed.path, **single.stats(),
                                   sha256=parsed.sha256, metadata=parsed.metadata))
        for a, b in combinations(files, 2):
            info = pair_summary(a, b)
            all_a, all_b = set(a.entries) | set(a.empty_slots), set(b.entries) | set(b.empty_slots)
            info.update(dataset=name, common_resource_slot_ids=len(all_a & all_b),
                        both_zero_length_ids=len(a.empty_slots.keys() & b.empty_slots.keys()),
                        left_value_right_zero_ids=len(a.entries.keys() & b.empty_slots.keys()),
                        left_zero_right_value_ids=len(a.empty_slots.keys() & b.entries.keys()))
            overlaps.append(info)
    names = [n for n in ('aok_jp', 'aoc_jp', 'hd_jp', 'de_jp', 'hd_en', 'de_en') if n in datasets]
    legacy_ids = set().union(*(set(d.entries) for d in legacy.values()))
    intersections = {'legacy_union_ids': len(legacy_ids)}
    for name in ('hd_jp', 'de_jp'):
        if name in datasets:
            intersections[f'legacy_union_common_with_{name}'] = len(legacy_ids & datasets[name].entries.keys())
    japanese = ('aok_jp', 'aoc_jp', 'hd_jp', 'de_jp')
    if all(n in datasets for n in japanese):
        intersections['all_four_japanese_common_ids'] = len(set.intersection(*(set(datasets[n].entries) for n in japanese)))
    return dict(datasets={n: d.stats() for n, d in legacy.items()}, files=file_stats,
                within_generation_file_pairs=overlaps,
                id_intersections=intersections,
                generation_pairs=[pair_summary(datasets[a], datasets[b]) for a,b in combinations(names, 2)],
                value_comparison='Literal only: resource Unicode versus unexpanded key-value escapes; no normalization')
