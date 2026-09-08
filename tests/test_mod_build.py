import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools.localization.mod_build import patch_bytes,sha,generate,prepare,SCHEMA,GENERATOR
from tools.localization.parser import parse_text
from tools.localization.patch_plan import tokens


def operation(raw,line=1,start=None,end=None,replacement='旧走者'):
    entry=next(e for e in parse_text(raw.decode('utf-8-sig'),'de_jp/test.txt').entries if e.line==line)
    before=entry.value;a=0 if start is None else start;b=len(before) if end is None else end
    return dict(operation_id='synthetic-'+str(line),source_path='de_jp/test.txt',source_line=line,
        string_id=entry.string_id,before=before,after=before[:a]+replacement+before[b:],
        expected_source_sha256=sha(raw),expected_value_sha256=sha(before.encode('utf8')),
        matched_span=[a,b],matched=before[a:b],replacement=replacement,
        replacement_type='full_value' if (a,b)==(0,len(before)) else 'span')


def bundle():
    files={'resources/jp/strings/key-value/test.txt':'5001 "旧走者"\r\n'.encode('utf8')}
    manifest=dict(schema_version=SCHEMA,generator=GENERATOR,output_file_hashes={k:sha(v) for k,v in files.items()})
    return dict(files=files,manifest=manifest,protected_roots=[],protected={},input_hashes={})


class ModBuildTests(unittest.TestCase):
    def test_full_value_and_physical_bytes_preserved(self):
        raw=('\ufeff// 日本語コメント\r\n 5001\t"新走者" // tail\n5002 "保持"\r5001 "別出現"').encode('utf8')
        op=operation(raw,2)
        result=patch_bytes(raw,'de_jp/test.txt',[op])
        self.assertEqual(result,raw.replace('新走者'.encode('utf8'),'旧走者'.encode('utf8')))
        self.assertIn('5001 "別出現"'.encode('utf8'),result)

    def test_royal_help_partial_and_layout_regression(self):
        raw=(r'26115 "<b>王家のイェニチェリ<b>の作成 (<cost>)\n説明 %s <i>"'+'\r\n'+
             r'17415 "パルティア\n戦術"').encode('utf8')
        ops=[operation(raw,1,3,12,'近衛イェニチェリ'),operation(raw,2,replacement=r'パルティアン\n戦術')]
        result=patch_bytes(raw,'de_jp/test.txt',ops)
        values=[e.value for e in parse_text(result.decode('utf8')).entries]
        self.assertEqual(values,[r'<b>近衛イェニチェリ<b>の作成 (<cost>)\n説明 %s <i>',r'パルティアン\n戦術'])
        for op in ops:self.assertEqual(tokens(op['before']),tokens(op['after']))

    def test_hash_value_span_id_location_fail_closed(self):
        raw=b'5001 "new"\n'
        base=operation(raw,replacement='old')
        for k,v in [('source_path','de_jp/other.txt'),('source_line',2),('string_id','5002'),
            ('expected_source_sha256','wrong'),('expected_value_sha256','wrong'),('before','wrong'),
            ('matched','wrong'),('matched_span',[0,99]),('after','wrong'),('replacement_type','span')]:
            with self.subTest(field=k),self.assertRaises(ValueError):
                op=copy.deepcopy(base);op[k]=v;patch_bytes(raw,'de_jp/test.txt',[op])

    def test_double_application_rejected(self):
        raw=b'5001 "new"\n';op=operation(raw,replacement='old')
        with self.assertRaises(ValueError):patch_bytes(raw,'de_jp/test.txt',[op,op])
        once=patch_bytes(raw,'de_jp/test.txt',[op])
        with self.assertRaises(ValueError):patch_bytes(once,'de_jp/test.txt',[op])

    def test_tokens_and_unknown_escapes_rejected(self):
        raw=b'5001 "new"\n'
        for replacement in ['old %s','<b>old',r'old\n','old\n','old"']:
            with self.subTest(replacement=replacement),self.assertRaises(ValueError):
                patch_bytes(raw,'de_jp/test.txt',[operation(raw,replacement=replacement)])
        raw=b'5001 "new\\q"\n'
        with self.assertRaises(ValueError):patch_bytes(raw,'de_jp/test.txt',[operation(raw,replacement=r'old\q')])

    def test_untouched_file_exact_and_unicode_separators(self):
        raw='\ufeff// untouched\r\n5001 "日本語\u2028表示"\r\n'.encode('utf8')
        self.assertEqual(patch_bytes(raw,'de_jp/test.txt',[]),raw)

    def test_build_dry_run_verify_and_determinism(self):
        Path('dist').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir='dist') as temp:
            root=Path(temp);b=bundle()
            generate(b,root/'dry','dry-run');self.assertFalse((root/'dry').exists())
            generate(b,root/'a');generate(b,root/'b')
            expected={p.relative_to(root/'a'):p.read_bytes() for p in (root/'a').rglob('*') if p.is_file()}
            self.assertEqual(expected,{p.relative_to(root/'b'):p.read_bytes() for p in (root/'b').rglob('*') if p.is_file()})
            generate(b,root/'a','verify-only')
            with self.assertRaises(ValueError):generate(b,root/'a')
            with (root/'a/manifest.json').open(encoding='utf8') as stream:self.assertEqual(json.load(stream),b['manifest'])
            (root/'a/extra.txt').write_bytes(b'extra')
            with self.assertRaises(ValueError):generate(b,root/'a','verify-only')

    def test_output_tamper_and_missing_files_detected(self):
        Path('dist').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir='dist') as temp:
            root=Path(temp);b=bundle();generate(b,root/'output')
            path=root/'output'/next(iter(b['files']))
            path.write_bytes(b'bad')
            with self.assertRaises(ValueError):generate(b,root/'output','verify-only')
            path.unlink()
            with self.assertRaises(ValueError):generate(b,root/'output','verify-only')

    def test_protected_directory_and_changed_input_rejected(self):
        with self.assertRaises(ValueError):generate(bundle(),Path('source/output'))
        with self.assertRaises(ValueError):generate(bundle(),Path('reviews/output'))
        Path('dist').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir='dist') as temp:
            root=Path(temp);p=root/'input';p.write_bytes(b'original')
            b=bundle();b['input_hashes']={str(p):sha(p.read_bytes())};p.write_bytes(b'changed')
            with self.assertRaises(ValueError):generate(b,root/'output')
            self.assertFalse((root/'output').exists())


class LocalModIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tools.localization.human_reviews import DEFAULT_LEDGER
        cls.plan=Path('reports/phase1d-layout/patch-plan.json')
        if not cls.plan.exists():raise unittest.SkipTest('Local audited source data unavailable')
        cls.args=(Path('source'),cls.plan,DEFAULT_LEDGER,Path('reviews/phase1d-layout-decisions.json'),Path('reports/phase1c-normalized'))
        cls.b=prepare(*cls.args)

    def test_real_346_output_and_unchanged_records(self):
        b=self.b;m=b['manifest']
        self.assertEqual((m['applied_operation_count'],m['full_value_replacements'],m['span_replacements'],m['changed_output_files']),
                         (346,186,160,1))
        self.assertEqual(len(b['files']),12)
        Path('dist').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir='dist') as temp:
            root=Path(temp);generate(b,root/'a');generate(b,root/'b');generate(b,root/'a','verify-only')
            for p in (root/'a').rglob('*'):
                if p.is_file():self.assertEqual(p.read_bytes(),(root/'b'/p.relative_to(root/'a')).read_bytes())
            plan=json.loads(self.plan.read_text(encoding='utf8'))
            output=parse_text(b['files']['resources/jp/strings/key-value/key-value-strings-utf8.txt'].decode('utf-8-sig'))
            values={(e.line,e.string_id):e.value for e in output.entries}
            for op in plan['operations']:self.assertEqual(values[(op['source_line'],op['string_id'])],op['after'])

    def test_signature_tamper_in_actual_plan_is_rejected(self):
        from tools.localization.blocked_audit import serialize_json
        with tempfile.TemporaryDirectory(dir='reports') as temp:
            p=Path(temp)/'plan.json';obj=json.loads(self.plan.read_text(encoding='utf8'))
            obj['operations'][0]['evidence'][0]['decision_signature']='tampered'
            p.write_text(serialize_json(obj),encoding='utf8')
            with self.assertRaises(ValueError):prepare(self.args[0],p,*self.args[2:])
