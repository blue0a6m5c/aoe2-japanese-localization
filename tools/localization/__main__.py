"""Run with python -m tools.localization; all text output is UTF-8 JSON."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from .analysis import (CATEGORIES, all_ids, classify, legacy_summary, load_datasets, row, summary)


def positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('Must be positive')
    return number


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Read-only AoK/AoC/HD/DE localization analysis')
    parser.add_argument('--source-root', type=Path, default=Path('source'))
    parser.add_argument('--config', type=Path, help='JSON object mapping dataset names to directories under source-root')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('stats', help='Counts, categories, and source SHA-256 inventory')
    commands.add_parser('legacy-stats', help='Legacy DLL counts, ranges, overlaps, and generation ID intersections')
    show = commands.add_parser('show', help='Show all occurrences of a String ID across datasets')
    show.add_argument('string_id')
    for name in ('search', 'compare', 'changes', 'report', 'issues'):
        cmd = commands.add_parser(name)
        if name == 'search':
            cmd.add_argument('query')
        else:
            cmd.add_argument('--query', default=None, help='Literal substring search (no regex)')
        cmd.add_argument('--dataset', action='append', help='Search these datasets (OR); repeatable')
        cmd.add_argument('--ignore-case', action='store_true')
        cmd.add_argument('--category', choices=CATEGORIES, action='append', default=[], help='Repeat for AND')
        cmd.add_argument('--missing', action='append', default=[], help='Dataset name; repeat for AND')
        cmd.add_argument('--id-type', choices=('all', 'numeric', 'symbolic'), default='all')
        cmd.add_argument('--limit', type=positive, default=50)
        cmd.add_argument('--offset', type=int, default=0)
        cmd.add_argument('--values', action='store_true', help='Include raw values; at most 200 rows per invocation')
        if name == 'report':
            cmd.add_argument('--output', type=Path, required=True, help='New JSON file inside reports/ only')
    return parser


def selected_ids(args, datasets) -> list[str]:
    names = args.dataset or list(datasets)
    unknown = (set(names) | set(args.missing)) - set(datasets)
    if unknown:
        raise ValueError('Unknown dataset(s): ' + ', '.join(sorted(unknown)))
    if args.offset < 0:
        raise ValueError('--offset must be nonnegative')
    if args.values and args.limit > 200:
        raise ValueError('--values requires --limit <= 200')
    result = []
    for sid in all_ids(datasets):
        flags = classify(sid, datasets)
        if not set(args.category).issubset(flags):
            continue
        if args.command == 'changes' and not {'en_changed', 'jp_changed'}.intersection(flags):
            continue
        if any(sid in datasets[r].entries for r in args.missing):
            continue
        numeric = sid.isascii() and sid.isdecimal()
        if args.id_type != 'all' and (args.id_type == 'numeric') != numeric:
            continue
        if args.query is not None:
            query = args.query.casefold() if args.ignore_case else args.query
            if not any(query in (e.value.casefold() if args.ignore_case else e.value)
                       for n in names for e in datasets[n].entries.get(sid, [])):
                continue
        result.append(sid)
    return result


def write_report(path: Path, content: str, source_root: Path) -> None:
    target = path.resolve()
    allowed = (Path.cwd() / 'reports').resolve()
    source = source_root.resolve()
    # Resolve links before containment checks. Never overwrite an existing file.
    if (not target.is_relative_to(allowed) or target.is_relative_to(source)
            or target.is_relative_to((Path.cwd() / 'source').resolve())):
        raise ValueError('Reports must be written inside reports/ and outside source/')
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(content + '\n')


def main(argv=None) -> int:
    parser = argument_parser()
    args = parser.parse_args(argv)
    try:
        config = json.loads(args.config.read_text(encoding='utf-8-sig')) if args.config else None
        datasets = load_datasets(args.source_root, config)
        stats = summary(datasets)
        inventory = [dict(dataset=n, path=f.path, sha256=f.sha256, size_bytes=f.size_bytes,
                          bom=f.bom, format=f.format, entries=len(f.entries), issues=len(f.issues),
                          empty_resource_slots=len(f.empty_slots), metadata=f.metadata)
                     for n, d in datasets.items() for f in d.files]
        diagnostics = [dict(dataset=n, **{k: v for k, v in asdict(i).items() if k != 'raw'})
                       for n, d in datasets.items() for i in d.issues]
        duplicates = [row(sid, datasets) for sid in all_ids(datasets)
                      if 'duplicate' in classify(sid, datasets)]
        issue_count = len(diagnostics) + stats['duplicate_dataset_id_pairs']
        incomplete = bool(stats['encoding_errors'] or stats['pe_errors'])
        if incomplete and args.command not in ('stats', 'legacy-stats', 'issues'):
            raise ValueError('Input encoding or PE errors make comparison incomplete; inspect stats or issues')
        common = {'schema_version': 2, 'comparison_mode': 'literal_stored_value',
                  'diagnostic_count': len(diagnostics),
                  'duplicate_dataset_id_pairs': stats['duplicate_dataset_id_pairs'],
                  'incomplete': incomplete}
        if args.command == 'stats':
            output = {**common, **stats, 'inventory': inventory, 'legacy': legacy_summary(datasets)}
        elif args.command == 'legacy-stats':
            output = {**common, **legacy_summary(datasets)}
        elif args.command == 'show':
            output = {**common, **row(args.string_id, datasets, True),
                      'diagnostics': [d for d in diagnostics if d['string_id'] == args.string_id]}
        else:
            ids = selected_ids(args, datasets)
            if args.command == 'issues':
                # File-level issues have no ID and always remain visible.
                selected = set(ids)
                items = [dict(type='diagnostic', **d) for d in diagnostics
                         if d['string_id'] is None or d['string_id'] in selected]
                items += [dict(type='duplicate', **r) for r in duplicates if r['string_id'] in selected]
                output = {**common, 'total': len(items), 'offset': args.offset,
                          'items': items[args.offset:args.offset + args.limit]}
            else:
                page = ids[args.offset:args.offset + args.limit]
                output = {**common, 'total': len(ids), 'offset': args.offset,
                          'rows': [row(sid, datasets, args.values) for sid in page]}
                if args.command == 'report':
                    output.update(statistics=stats, inventory=inventory, legacy=legacy_summary(datasets),
                                  filters={k: getattr(args, k) for k in
                                           ('query', 'dataset', 'ignore_case', 'category', 'missing', 'id_type', 'limit', 'offset', 'values')})
        content = json.dumps(output, ensure_ascii=False, indent=2) + '\n'
        if args.command == 'report':
            write_report(args.output, content.rstrip('\n'), args.source_root)
            print(json.dumps({'report': args.output.as_posix(), 'total': output['total'],
                              'rows_written': len(output['rows'])}, ensure_ascii=False))
        else:
            print(content, end='')
        if issue_count:
            print(f'Input diagnostics: {len(diagnostics)}; duplicate dataset/ID pairs: '
                  f'{stats["duplicate_dataset_id_pairs"]}. Inspect issues; ambiguous values are not resolved.', file=sys.stderr)
        return 1 if issue_count else 0
    except (OSError, ValueError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    raise SystemExit(main())
