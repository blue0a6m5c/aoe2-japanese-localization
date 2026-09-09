import json
import copy
from pathlib import Path
import tempfile
import unittest

from tools.localization import mod_build,mod_package


def fixture():
    raw=('\ufeff// synthetic\r\n17415 "パルティアン\\n戦術"\r\n5001 "同値"\r\n5001 "同値"\r\n'
         '5002 "第一"\r\n5002 "第二"\r\n').encode('utf8')
    files={mod_package.INPUT_TRANSLATION:raw,'resources/jp/strings/key-value/unchanged.txt':b'// unchanged\n'}
    manifest=dict(output_file_hashes={k:mod_build.sha(v) for k,v in files.items()},changed_output_files=1,
                  source_hashes={'de_jp/key-value-strings-utf8.txt':'synthetic-original-hash'},
                  applied_operation_count=1,patch_plan_sha256='synthetic-plan-hash')
    return dict(files=files,manifest=manifest,protected_roots=[],protected={},input_hashes={},
                operations=[dict(operation_id='test-17415',string_id='17415',source_path='de_jp/key-value-strings-utf8.txt',
                                 source_line=2,after=r'パルティアン\n戦術')])


class ModPackageTests(unittest.TestCase):
    def setUp(self):
        Path('dist').mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir='dist');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.original=fixture()
        mod_build.generate(self.original,self.root/'phase1e')
        self.docs={'INSTALL.md':b'# Install\n','CHECKLIST.md':'# 検証\n'.encode('utf8')}

    def package(self):
        return mod_package.assemble(self.original,self.root/'phase1e',self.docs)

    def test_exact_values_and_only_changed_ids(self):
        p=self.package();raw=self.original['files'][mod_package.INPUT_TRANSLATION]
        self.assertNotEqual(p['files'][mod_package.OUTPUT_TRANSLATION],raw)
        self.assertEqual(p['files'][mod_package.OUTPUT_TRANSLATION],'17415 "パルティアン\\n戦術"\n'.encode('utf8'))
        mapping=p['manifest']['translation_mapping'][0]
        self.assertNotEqual(mapping['input_sha256'],mapping['package_sha256'])
        self.assertEqual(mapping['package_sha256'],mod_build.sha(p['files'][mod_package.OUTPUT_TRANSLATION]))
        self.assertEqual(p['manifest']['translation_file_count'],1)
        self.assertEqual(p['manifest']['unchanged_phase1e_files_omitted'],1)
        self.assertFalse(any('unchanged.txt' in name for name in p['files']))
        self.assertEqual(p['manifest']['verification']['duplicate_id_count'],0)
        self.assertEqual(p['manifest']['verification']['matching_value_count'],1)
        self.assertFalse(p['manifest']['runtime_verified'])

    def test_metadata_correct_case_and_root(self):
        p=self.package()
        info=json.loads(p['files'][mod_package.MOD_NAME+'/info.json'])
        self.assertEqual(set(info),{'Author','CacheStatus','Description','Title'})
        self.assertEqual(info['CacheStatus'],0)
        self.assertNotIn('Publish',info)

    def test_regeneration_verification_and_input_unchanged(self):
        before=mod_build.snapshot([self.root/'phase1e'])
        a=self.package();b=self.package()
        self.assertEqual(a['files'],b['files']);self.assertEqual(a['manifest'],b['manifest'])
        mod_build.generate(a,self.root/'a');mod_build.generate(b,self.root/'b')
        mod_build.generate(self.package(),self.root/'a','verify-only')
        for file in (self.root/'a').rglob('*'):
            if file.is_file():self.assertEqual(file.read_bytes(),(self.root/'b'/file.relative_to(self.root/'a')).read_bytes())
        self.assertEqual(mod_build.snapshot([self.root/'phase1e']),before)
        with self.assertRaises(ValueError):mod_build.generate(a,self.root/'a')

    def test_modified_phase1e_fails_before_output(self):
        (self.root/'phase1e'/mod_package.INPUT_TRANSLATION).write_bytes(b'corrupted')
        with self.assertRaises(ValueError):self.package()
        self.assertFalse((self.root/'output').exists())

    def test_multiple_changed_files_rejected(self):
        # Build a self-consistent synthetic manifest; packaging must still reject it.
        self.original['manifest']['changed_output_files']=2
        from tools.localization.blocked_audit import serialize_json
        (self.root/'phase1e/manifest.json').write_text(serialize_json(self.original['manifest']),encoding='utf8')
        with self.assertRaises(ValueError):self.package()

    def test_missing_documents_and_layout_checklist_regression(self):
        self.docs.pop('CHECKLIST.md')
        with self.assertRaises(ValueError):self.package()
        text=mod_package.DOCS['CHECKLIST.md'].read_text(encoding='utf8')
        records=json.loads(Path('reviews/phase1d-layout-decisions.json').read_text(encoding='utf8'))['records']
        self.assertEqual(len(records),13)
        for r in records:
            self.assertIn(r['string_id'],text)
            self.assertIn(r['replacement'],text)

    def test_later_input_change_or_output_tamper_detected(self):
        p=self.package();mod_build.generate(p,self.root/'output')
        target=self.root/'output'/mod_package.OUTPUT_TRANSLATION
        target.write_bytes(b'corrupt')
        with self.assertRaises(ValueError):mod_build.generate(p,self.root/'output','verify-only')
        (self.root/'phase1e'/mod_package.INPUT_TRANSLATION).write_bytes(b'corrupt')
        with self.assertRaises(ValueError):mod_build.generate(p,self.root/'new-output')

    def test_local_phase1e_integration(self):
        from tests.local_pipeline import inputs,payload
        item=inputs();input_dir=payload()[1]
        p=mod_package.prepare(*item['args'],input_dir)
        self.assertEqual(p['manifest']['verified_phase1e_operations'],387)
        self.assertTrue(p['manifest']['runtime_verified'])
        self.assertEqual(p['manifest']['runtime_validation']['status'],'matching_user_report')
        self.assertEqual(len(p['manifest']['runtime_validation']['confirmed_names']),7)
        self.assertEqual(p['manifest']['runtime_validation']['confirmed_ui'][0]['string_id'],'170300')
        mod_build.generate(p,self.root/'real-package');mod_build.generate(p,self.root/'real-package','verify-only')
        raw=(self.root/'real-package'/mod_package.OUTPUT_TRANSLATION).read_bytes()
        from tools.localization.parser import parse_text
        phase1e=parse_text((input_dir/mod_package.INPUT_TRANSLATION).read_bytes().decode('utf-8-sig'))
        plan=json.loads(item['args'][1].read_text(encoding='utf8'))
        ids={o['string_id'] for o in plan['operations']}
        expected={e.string_id:e.value for e in phase1e.entries if e.string_id in ids}
        report=mod_package.verify_delta(raw,expected)
        self.assertEqual(report['matching_value_count'],387)
        self.assertEqual(report['output_entry_count'],387)
        self.assertTrue(report['id_set_equal'])
        self.assertEqual(len(ids),387)
        with (self.root/'real-package/manifest.json').open(encoding='utf8') as f:self.assertEqual(json.load(f),p['manifest'])

    def test_missing_extra_duplicate_and_wrong_values_fail(self):
        expected={'17415':r'パルティアン\n戦術'}
        valid='17415 "パルティアン\\n戦術"\n'
        for text in ['',valid+'99 "extra"\n',valid+valid,'17415 "wrong"\n','17415 "unterminated']:
            with self.subTest(text=text),self.assertRaises(ValueError):
                mod_package.verify_delta(text.encode('utf8'),expected)

    def test_runtime_report_bound_to_translation_hash_and_preserved_as_input(self):
        path=self.root/'runtime.json'
        adopted='採用値'
        record=dict(schema_version=1,authority='explicit_user_runtime_report',result='pass',
                    confirmed_names=['試験名称'],confirmed_ui=[dict(string_id='9',adopted_jp=adopted,
                        result='pass',ownership_verified=True)],
                    record_id='synthetic',translation_sha256='expected')
        path.write_text(json.dumps(record),encoding='utf8')
        bundle=dict(manifest={'delta_sha256':'expected','value_provenance':[
            {'string_id':'9','value_sha256':mod_build.sha(adopted.encode('utf8'))}]},input_hashes={})
        mod_package.attach_game_validation(bundle,path)
        self.assertTrue(bundle['manifest']['runtime_verified'])
        self.assertEqual(bundle['manifest']['runtime_validation']['confirmed_ui'],record['confirmed_ui'])
        self.assertIn(str(path),bundle['input_hashes'])
        bundle['manifest']['delta_sha256']='different'
        mod_package.attach_game_validation(bundle,path)
        self.assertFalse(bundle['manifest']['runtime_verified'])
        self.assertEqual(bundle['manifest']['runtime_validation']['confirmed_names'],[])
        self.assertEqual(bundle['manifest']['runtime_validation']['confirmed_ui'],[])
        record['result']='unknown';path.write_text(json.dumps(record),encoding='utf8')
        with self.assertRaises(ValueError):mod_package.attach_game_validation(bundle,path)

    def test_runtime_ui_report_structure_and_current_value_are_validated(self):
        path=self.root/'runtime.json';adopted='採用値'
        valid=dict(string_id='9',adopted_jp=adopted,result='pass',ownership_verified=True)
        record=dict(schema_version=1,authority='explicit_user_runtime_report',result='pass',
                    confirmed_names=['試験名称'],confirmed_ui=[valid],record_id='synthetic',
                    translation_sha256='expected')
        bundle=dict(manifest={'delta_sha256':'expected','value_provenance':[
            {'string_id':'9','value_sha256':mod_build.sha(adopted.encode('utf8'))}]},input_hashes={})
        invalid=[None,{},dict(valid,string_id=''),dict(valid,adopted_jp=''),
                 dict(valid,result='unknown'),dict(valid,ownership_verified=False)]
        for item in invalid:
            record['confirmed_ui']=[item];path.write_text(json.dumps(record),encoding='utf8')
            with self.subTest(item=item),self.assertRaises(ValueError):
                mod_package.attach_game_validation(copy.deepcopy(bundle),path)
        for item in (dict(valid,adopted_jp='別の値'),dict(valid,string_id='10')):
            record['confirmed_ui']=[item];path.write_text(json.dumps(record),encoding='utf8')
            with self.subTest(item=item),self.assertRaises(ValueError):
                mod_package.attach_game_validation(copy.deepcopy(bundle),path)
        record['confirmed_ui']=[valid,valid];path.write_text(json.dumps(record),encoding='utf8')
        with self.assertRaises(ValueError):mod_package.attach_game_validation(bundle,path)

    def test_missing_or_duplicate_target_in_phase1e_is_not_resolved(self):
        for sid in ['99999','5001','5002']:
            b=copy.deepcopy(self.original);b['operations'][0]['string_id']=sid
            with self.subTest(sid=sid),self.assertRaises(ValueError):mod_package.delta_values(b)

    def test_target_count_location_and_value_binding(self):
        for field,value in [('source_line',3),('source_path','de_jp/another.txt'),('after','wrong')]:
            b=copy.deepcopy(self.original);b['operations'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):mod_package.delta_values(b)
        b=copy.deepcopy(self.original);b['operations']*=2
        with self.assertRaises(ValueError):mod_package.delta_values(b)
        b['manifest']['applied_operation_count']=2
        with self.assertRaises(ValueError):mod_package.delta_values(b)

    def test_escape_and_unicode_values_preserved(self):
        value=r'<b>日本語<b> \"引用\" %s <cost>\n次行'
        raw=f'9 "{value}"\n'.encode('utf8')
        # Use parser-valid escapes and retain exactly the stored representation.
        from tools.localization.parser import parse_text
        parsed=parse_text(raw.decode('utf8'))
        self.assertFalse(parsed.issues)
        self.assertEqual(mod_package.verify_delta(raw,{'9':value})['matching_value_count'],1)
