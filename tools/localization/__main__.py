"""Run with python -m tools.localization; all text output is UTF-8 JSON."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from .analysis import (CATEGORIES, all_ids, classify, legacy_summary, load_datasets, row, summary)
from .gameplay import (FAMILIES, FLAGS, NAME_CATEGORIES, build_inventory, filter_rows, inventory_stats, render_tsv)
from . import restoration
from . import adoption
from . import scope
from . import patch_plan
from . import blocked_audit
from . import layout_plan
from . import mod_build
from . import mod_package
from .human_reviews import load_ledger, DEFAULT_LEDGER
from . import context_overrides
from . import term_audit
from . import source_apply
from . import validator


def positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('Must be positive')
    return number


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='AoK/AoC/HD/DE localization analysis and authenticated source apply')
    parser.add_argument('--source-root', type=Path, default=Path('source'))
    parser.add_argument('--config', type=Path, help='JSON object mapping dataset names to directories under source-root')
    commands = parser.add_subparsers(dest='command', required=True)
    validate = commands.add_parser('validate', help='Validate approved decisions and resolve final values')
    validate.add_argument('--decisions', type=Path, default=validator.DEFAULT_DECISIONS)
    commands.add_parser('stats', help='Counts, categories, and source SHA-256 inventory')
    commands.add_parser('legacy-stats', help='Legacy DLL counts, ranges, overlaps, and generation ID intersections')
    terms = commands.add_parser('term-audit', help='Phase 2A-1 structural concept review; no decisions or patches')
    terms.add_argument('--output-dir', type=Path, required=True, help='New reports/phase2a/<run>/ directory')
    restore = commands.add_parser('restoration', help='Legacy policy review proposals; never translation overrides')
    restore.add_argument('--classification', choices=restoration.CLASSES)
    restore.add_argument('--limit', type=positive, default=25)
    restore.add_argument('--output-dir', type=Path)
    adopt = commands.add_parser('adoption', help='Unapproved Phase 1B editorial review sheet')
    adopt.add_argument('--output-dir', type=Path, required=True)
    scope_audit = commands.add_parser('scope-audit', help='Read-only Phase 1C application scope report')
    scope_audit.add_argument('--output-dir', type=Path, default=Path('reports/phase1c'))
    scope_audit.add_argument('--ledger', type=Path, default=DEFAULT_LEDGER)
    scope_audit.add_argument('--context-overrides', type=Path, default=context_overrides.DEFAULT_PATH)
    scope_audit.add_argument('--names-only', action='store_true', help='Legacy name-only audit; omit direct overrides')
    scope_review = commands.add_parser('scope-review', help='Inspect bounded scope candidates')
    scope_review.add_argument('--class', dest='scope_class', choices=scope.CLASSES, default='review')
    scope_review.add_argument('--limit', type=positive, default=10)
    scope_review.add_argument('--names-only', action='store_true')
    patch = commands.add_parser('patch-plan', help='Occurrence-bound dry-run only; no apply command')
    patch.add_argument('--scope-dir', type=Path, default=Path('reports/phase1c-normalized'))
    patch.add_argument('--ledger', type=Path, default=DEFAULT_LEDGER)
    patch.add_argument('--output-dir', type=Path, default=Path('reports/phase1d'))
    blocked = commands.add_parser('blocked-audit', help='Dry-run layout proposals for blocked Phase 1D occurrences')
    blocked.add_argument('--scope-dir', type=Path, default=Path('reports/phase1c-normalized'))
    blocked.add_argument('--ledger', type=Path, default=DEFAULT_LEDGER)
    blocked.add_argument('--plan-dir', type=Path, default=Path('reports/phase1d'))
    blocked.add_argument('--output-dir', type=Path, default=Path('reports/phase1d-blocked-audit'))
    blocked_review = commands.add_parser('blocked-review', help='Read saved manual-review JSON as a human-readable table')
    blocked_review.add_argument('--input', type=Path, default=Path('reports/phase1d-blocked-audit/manual-review.json'))
    layout = commands.add_parser('layout-plan', help='Integrate automatic and human layout decisions; dry-run only')
    layout.add_argument('--scope-dir', type=Path, default=Path('reports/phase1c-normalized'))
    layout.add_argument('--ledger', type=Path, default=DEFAULT_LEDGER)
    layout.add_argument('--layout-ledger', type=Path, default=Path('reviews/phase1d-layout-decisions.json'))
    layout.add_argument('--output-dir', type=Path, default=Path('reports/phase1d-layout'))
    apply = commands.add_parser('apply', help='Apply the authenticated baseline and Phase 2A source plan')
    apply.add_argument('--authorization', type=Path, default=source_apply.DEFAULT_AUTHORIZATION)
    apply.add_argument('--ledger', type=Path, default=DEFAULT_LEDGER)
    apply.add_argument('--layout-ledger', type=Path, default=source_apply.DEFAULT_LAYOUT_LEDGER)
    apply.add_argument('--dry-run', action='store_true')
    build = commands.add_parser('mod-build', help='Generate a verified independent Mod payload; never install')
    build.add_argument('--plan', type=Path, default=Path('reports/phase1d-layout/patch-plan.json'))
    build.add_argument('--scope-dir', type=Path, default=Path('reports/phase1c-normalized'))
    build.add_argument('--ledger', type=Path, default=DEFAULT_LEDGER)
    build.add_argument('--layout-ledger', type=Path, default=Path('reviews/phase1d-layout-decisions.json'))
    build.add_argument('--output-dir', type=Path, default=Path('dist/phase1e-mod'))
    modes=build.add_mutually_exclusive_group()
    modes.add_argument('--dry-run', action='store_true')
    modes.add_argument('--verify-only', action='store_true')
    package = commands.add_parser('mod-package', help='Create a local display-test package; no install or launch')
    package.add_argument('--input-dir', type=Path, default=Path('dist/phase1e-mod'))
    package.add_argument('--plan', type=Path, default=Path('reports/phase1d-layout/patch-plan.json'))
    package.add_argument('--scope-dir', type=Path, default=Path('reports/phase1c-normalized'))
    package.add_argument('--ledger', type=Path, default=DEFAULT_LEDGER)
    package.add_argument('--layout-ledger', type=Path, default=Path('reviews/phase1d-layout-decisions.json'))
    package.add_argument('--output-dir', type=Path, default=Path('dist/phase1f-local-mod-delta'))
    package.add_argument('--verify-only', action='store_true')
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
    plan_blocked = False
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
        if args.command == 'apply':
            if args.config:
                raise ValueError('Source apply uses the audited default dataset layout; --config is unsupported')
            bundle = source_apply.prepare(args.source_root, authorization_path=args.authorization,
                                          ledger_path=args.ledger, layout_path=args.layout_ledger)
            result = source_apply.execute(bundle, dry_run=args.dry_run)
            print(json.dumps({'mode':'dry-run' if args.dry_run else 'apply', **result},
                             ensure_ascii=True, indent=2))
            return 0
        if args.command == 'mod-package':
            if args.config:raise ValueError('Local package requires the audited default dataset layout')
            bundle=mod_package.prepare(args.source_root,args.plan,args.ledger,args.layout_ledger,args.scope_dir,args.input_dir)
            mode='verify-only' if args.verify_only else 'build'
            manifest=mod_build.generate(bundle,args.output_dir,mode)
            print(json.dumps({'mode':mode,'output_dir':args.output_dir.as_posix(),'manifest':manifest},ensure_ascii=True,indent=2))
            return 0
        if args.command == 'mod-build':
            if args.config:raise ValueError('Mod build uses the audited default dataset layout; --config is unsupported')
            bundle=mod_build.prepare(args.source_root,args.plan,args.ledger,args.layout_ledger,args.scope_dir)
            mode='dry-run' if args.dry_run else 'verify-only' if args.verify_only else 'build'
            manifest=mod_build.generate(bundle,args.output_dir,mode)
            print(json.dumps({'mode':mode,'output_dir':args.output_dir.as_posix(),'manifest':manifest},ensure_ascii=True,indent=2))
            return 0
        if args.command == 'blocked-review':
            print(blocked_audit.render_manual_review(blocked_audit.load_json(args.input)),end='')
            return 0
        config = json.loads(args.config.read_text(encoding='utf-8-sig')) if args.config else None
        if args.command == 'term-audit':
            protected_roots = [args.source_root, Path('source'), Path('reviews'), Path('translations'), Path('dist')]
            if isinstance(config, dict):
                for spec in config.values():
                    source_path = spec if isinstance(spec, str) else spec.get('path') if isinstance(spec, dict) else None
                    if isinstance(source_path, str):
                        protected_roots.append(args.source_root / source_path)
            if any(args.output_dir.resolve().is_relative_to(p.resolve()) for p in protected_roots):
                raise ValueError('Output overlaps a protected input directory')
            protected_before = mod_build.snapshot(protected_roots)
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
        if args.command == 'term-audit':
            audit = term_audit.build_audit(datasets)
            audit['review_references'] = []
            for p in sorted(Path('reviews').glob('*.json')):
                ledger = json.loads(p.read_text(encoding='utf8'))
                for r in ledger.get('records', []):
                    proposed = r.get('proposed_jp', r.get('replacement'))
                    notes = r.get('notes')
                    en = datasets['de_en'].resolved(r['string_id'])
                    bound = (en is not None and r.get('expected_de_english') == en.value
                             and r.get('signature') is not None and r.get('help_ids') is not None
                             and adoption.signature(datasets, r['string_id'], r['help_ids']) == r['signature'])
                    audit['review_references'].append(dict(ledger=p.as_posix(), string_id=r['string_id'],
                        signature=r.get('signature'), binding_signature=r.get('binding_signature'),
                        adopted_value_sha256=restoration.digest(proposed or ''),
                        decision=r.get('decision'), proposed_jp=proposed,
                        authority=r.get('authority', ledger.get('authority')),
                        notes_summary=notes[:160] if isinstance(notes, str) else None,
                        notes_reference=dict(ledger=p.as_posix(), string_id=r['string_id']),
                        evidence_status='matches' if bound else 'unverified_or_stale',
                        reference_only=True))
            audit['provenance'] = {
                'project_baseline_commit': 'bbd939d',
                'implementation_sha256': {p.name: mod_build.sha(p.read_bytes())
                                        for p in sorted(Path(__file__).parent.glob('*.py'))},
                'review_file_sha256': {p.as_posix(): mod_build.sha(p.read_bytes())
                                      for p in sorted(Path('reviews').glob('*')) if p.is_file()},
                'review_reference_policy': 'Read-only fingerprints; no adjudication applied or revalidated by this audit'}
            mod_build.unchanged(protected_roots, protected_before)
            paths = term_audit.write_artifacts(audit, args.output_dir, args.source_root)
            mod_build.unchanged(protected_roots, protected_before)
            output = {**common, **audit['statistics'], 'reports': paths}
        elif args.command == 'layout-plan':
            rows,metadata,hashes=patch_plan.read_audit(args.scope_dir)
            plan=layout_plan.integrate(datasets,load_ledger(args.ledger),rows,metadata,hashes,blocked_audit.load_json(args.layout_ledger))
            artifacts={'patch-plan.json':{k:v for k,v in plan.items() if k!='blocked'},'blocked.json':plan['blocked']}
            reports={name:blocked_audit.serialize_json(obj) for name,obj in artifacts.items()}
            reports.update({'patch-plan.tsv':layout_plan.render_table(plan),'patch-summary.md':patch_plan.render_summary(plan)})
            if any((args.output_dir/name).exists() for name in reports):
                raise ValueError('Layout plan already exists; choose a new output directory')
            for name,content in reports.items():
                write_report(args.output_dir/name,content.rstrip('\n'),args.source_root)
                if name in artifacts: blocked_audit.verify_json(args.output_dir/name,artifacts[name])
            plan_blocked=bool(plan['blocked'])
            output={**common,**plan['statistics'],'reports':[(args.output_dir/name).as_posix() for name in reports]}
        elif args.command == 'blocked-audit':
            rows,metadata,hashes=patch_plan.read_audit(args.scope_dir)
            result=blocked_audit.audit_blocked(datasets,load_ledger(args.ledger),rows,metadata,hashes,
                json.loads((args.plan_dir/'patch-plan.json').read_text(encoding='utf8')),
                json.loads((args.plan_dir/'blocked.json').read_text(encoding='utf8')))
            reports={'blocked-audit.tsv':blocked_audit.render_table(result),
                     'blocked-summary.md':blocked_audit.render_summary(result)}
            artifacts=blocked_audit.json_artifacts(result)
            reports.update({name:blocked_audit.serialize_json(value) for name,value in artifacts.items()})
            if any((args.output_dir/name).exists() for name in reports):
                raise ValueError('Blocked audit already exists; choose a new output directory')
            for name,content in reports.items():
                write_report(args.output_dir/name,content.rstrip('\n'),args.source_root)
                if name in artifacts:
                    blocked_audit.verify_json(args.output_dir/name,artifacts[name])
            plan_blocked=bool(result['manual_review'])
            output={**common,**result['statistics'],'reports':[(args.output_dir/name).as_posix() for name in reports]}
        elif args.command == 'patch-plan':
            rows,metadata,hashes=patch_plan.read_audit(args.scope_dir)
            plan=patch_plan.build_plan(datasets,load_ledger(args.ledger),rows,metadata,hashes)
            plan_blocked=bool(plan['blocked'])
            reports={'patch-plan.json':json.dumps({k:v for k,v in plan.items() if k!='blocked'},ensure_ascii=False,indent=2),
                     'patch-plan.tsv':patch_plan.render_tsv(plan),'patch-summary.md':patch_plan.render_summary(plan),
                     'blocked.json':json.dumps(plan['blocked'],ensure_ascii=False,indent=2)}
            if any((args.output_dir/name).exists() for name in reports):
                raise ValueError('Patch plan already exists; choose a new output directory')
            for name,content in reports.items():
                write_report(args.output_dir/name,content.rstrip('\n'),args.source_root)
            output={**common,**plan['statistics'],'reports':[(args.output_dir/name).as_posix() for name in reports]}
        elif args.command in ('scope-audit','scope-review'):
            if args.command=='scope-review' and args.limit>200:
                raise ValueError('--limit must be <= 200')
            if args.command=='scope-audit':
                context_path=None if args.names_only else args.context_overrides
                audit=scope.build_scope(datasets,load_ledger(args.ledger),context_path=context_path)
            else:
                audit=scope.build_scope(datasets,load_ledger() if args.names_only else None)
            if args.command=='scope-audit':
                metadata={k:v for k,v in audit.items() if k!='rows'}
                reports={'scope-audit.tsv':scope.render_audit(audit), 'scope-summary.md':scope.render_summary(audit),
                         'scope-metadata.json':json.dumps(metadata,ensure_ascii=False,indent=2)}
                reports['duplicate-audit.json']=json.dumps(audit['duplicate_audit'],ensure_ascii=False,indent=2)
                if any((args.output_dir/name).exists() for name in reports):
                    raise ValueError('Scope report already exists; choose a new output directory')
                for name,content in reports.items():
                    write_report(args.output_dir/name,content.rstrip('\n'),args.source_root)
                output={**common,'decision_count':audit['decision_count'],'related_id_count':audit['related_id_count'],
                        'scope_counts':audit['scope_counts'],'total':audit['total'],'conflict_count':audit['conflict_count'],
                        'reports':[(args.output_dir/name).as_posix() for name in reports]}
            else:
                selected=[r for r in audit['rows'] if r['scope_class']==args.scope_class]
                output={**common,'total':len(selected),'rows':selected[:args.limit],'scope_class':args.scope_class}
        elif args.command == 'adoption':
            review = adoption.build_adoption(datasets)
            reports = {'review.tsv': adoption.render_review(review),
                       'evidence.tsv': adoption.render_evidence(review),
                       'review-summary.md': adoption.render_summary(review),
                       'definite-bugs.json': json.dumps(review['bugs'],ensure_ascii=False,indent=2)}
            reports['human-review-audit.json'] = json.dumps(review['human_review'],ensure_ascii=False,indent=2)
            if any((args.output_dir / name).exists() for name in reports):
                raise ValueError('Review already exists; choose a new output directory')
            for name, content in reports.items():
                write_report(args.output_dir / name, content.rstrip('\n'), args.source_root)
            output = {**common, 'total':review['total'], 'counts':review['counts'],
                      'upstream_counts':review['upstream_counts'], 'consistency_rows':review['consistency_rows'],
                      'human_counts':review['human_counts'], 'baseline_human_counts':review['baseline_human_counts'],
                      'reports':[(args.output_dir/name).as_posix() for name in reports]}
        elif args.command == 'restoration':
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
        return 1 if issue_count or plan_blocked else 0
    except (OSError, ValueError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    raise SystemExit(main())
