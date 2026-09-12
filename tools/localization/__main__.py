"""Run with python -m tools.localization; all text output is UTF-8 JSON."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from .analysis import (CATEGORIES, all_ids, classify, legacy_summary, load_datasets, row, summary)
from .gameplay import (FAMILIES, FLAGS, NAME_CATEGORIES, build_inventory, filter_rows, inventory_stats, render_tsv)
from . import restoration
from . import validator
from . import builder


def positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('Must be positive')
    return number


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='AoK/AoC/HD/DE localization analysis and decision-driven production')
    parser.add_argument('--source-root', type=Path, default=Path('source'))
    parser.add_argument('--config', type=Path, help='JSON object mapping dataset names to directories under source-root')
    commands = parser.add_subparsers(dest='command', required=True)
    validate = commands.add_parser('validate', help='Validate approved decisions and resolve final values')
    validate.add_argument('--decisions', type=Path, default=validator.DEFAULT_DECISIONS)
    production_build = commands.add_parser('build', help='Build the decision-driven Production Mod and glossary')
    production_build.add_argument('--decisions', type=Path, default=validator.DEFAULT_DECISIONS)
    commands.add_parser('stats', help='Counts, categories, and source SHA-256 inventory')
    commands.add_parser('legacy-stats', help='Legacy DLL counts, ranges, overlaps, and generation ID intersections')
    restore = commands.add_parser('restoration', help='Legacy policy review proposals; never translation overrides')
    restore.add_argument('--classification', choices=restoration.CLASSES)
    restore.add_argument('--limit', type=positive, default=25)
    restore.add_argument('--output-dir', type=Path)
    names = commands.add_parser('names', help='Evidence-linked gameplay name inventory and audit')
    names.add_argument('--stats', action='store_true')
    names.add_argument('--category', choices=NAME_CATEGORIES)
    names.add_argument('--family', choices=FAMILIES)
    names.add_argument('--flag', choices=FLAGS)
    names.add_argument('--pack')
    names.add_argument('--series')
    names.add_argument('--id', dest='string_id')
    names.add_argument('--review', action='store_true')
    names.add_argument('--primary', action='store_true', help='Full-name offset matches only; omit compact labels/aliases')
    names.add_argument('--suspicious', action='store_true')
    names.add_argument('--limit', type=positive, default=50)
    names.add_argument('--offset', type=int, default=0)
    names.add_argument('--all', action='store_true', help='Export all filtered name candidates; requires --output')
    names.add_argument('--format', choices=('json', 'tsv'), default='json')
    names.add_argument('--output', type=Path)
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
        if args.command == 'validate':
            try:
                result = validator.validate_repository(args.decisions, args.source_root)
            except validator.ValidationError as exc:
                print('Validation failed', file=sys.stderr)
                for diagnostic in exc.diagnostics:
                    print('- ' + diagnostic.render(), file=sys.stderr)
                print(f'errors: {len(exc.diagnostics)}', file=sys.stderr)
                return 1
            print('Validation passed')
            print(f'decisions: {result.decisions}')
            print(f'targets: {result.targets}')
            print(f'resolved: {len(result.resolved)}')
            print('errors: 0')
            print('roles: ' + ', '.join(f'{role}={count}' for role, count in result.role_counts.items()))
            return 0
        if args.command == 'build':
            result = builder.build_repository(args.decisions, args.source_root)
            print('Build completed')
            print(f'decisions: {result.decisions}')
            print(f'targets: {result.targets}')
            print(f'overrides: {result.overrides}')
            print(f'unchanged: {result.unchanged}')
            if result.mod_path is None:
                print('No overrides required; Mod payload was not published')
            else:
                print(f'mod: {result.mod_path.as_posix()}')
            print(f'glossary: {result.glossary_path.as_posix()}')
            return 0
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
        if args.command == 'restoration':
            if args.limit > 200:
                raise ValueError('--limit must be <= 200')
            output = restoration.build_restoration(datasets)
            if args.classification:
                output['rows'] = [r for r in output['rows'] if r['classification'] == args.classification]
                output['total'] = len(output['rows'])
                output['counts'] = {c: sum(r['classification'] == c for r in output['rows']) for c in restoration.CLASSES}
                output['filter'] = args.classification
            output.update(common)
            if args.output_dir:
                targets = [args.output_dir / 'candidates.tsv', args.output_dir / 'summary.md']
                if any(p.exists() for p in targets):
                    raise ValueError('Report already exists; choose a new output directory')
                write_report(targets[0], restoration.render_tsv(output).rstrip('\n'), args.source_root)
                write_report(targets[1], restoration.render_markdown(output), args.source_root)
                output = {k:v for k,v in output.items() if k != 'rows'}
                output['reports'] = [p.as_posix() for p in targets]
            else:
                output['rows'] = output['rows'][:args.limit]
        elif args.command == 'names':
            if args.offset < 0 or (args.limit > 200 and not args.output):
                raise ValueError('Use nonnegative --offset; stdout is limited to 200 names')
            if args.all and not args.output:
                raise ValueError('--all requires --output inside reports/')
            if args.stats and args.format == 'tsv':
                raise ValueError('--stats requires JSON format')
            audit = build_inventory(datasets)
            filtered = filter_rows(audit['rows'], category=args.category, family=args.family, flag=args.flag,
                                   pack=args.pack, series=args.series, review=args.review,
                                   suspicious=args.suspicious, string_id=args.string_id, primary=args.primary)
            page = [] if args.stats else filtered[args.offset:] if args.all else filtered[args.offset:args.offset + args.limit]
            output = {**common, 'name_inventory_version': audit['schema_version'],
                      'rules_sha256': audit['rules_sha256'], 'statistics': audit['statistics'],
                      'selected_statistics': inventory_stats(filtered),
                      'coverage': audit['coverage'], 'inventory': inventory, 'total': len(filtered),
                      'offset': args.offset, 'rows': page,
                      'filters': {k: getattr(args, k) for k in ('category', 'family', 'flag', 'pack', 'series', 'review', 'suspicious', 'string_id', 'primary')}}
        elif args.command == 'stats':
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
        content = (render_tsv(output['rows']) if args.command == 'names' and args.format == 'tsv'
                   else json.dumps(output, ensure_ascii=False, indent=2) + '\n')
        if args.command == 'report' or (args.command == 'names' and args.output):
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
