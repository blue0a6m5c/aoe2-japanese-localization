"""Verified, independent Mod payload generation. No installation API."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import time

from .analysis import load_datasets
from .blocked_audit import load_json,serialize_json
from .human_reviews import load_ledger
from .layout_plan import integrate
from .parser import HEADER,parse_text
from .patch_plan import read_audit,tokens

SCHEMA=1
GENERATOR='localization-mod-build/1'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def snapshot(roots):
    return {str(p.resolve()):sha(p.read_bytes()) for root in roots
            for p in sorted(Path(root).rglob('*')) if p.is_file()}


def unchanged(roots,expected):
    if snapshot(roots)!=expected: raise ValueError('Protected source/review files changed during generation')


def patch_bytes(raw,label,operations):
    """Change quoted value substrings only, preserving all other source bytes."""
    text=raw.decode('utf-8-sig',errors='strict')
    parsed=parse_text(text,label)
    parts=re.split(r'(\r\n|\n|\r)',text)
    original=list(parts)
    seen=set();ids=set();by_line={}
    for op in operations:
        line=op['source_line'];sid=op['string_id']
        if type(line)!=int or line<1 or line in seen: raise ValueError('Missing or duplicate source location')
        seen.add(line)
        if op['operation_id'] in ids: raise ValueError('Duplicate operation ID')
        ids.add(op['operation_id'])
        if op['source_path']!=label or op['expected_source_sha256']!=sha(raw):
            raise ValueError('Source path/hash mismatch')
        entries=[e for e in parsed.entries if e.line==line and e.string_id==sid]
        if len(entries)!=1 or entries[0].ambiguous or any(i.line==line for i in parsed.issues):
            raise ValueError('Missing, ambiguous or malformed source occurrence')
        before=entries[0].value
        if before!=op['before'] or sha(before.encode('utf8'))!=op['expected_value_sha256']:
            raise ValueError('Expected current value mismatch')
        a,b=op['matched_span']
        if type(a)!=int or type(b)!=int or not 0<=a<b<=len(before) or before[a:b]!=op['matched']:
            raise ValueError('Expected current span mismatch')
        replacement=op['replacement']
        if not isinstance(replacement,str):raise ValueError('Invalid replacement')
        after=before[:a]+replacement+before[b:]
        full=(a,b)==(0,len(before))
        if op['replacement_type']!=('full_value' if full else 'span'):
            raise ValueError('Replacement type mismatch')
        if after!=op['after'] or after==before:raise ValueError('Expected result mismatch or no-op')
        if tokens(before)!=tokens(after):raise ValueError('Technical token sequence changed')
        index=(line-1)*2
        header=HEADER.match(parts[index])
        if not header or header[1]!=sid:raise ValueError('Physical record mismatch')
        start=header.end();end=start+len(before)
        if parts[index][start:end]!=before or parts[index][end:end+1]!='"':
            raise ValueError('Quoted source value mismatch')
        parts[index]=parts[index][:start]+after+parts[index][end:]
        by_line[line]=op
    output=('\ufeff' if raw.startswith(b'\xef\xbb\xbf') else '')+''.join(parts)
    result=output.encode('utf8')
    # Verify physical byte preservation outside targeted value records, including
    # CR/LF delimiters, comments, duplicate-ID occurrences and whitespace.
    for i,(before,after) in enumerate(zip(original,parts)):
        if (i%2 or i//2+1 not in by_line) and before.encode('utf8')!=after.encode('utf8'):
            raise ValueError('Unplanned physical record modification')
    reparsed=parse_text(result.decode('utf-8-sig'),label)
    if parsed.issues!=reparsed.issues or len(parsed.entries)!=len(reparsed.entries):
        raise ValueError('Output parser structure/diagnostics changed')
    applied=0
    for old,new in zip(parsed.entries,reparsed.entries):
        if (old.string_id,old.line,old.ambiguous)!=(new.string_id,new.line,new.ambiguous):
            raise ValueError('Output occurrence structure changed')
        expected=by_line[old.line]['after'] if old.line in by_line else old.value
        if new.value!=expected:raise ValueError('Output value verification failed')
        applied+=old.line in by_line
    if applied!=len(operations):raise ValueError('Missing or excess application')
    return result


def safe_source(root,label):
    relative=PurePosixPath(label)
    if relative.parts[:1]!=('de_jp',) or '..' in relative.parts or '\\' in label:
        raise ValueError('Invalid DE JP source label')
    base=(root/'de/jp/key-value').resolve()
    path=base.joinpath(*relative.parts[1:]).resolve()
    if not path.is_relative_to(base) or path==base:raise ValueError('Source path escapes DE JP root')
    return path


def prepare(source_root,plan_path,ledger_path,layout_path,scope_dir):
    """Validate everything and construct bytes in memory before any output write."""
    protected_roots=[source_root,Path('reviews')]
    protected=snapshot(protected_roots)
    input_paths=[plan_path,ledger_path,layout_path,scope_dir/'scope-audit.tsv',scope_dir/'scope-metadata.json']
    input_hashes={str(p):sha(p.read_bytes()) for p in input_paths}
    plan=load_json(plan_path)
    if plan.get('mode')!='dry_run_only' or plan.get('schema_version')!=1:
        raise ValueError('Unsupported patch plan schema/mode')
    rows,metadata,hashes=read_audit(scope_dir)
    data=load_datasets(source_root)
    regenerated=integrate(data,load_ledger(ledger_path),rows,metadata,hashes,load_json(layout_path))
    if regenerated['blocked'] or plan!={k:v for k,v in regenerated.items() if k!='blocked'}:
        raise ValueError('Patch plan does not exactly match freshly verified source, decisions and scope')
    groups={};locations=set();operation_ids=set()
    for op in plan['operations']:
        location=(op['source_path'],op['source_line'])
        if location in locations or op['operation_id'] in operation_ids:
            raise ValueError('Duplicate operation/source location')
        locations.add(location);operation_ids.add(op['operation_id'])
        groups.setdefault(op['source_path'],[]).append(op)
    files={};sources={};changed=0
    for parsed in data['de_jp'].files:
        path=safe_source(source_root,parsed.path)
        raw=path.read_bytes()
        if sha(raw)!=parsed.sha256:raise ValueError('Source changed after parsing')
        ops=groups.pop(parsed.path,[])
        output=patch_bytes(raw,parsed.path,ops)
        relative='resources/jp/strings/key-value/'+parsed.path.removeprefix('de_jp/')
        if relative in files:raise ValueError('Duplicate output path')
        files[relative]=output;sources[parsed.path]=sha(raw)
        changed+=output!=raw
    if groups:raise ValueError('Operations reference unknown source file')
    expected_locations={(x['source_path'],x['source_line']):x for x in plan['locations']}
    if set(expected_locations)!=locations or len(plan['locations'])!=len(locations):
        raise ValueError('Patch location inventory mismatch')
    for op in plan['operations']:
        loc=expected_locations[(op['source_path'],op['source_line'])]
        if loc['after']!=op['after'] or loc['before']!=op['before'] or loc['operation_ids']!=[op['operation_id']]:
            raise ValueError('Location result mismatch')
    unchanged(protected_roots,protected)
    if any(sha(p.read_bytes())!=input_hashes[str(p)] for p in input_paths):raise ValueError('Inputs changed during validation')
    manifest=dict(schema_version=SCHEMA,generator=GENERATOR,patch_plan_sha256=input_hashes[str(plan_path)],
        input_hashes=input_hashes,source_hashes=sources,decision_ledger_sha256=plan['ledger_sha256'],
        layout_ledger_sha256=plan['layout_ledger_sha256'],applied_operation_count=len(plan['operations']),
        full_value_replacements=sum(o['replacement_type']=='full_value' for o in plan['operations']),
        span_replacements=sum(o['replacement_type']=='span' for o in plan['operations']),
        changed_string_ids=len({o['string_id'] for o in plan['operations']}),changed_output_files=changed,
        output_file_hashes={name:sha(value) for name,value in sorted(files.items())},
        verification=dict(missing_applications=0,extra_changes=0,conflicts=0,duplicate_applications=0,
                          unchanged_records_byte_identical=True,all_expected_results_match=True,technical_tokens_preserved=True))
    return dict(files=files,manifest=manifest,protected_roots=protected_roots,protected=protected,
                input_hashes=input_hashes,operations=plan['operations'])


def check_inputs(bundle):
    unchanged(bundle['protected_roots'],bundle['protected'])
    if any(sha(Path(p).read_bytes())!=v for p,v in bundle['input_hashes'].items()):
        raise ValueError('Validated input changed before publication')


def output_target(path):
    target=path.absolute();allowed=(Path.cwd()/'dist').resolve()
    if not target.resolve().is_relative_to(allowed) or target.resolve()==allowed or target.resolve()!=target:
        raise ValueError('Output must be a new directory inside dist/, without symlink redirection')
    return target


def verify_directory(bundle,target):
    expected=set(bundle['files'])|{'manifest.json'}
    all_paths=list(target.rglob('*'))
    if any(p.is_symlink() or p.resolve()!=p.absolute() for p in all_paths):raise ValueError('Output contains links')
    actual={p.relative_to(target).as_posix() for p in all_paths if p.is_file()}
    if actual!=expected:raise ValueError('Output file inventory mismatch')
    for relative,value in bundle['files'].items():
        if (target/relative).read_bytes()!=value:raise ValueError('Output bytes differ from verified expected result: '+relative)
    if load_json(target/'manifest.json')!=bundle['manifest']:raise ValueError('Manifest mismatch')
    check_inputs(bundle)


def generate(bundle,output,mode='build'):
    if mode not in ('build','dry-run','verify-only'):raise ValueError('Unsupported build mode')
    target=output_target(output)
    check_inputs(bundle)
    if mode=='dry-run':return bundle['manifest']
    if mode=='verify-only':
        verify_directory(bundle,target);return bundle['manifest']
    if target.exists():raise ValueError('Output already exists; choose a new directory')
    target.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='.localization-build-',dir=target.parent)).resolve()
    try:
        for relative,value in bundle['files'].items():
            path=staging/relative;path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as stream:stream.write(value)
        with (staging/'manifest.json').open('x',encoding='utf8',newline='\n') as stream:
            stream.write(serialize_json(bundle['manifest'])+'\n')
        verify_directory(bundle,staging)
        # Publish only fully verified output. Never overwrite a prior build.
        if target.exists():raise ValueError('Output appeared during build')
        # Windows scanners can briefly retain handles on newly written files.
        # Retry only the atomic rename; never fall back to a partial copy.
        for attempt in range(6):
            if target.exists():raise ValueError('Output appeared during build')
            try:
                staging.rename(target)
                break
            except PermissionError:
                if attempt==5:raise
                time.sleep(0.1*(2**attempt))
    finally:
        if staging.exists():
            if staging.parent!=target.parent.resolve() or not staging.name.startswith('.localization-build-'):
                raise ValueError('Unexpected staging path')
            shutil.rmtree(staging)
    return bundle['manifest']
