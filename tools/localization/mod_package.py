"""AoE2 DE local test package. No install, launch or publishing API."""
from collections import defaultdict
from pathlib import Path

from . import mod_build
from .blocked_audit import serialize_json
from .parser import parse_text
from .analysis import id_sort

MOD_NAME='AoE2-Japanese-Localization-Phase1F'
INPUT_TRANSLATION='resources/jp/strings/key-value/key-value-strings-utf8.txt'
OUTPUT_TRANSLATION=MOD_NAME+'/resources/jp/strings/key-value/key-value-modded-strings-utf8.txt'
DOCS={'INSTALL.md':Path('docs/phase1f-local-mod.md'),'CHECKLIST.md':Path('docs/phase1f-checklist.md')}


def delta_values(verified):
    """Select only verified operation IDs; resolve against the Phase 1E payload."""
    operations=verified['operations']
    if len(operations)!=verified['manifest']['applied_operation_count']:
        raise ValueError('Verified operation count mismatch')
    ids=[op['string_id'] for op in operations]
    if len(set(ids))!=len(ids):raise ValueError('Duplicate target ID cannot be represented by a unique override')
    by_id=defaultdict(list)
    for path,raw in verified['files'].items():
        parsed=parse_text(raw.decode('utf-8-sig'),path)
        if parsed.issues:raise ValueError('Invalid Phase 1E translation input')
        for entry in parsed.entries:by_id[entry.string_id].append(entry)
    expected={};proofs=[]
    for op in sorted(operations,key=lambda o:id_sort(o['string_id'])):
        sid=op['string_id'];entries=by_id.get(sid,[])
        if len(entries)!=1:raise ValueError('Missing or duplicate Phase 1E target ID: '+sid)
        entry=entries[0]
        if not op['source_path'].startswith('de_jp/'):
            raise ValueError('Unexpected operation dataset')
        path='resources/jp/strings/key-value/'+op['source_path'].removeprefix('de_jp/')
        if entry.path!=path or entry.line!=op['source_line'] or entry.value!=op['after']:
            raise ValueError('Phase 1E occurrence/result mismatch: '+sid)
        expected[sid]=entry.value
        proofs.append(dict(string_id=sid,operation_id=op['operation_id'],phase1e_file=path,phase1e_line=entry.line,
            phase1e_file_sha256=verified['manifest']['output_file_hashes'][path],
            value_sha256=mod_build.sha(entry.value.encode('utf8')),package_line=len(proofs)+1))
    return expected,proofs


def verify_delta(raw,expected):
    parsed=parse_text(raw.decode('utf-8-sig'))
    if parsed.issues:raise ValueError('Invalid generated override syntax')
    by_id=defaultdict(list)
    for entry in parsed.entries:by_id[entry.string_id].append(entry.value)
    missing=set(expected)-set(by_id);extra=set(by_id)-set(expected)
    duplicates={sid for sid,values in by_id.items() if len(values)!=1}
    mismatched={sid for sid in set(expected)&set(by_id) if any(v!=expected[sid] for v in by_id[sid])}
    result=dict(expected_id_count=len(expected),output_id_count=len(by_id),output_entry_count=len(parsed.entries),
        missing_id_count=len(missing),extra_id_count=len(extra),duplicate_id_count=len(duplicates),
        value_mismatch_count=len(mismatched),matching_value_count=len(set(expected)&set(by_id)-mismatched-duplicates),
        id_set_equal=not missing and not extra)
    if missing or extra or duplicates or mismatched:raise ValueError('Delta verification failed: '+str(result))
    return result


def assemble(verified,phase1e_dir,documents):
    """Extract verified final values only; keep the Phase 1E full payload read-only."""
    before=mod_build.snapshot([phase1e_dir])
    mod_build.verify_directory(verified,phase1e_dir)
    if INPUT_TRANSLATION not in verified['files']:
        raise ValueError('Missing expected Phase 1E translation file')
    translation=(phase1e_dir/INPUT_TRANSLATION).read_bytes()
    expected_hash=verified['manifest']['output_file_hashes'][INPUT_TRANSLATION]
    if mod_build.sha(translation)!=expected_hash:raise ValueError('Phase 1E translation hash mismatch')
    if verified['manifest']['changed_output_files']!=1:
        raise ValueError('Package schema supports the single audited changed source file only')
    original_hash=verified['manifest']['source_hashes'].get('de_jp/key-value-strings-utf8.txt')
    if not original_hash or original_hash==expected_hash:
        raise ValueError('Selected Phase 1E file is not the verified changed translation')
    expected,proofs=delta_values(verified)
    # Values are parser-preserved key-value syntax (literal escapes), not decoded
    # strings. Do not JSON-escape or normalize them a second time.
    delta=''.join(f'{sid} "{expected[sid]}"\n' for sid in sorted(expected,key=id_sort)).encode('utf8')
    delta_verification=verify_delta(delta,expected)
    info=dict(Author='AoE2 Japanese Localization Project',CacheStatus=0,Title='AoE2 Japanese Localization - Phase 1F Test',
              Description='Local Japanese display test. Changed IDs only; final values verified against Phase 1E.')
    files={OUTPUT_TRANSLATION:delta,MOD_NAME+'/info.json':(serialize_json(info)+'\n').encode('utf8')}
    if set(documents)!={'INSTALL.md','CHECKLIST.md'}:raise ValueError('Missing package instructions/checklist')
    files.update(documents)
    manifest=dict(schema_version=2,generator='localization-local-mod-package/2',
        packaging_policy='changed_string_ids_only',mod_folder=MOD_NAME,
        runtime_verified=False,phase1e_manifest_sha256=mod_build.sha((phase1e_dir/'manifest.json').read_bytes()),
        phase1e_patch_plan_sha256=verified['manifest']['patch_plan_sha256'],
        verified_phase1e_operations=verified['manifest']['applied_operation_count'],
        translation_mapping=[dict(input_file=INPUT_TRANSLATION,package_file=OUTPUT_TRANSLATION,
                                  input_sha256=expected_hash,package_sha256=mod_build.sha(delta))],
        translation_file_count=1,unchanged_phase1e_files_omitted=len(verified['files'])-1,
        translation_entry_count=len(expected),delta_sha256=mod_build.sha(delta),value_provenance=proofs,
        verification=dict(phase1e_verified=True,**delta_verification,game_launched=False,installed=False),
        output_file_hashes={path:mod_build.sha(value) for path,value in sorted(files.items())})
    mod_build.unchanged([phase1e_dir],before)
    roots=verified['protected_roots']+[phase1e_dir]
    protected={**verified['protected'],**before}
    mod_build.unchanged(roots,protected)
    return dict(files=files,manifest=manifest,protected_roots=roots,protected=protected,
                input_hashes=dict(verified['input_hashes']))


def prepare(source_root,plan,ledger,layout_ledger,scope_dir,phase1e_dir):
    verified=mod_build.prepare(source_root,plan,ledger,layout_ledger,scope_dir)
    documents={name:path.read_bytes() for name,path in DOCS.items()}
    bundle=assemble(verified,phase1e_dir,documents)
    bundle['input_hashes'].update({str(path):mod_build.sha(documents[name]) for name,path in DOCS.items()})
    validation=Path(__file__).resolve().parents[2]/'reviews/game-validation.json'
    if validation.exists():attach_game_validation(bundle,validation)
    return bundle


def attach_game_validation(bundle,path):
    """Bind a user's display-test report to exact translation bytes, never launch."""
    from .blocked_audit import load_json
    record=load_json(path)
    if (record.get('schema_version')!=1 or record.get('authority')!='explicit_user_runtime_report'
            or record.get('result')!='pass' or not record.get('confirmed_names')):
        raise ValueError('Invalid human runtime validation record')
    confirmed_ui=record.get('confirmed_ui',[])
    if not isinstance(confirmed_ui,list):raise ValueError('Invalid confirmed UI records')
    ui_ids=[]
    for item in confirmed_ui:
        if (not isinstance(item,dict) or not isinstance(item.get('string_id'),str) or not item['string_id']
                or not isinstance(item.get('adopted_jp'),str) or not item['adopted_jp']
                or item.get('result')!='pass' or item.get('ownership_verified') is not True):
            raise ValueError('Invalid confirmed UI record')
        ui_ids.append(item['string_id'])
    if len(ui_ids)!=len(set(ui_ids)):raise ValueError('Duplicate confirmed UI String ID')
    matched=record.get('translation_sha256')==bundle['manifest']['delta_sha256']
    if matched:
        provenance={p['string_id']:p for p in bundle['manifest'].get('value_provenance',[])}
        for item in confirmed_ui:
            proof=provenance.get(item['string_id'])
            if proof is None or proof.get('value_sha256')!=mod_build.sha(item['adopted_jp'].encode('utf8')):
                raise ValueError('Confirmed UI value does not match current translation: '+item['string_id'])
    record_hash=mod_build.sha(path.read_bytes())
    bundle['manifest'].update(runtime_verified=matched,runtime_validation=dict(
        status='matching_user_report' if matched else 'report_for_different_translation',
        record_sha256=record_hash,record_id=record['record_id'],
        authority=record['authority'],coverage='user_reported_displays',
        confirmed_names=record['confirmed_names'] if matched else [],
        confirmed_ui=confirmed_ui if matched else [],
        installed_bytes_independently_verified=False))
    bundle['input_hashes'][str(path)]=record_hash
