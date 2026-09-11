"""Apply only the authenticated formal source plan; no translation inference."""
import json
import os
from pathlib import Path
import stat
import tempfile

from .analysis import Dataset, load_datasets
from .blocked_audit import load_json
from . import context_overrides, layout_plan, phase2a_patch_plan, scope
from .human_reviews import DEFAULT_LEDGER, implementation_ledger, load_ledger
from .mod_build import patch_bytes, safe_source, sha, snapshot, unchanged
from .parser import parse_text
from .patch_plan import tokens
from .source_states import CERTIFICATE_SHA256, _certificate, evidence_data


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUTHORIZATION = ROOT / 'reviews/phase2a-source-patch-authorization.json'
DEFAULT_LAYOUT_LEDGER = ROOT / 'reviews/phase1d-layout-decisions.json'


def load_authorization(path=DEFAULT_AUTHORIZATION):
    authorization = json.loads(Path(path).read_text(encoding='utf8'))
    expected = {
        'baseline_operations': 387, 'phase2a_operations': 141,
        'merged_operations': 528, 'unique_ids': 528,
        'full_value': 287, 'span': 241,
        'phase2a_concepts': 64, 'phase2a_target_bindings': 249,
    }
    if (authorization.get('schema_version') != 1
            or authorization.get('authorization_id') != 'phase2a-source-patch-2026-09-11'
            or authorization.get('authority') !=
            'explicit project-owner approval to apply the existing Phase 2A operation plan'
            or authorization.get('status') != 'approved'
            or authorization.get('scope') != 'source_patch_only'
            or authorization.get('source_state_certificate_sha256') != CERTIFICATE_SHA256
            or authorization.get('expected') != expected):
        raise ValueError('Invalid or stale Phase 2A source-patch authorization')
    return authorization


def formal_plans(data, formal_ledger, layout_ledger):
    """Regenerate the existing baseline and Phase 2A plans from one source view."""
    baseline_ledger = implementation_ledger(formal_ledger)
    audit = scope.build_scope(data, baseline_ledger,
                              context_path=context_overrides.DEFAULT_PATH)
    metadata = {key: value for key, value in audit.items() if key != 'rows'}
    baseline = layout_plan.integrate(data, baseline_ledger, audit['rows'],
                                     metadata, {}, layout_ledger)
    phase2a = phase2a_patch_plan.build_plan(data, formal_ledger, layout_ledger)
    return audit, baseline, phase2a


def _validate_plans(audit, baseline, phase2a, states, authorization):
    if audit['stale_decisions'] or audit['conflict_count']:
        raise ValueError('Stale or conflicting scope; source apply refused')
    if baseline['blocked'] or phase2a['blocked']:
        raise ValueError('Blocked operation; source apply refused')
    if (baseline['statistics']['conflicts']
            or baseline['statistics']['duplicate_id_patch_operations']):
        raise ValueError('Conflicting or duplicate operation; source apply refused')
    operations = baseline['operations'] + phase2a['operations']
    ids = [operation['string_id'] for operation in operations]
    locations = [(operation['source_path'], operation['source_line']) for operation in operations]
    operation_ids = [operation['operation_id'] for operation in operations]
    if len(ids) != len(set(ids)) or len(locations) != len(set(locations)) \
            or len(operation_ids) != len(set(operation_ids)):
        raise ValueError('Duplicate merged operation; source apply refused')
    _, records = _certificate()
    authorized_ids = set(records)
    if set(ids) & set(states) or set(ids) | set(states) != authorized_ids:
        raise ValueError('Merged plan does not cover exactly the authorized source states')
    expected = authorization['expected']
    if len(operations) + len(states) != expected['merged_operations']:
        raise ValueError('Authorized operation count mismatch')
    return operations


def _updated_data(data, outputs):
    updated = Dataset('de_jp')
    for source in data['de_jp'].files:
        raw = outputs.get(source.path, source.raw_bytes)
        parsed = parse_text(raw.decode('utf-8-sig', errors='strict'), source.path)
        parsed.raw_bytes = raw
        parsed.sha256 = sha(raw)
        parsed.size_bytes = len(raw)
        parsed.bom = raw.startswith(b'\xef\xbb\xbf')
        parsed.format = source.format
        parsed.metadata = source.metadata
        updated.add(parsed)
    return {**data, 'de_jp': updated}


def prepare(source_root, *, authorization_path=DEFAULT_AUTHORIZATION,
            ledger_path=DEFAULT_LEDGER, layout_path=DEFAULT_LAYOUT_LEDGER):
    """Validate all operations and construct the complete after-state in memory."""
    source_root = Path(source_root)
    authorization = load_authorization(authorization_path)
    formal_ledger = load_ledger(ledger_path)
    layout_ledger = load_json(layout_path)
    data = load_datasets(source_root)
    protected_roots = [source_root, ROOT / 'reviews']
    protected = snapshot(protected_roots)
    _, states = evidence_data(data)
    audit, baseline, phase2a = formal_plans(data, formal_ledger, layout_ledger)
    operations = _validate_plans(audit, baseline, phase2a, states, authorization)

    groups = {}
    for operation in operations:
        groups.setdefault(operation['source_path'], []).append(operation)
    outputs = {}
    originals = {}
    paths = {}
    for source in data['de_jp'].files:
        path = safe_source(source_root, source.path)
        raw = path.read_bytes()
        if sha(raw) != source.sha256:
            raise ValueError('Source changed after validation')
        file_operations = groups.pop(source.path, [])
        if not file_operations:
            continue
        # The authenticated operation retains the pristine whole-file hash in
        # mixed state. Only this execution-local hash is adapted after the
        # certificate and formal planners have accepted every operation.
        executable = [dict(operation, expected_source_sha256=sha(raw))
                      for operation in file_operations]
        token_changes = {operation['operation_id'] for operation in file_operations
                         if operation.get('layout_provenance', {}).get('kind') == 'human_layout'
                         and tokens(operation['before']) != tokens(operation['after'])}
        output = patch_bytes(raw, source.path, executable,
                             authorized_token_changes=token_changes)
        if output != raw:
            outputs[source.path] = output
            originals[source.path] = raw
            paths[source.path] = path
    if groups:
        raise ValueError('Operation references an unknown DE JP source file')

    after = _updated_data(data, outputs)
    after_audit, after_baseline, after_phase2a = formal_plans(
        after, formal_ledger, layout_ledger)
    remaining = _validate_plans(after_audit, after_baseline, after_phase2a,
                                {**states, **{op['string_id']: 'ALREADY_APPLIED'
                                               for op in operations}}, authorization)
    if remaining:
        raise ValueError('Post-application formal plan is not empty')

    return {
        'source_root': source_root,
        'operations': operations,
        'already_applied': len(states),
        'outputs': outputs,
        'originals': originals,
        'paths': paths,
        'protected_roots': protected_roots,
        'protected': protected,
        'summary': {
            'planned': len(operations),
            'applied': 0,
            'already_applied': len(states),
            'stale': 0,
            'changed_files': 0,
            'would_apply': len(operations),
            'would_change_files': len(outputs),
        },
    }


def execute(bundle, *, dry_run=False):
    """Publish verified bytes with same-directory atomic replacement."""
    summary = dict(bundle['summary'])
    if dry_run or not bundle['outputs']:
        return summary
    # The approved 528-operation plan changes one physical file, so its publish
    # is an all-or-nothing atomic replacement. Refuse scope expansion here.
    if len(bundle['outputs']) != 1:
        raise ValueError('Authorized source patch must change exactly one file')
    unchanged(bundle['protected_roots'], bundle['protected'])
    for label, path in bundle['paths'].items():
        if path.read_bytes() != bundle['originals'][label]:
            raise ValueError('Source changed before publication')
    label, output = next(iter(bundle['outputs'].items()))
    target = bundle['paths'][label]
    temporary = None
    try:
        descriptor, name = tempfile.mkstemp(prefix='.localization-apply-', dir=target.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(output)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, stat.S_IMODE(target.stat().st_mode))
        if target.read_bytes() != bundle['originals'][label]:
            raise ValueError('Source changed before atomic replacement')
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    if target.read_bytes() != output:
        raise ValueError('Atomic source replacement verification failed')
    summary.update(applied=len(bundle['operations']), changed_files=1)
    return summary
