"""Constructed source fixtures; the optional real-source test never builds a Mod."""
import copy
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.localization.analysis import Dataset, load_datasets
from tools.localization.parser import Entry, ParsedFile
from tools.localization.term_audit import build_audit, artifacts, write_artifacts, difference
from tools.localization.__main__ import main


RULES = dict(name_to_help_offsets=[21000, 12000, 11000], heading_aliases={},
             file_families={'ancient.txt': 'chronicles'}, dlc_help_ids={}, series={})


def add(data, dataset, sid, value, file='key-value-strings-utf8.txt'):
    path = f'{dataset}/{file}'
    data[dataset].add(ParsedFile(path, entries=[Entry(sid, value, path, int(sid) if sid.isdecimal() else 1)]))


def fixture():
    data = {n: Dataset(n) for n in ('de_en','de_jp','hd_en','hd_jp','aok_jp','aoc_jp')}
    for sid, en, jp in [
        ('5001','River Runner','川走者'), ('14001',r'River\nRunner',r'川の\n走者'),
        ('26001',r'Create <b>River Runner<b> (<cost>)\nInfantry. HIDDEN_BODY',
         r'<b>河走者<b>の作成 (<cost>)\nHIDDEN_JP_BODY'),
        ('6001','Create River Runner','川走者の作成')]:
        add(data,'de_en',sid,en);add(data,'de_jp',sid,jp)
    return data


def replace(data, dataset, sid, value):
    entry = data[dataset].entries[sid][0]
    data[dataset].entries[sid] = [Entry(sid, value, entry.path, entry.line)]


class TermAuditTests(unittest.TestCase):
    def test_concept_contains_names_button_and_heading_without_body(self):
        report = build_audit(fixture(), RULES)
        self.assertEqual(report['statistics']['concepts'], 1)
        self.assertEqual({o['string_id'] for o in report['occurrences']}, {'5001','14001','6001','26001'})
        self.assertEqual({f['kind'] for f in report['findings']}, {'concept_jp_variation','name_help_mismatch'})
        text = json.dumps(artifacts(report))
        self.assertNotIn('HIDDEN_BODY', text); self.assertNotIn('HIDDEN_JP_BODY', text)
        self.assertTrue(all(c['reviewer_decision'] is None for c in report['concepts']))
        self.assertEqual(report['statistics']['baseline_statuses'], {'one_supported_concept':1})

    def test_same_english_alone_is_candidate_not_membership(self):
        data=fixture();add(data,'de_en','999','River Runner');add(data,'de_jp','999','別表記')
        report=build_audit(data,RULES)
        self.assertNotIn('999',{o['string_id'] for o in report['occurrences']})
        self.assertTrue(any(u['string_id']=='999' for u in report['unresolved']))
        self.assertTrue(next(u for u in report['unresolved'] if u['string_id']=='999')['candidate_concept_ids'])
        self.assertTrue(all(r['status']=='candidate' for r in report['relations'] if r.get('name_id')=='999'))
        self.assertEqual(next(c['state'] for c in report['coverage'] if c['string_id']=='999'),'unresolved')

    def test_inventory_external_inflection_is_not_classified_candidate(self):
        data=fixture();add(data,'de_en','9998','River Runners');add(data,'de_jp','9998','複数の川走者')
        report=build_audit(data,RULES)
        self.assertNotIn('9998',{o['string_id'] for o in report['occurrences']})
        u=next(u for u in report['unresolved'] if u['string_id']=='9998')
        self.assertIn('same_file_inflected_label_candidate',u['reasons'])
        self.assertEqual(len(u['candidate_concept_ids']),1)
        c=next(c for c in report['coverage'] if c['string_id']=='9998')
        self.assertEqual(c['state'],'not_classified')
        self.assertEqual(c['candidate_concept_ids'],u['candidate_concept_ids'])

    def test_inventory_external_case_and_direct_operation_stay_candidates(self):
        data=fixture()
        for sid,en,jp in [('9997','RIVER RUNNER','upper'),('9996','Drop River Runner','drop')]:
            add(data,'de_en',sid,en);add(data,'de_jp',sid,jp)
        report=build_audit(data,RULES)
        concept=next(c['concept_id'] for c in report['concepts'] if c['english']=='River Runner')
        unresolved={u['string_id']:u for u in report['unresolved']}
        self.assertEqual(unresolved['9997']['candidate_concept_ids'],[concept])
        self.assertEqual(unresolved['9996']['candidate_concept_ids'],[concept])
        self.assertIn('same_file_direct_operation_candidate',unresolved['9996']['reasons'])
        self.assertFalse(any(o['string_id'] in {'9997','9996'} for o in report['occurrences']))

    def test_separate_same_spelling_anchors_never_merge(self):
        data=fixture()
        for sid,en,jp in [('5002','River Runner','第二走者'),
                          ('26002',r'Create <b>River Runner<b> (<cost>)\nInfantry.',r'<b>第二走者<b>の作成 (<cost>)')]:
            add(data,'de_en',sid,en);add(data,'de_jp',sid,jp)
        report=build_audit(data,RULES)
        self.assertEqual(report['statistics']['concepts'],2)
        self.assertNotIn('6001',{o['string_id'] for o in report['occurrences']})
        self.assertTrue(any('multiple_concept_actions' in u['reasons'] for u in report['unresolved']))

    def test_family_and_role_boundaries(self):
        data=fixture()
        for sid,en,jp,file in [
            ('5002','River Runner','古走者','ancient.txt'),
            ('26002',r'Create <b>River Runner<b> (<cost>)\nInfantry.',r'<b>古走者<b>の作成','ancient.txt'),
            ('7001','River Runner','川走者','key-value-strings-utf8.txt'),
            ('28001',r'Upgrade to <b>River Runner<b> (<cost>)\nInfantry.',r'<b>川走者<b>への進化','key-value-strings-utf8.txt')]:
            add(data,'de_en',sid,en,file);add(data,'de_jp',sid,jp,file)
        report=build_audit(data,RULES)
        self.assertEqual(report['statistics']['concepts'],3)
        self.assertEqual({c['category'] for c in report['concepts']},{'unit','technology'})
        self.assertFalse(any(f['kind']=='jp_collision_candidate' for f in report['findings']))

    def test_collision_does_not_merge_concepts(self):
        data=fixture()
        for sid,en,jp in [('5002','Mountain Runner','川走者'),
            ('26002',r'Create <b>Mountain Runner<b> (<cost>)\nInfantry.',r'<b>川走者<b>の作成')]:
            add(data,'de_en',sid,en);add(data,'de_jp',sid,jp)
        report=build_audit(data,RULES)
        finding=next(f for f in report['findings'] if f['kind']=='jp_collision_candidate')
        self.assertEqual(len(finding['concept_ids']),2)
        self.assertEqual(report['statistics']['concepts'],2)

    def test_duplicate_even_same_value_stays_unresolved(self):
        data=fixture();add(data,'de_jp','5001','川走者')
        report=build_audit(data,RULES)
        self.assertNotIn('5001',{o['string_id'] for o in report['occurrences']})
        self.assertTrue(any(u['string_id']=='5001' for u in report['unresolved']))
        self.assertEqual(report['diagnostics']['duplicates']['total'],1)

    def test_nested_language_paths_cannot_pair_by_basename(self):
        data=fixture()
        entry=data['de_jp'].entries['5001'][0]
        data['de_jp'].entries['5001']=[Entry('5001',entry.value,'de_jp/other/key-value-strings-utf8.txt',entry.line)]
        report=build_audit(data,RULES)
        self.assertNotIn('5001',{o['string_id'] for o in report['occurrences']})

    def test_nonstandard_heading_and_button_are_unresolved(self):
        data=fixture();replace(data,'de_jp','26001','河走者<b>の作成<b>')
        report=build_audit(data,RULES)
        self.assertIsNone(next(o for o in report['occurrences'] if o['role']=='help_heading')['jp_term'])
        self.assertTrue(any(u['kind']=='help_heading' for u in report['unresolved']))
        self.assertFalse(any(f['kind']=='name_help_mismatch' for f in report['findings']))

    def test_button_extracts_unknown_variant_and_ignores_effect_body(self):
        data=fixture();replace(data,'de_en','6001','Create River Runner (HIDDEN_EFFECT)')
        replace(data,'de_jp','6001','新たな走者の作成 (HIDDEN_TRANSLATION)')
        report=build_audit(data,RULES)
        o=next(o for o in report['occurrences'] if o['role']=='action_display')
        self.assertEqual(o['jp_term'],'新たな走者')
        self.assertNotIn('HIDDEN_EFFECT',json.dumps(artifacts(report)))

    def test_layout_only_is_visible_and_preserves_escaped_backslash(self):
        data=fixture()
        replace(data,'de_jp','14001',r'川\n走者');replace(data,'de_jp','26001',r'<b>川走者<b>の作成')
        report=build_audit(data,RULES)
        self.assertEqual({f['kind'] for f in report['findings']},{'layout_only_variation'})
        self.assertIn('wording_difference',difference(r'川\\n走者','川走者'))
        self.assertNotIn('layout_difference',difference(r'川\\n走者','川走者'))

    def test_no_ui_or_narrative_classification_and_unmatched_help_visible(self):
        data=fixture()
        for sid,text in [('111','Food'),('112','The runner says hello.'),
                         ('29000',r'Create <b>Missing Unit<b> (<cost>)\nInfantry.')]:
            add(data,'de_en',sid,text);add(data,'de_jp',sid,'未分類')
        report=build_audit(data,RULES)
        self.assertNotIn('111',{o['string_id'] for o in report['occurrences']})
        self.assertNotIn('112',{o['string_id'] for o in report['occurrences']})
        self.assertTrue(any(u['string_id']=='29000' for u in report['unresolved']))

    def test_history_reuse_missing_ambiguity_not_adoption(self):
        data=fixture()
        add(data,'hd_en','5001','Old Mountain');add(data,'hd_jp','5001','古山')
        add(data,'aoc_jp','5001','旧甲','a.dll');add(data,'aoc_jp','5001','旧乙','b.dll')
        report=build_audit(data,RULES)
        h=next(h for h in report['history'] if h['string_id']=='5001')
        self.assertEqual(h['continuity'],'english_changed_requires_review')
        self.assertEqual(h['datasets']['aoc_jp']['state'],'ambiguous')
        self.assertEqual(h['datasets']['aok_jp']['state'],'missing')
        self.assertTrue(all(c['reviewer_japanese'] is None for c in report['concepts']))
        self.assertFalse(any(f['kind']=='historical_jp_variation' for f in report['findings']))

    def test_reviewed_structural_seed_and_safe_historical_finding(self):
        data=fixture()
        for dataset,value in [('de_en','Sacred Object'),('de_jp','新名称'),
                              ('hd_en','Sacred Object'),('hd_jp','旧名称'),('aok_jp','旧名称')]:
            add(data,dataset,'5350',value)
        rules=copy.deepcopy(RULES)
        rules['concept_seeds']=[dict(seed_id='object-seed',name_id='5350',
            source_path='key-value-strings-utf8.txt',content_family='core',category='game_object',
            role='full_name',relation_kind='reviewed_structural_name_seed',
            confidence='reviewed_structural',provenance={'kind':'reviewed_string_role','reference':'fixture'})]
        report=build_audit(data,rules)
        concept=next(c for c in report['concepts'] if c['english']=='Sacred Object')
        self.assertEqual(concept['identity_status'],'reviewed_structural_seed')
        self.assertEqual(concept['seed_evidence']['confidence'],'reviewed_structural')
        finding=next(f for f in report['findings'] if f['kind']=='historical_jp_variation'
                     and concept['concept_id'] in f['concept_ids'])
        self.assertEqual(finding['detail']['hd_japanese'],'旧名称')
        self.assertEqual(finding['detail']['de_japanese'],'新名称')
        self.assertIsNone(finding['reviewer_decision'])
        before=finding['evidence_signature']
        replace(data,'de_jp','5350','別の新名称')
        after=next(f for f in build_audit(data,rules)['findings']
                   if f['kind']=='historical_jp_variation' and f['detail']['de_english']=='Sacred Object')
        self.assertNotEqual(before,after['evidence_signature'])

    def test_historical_finding_requires_legacy_support(self):
        data=fixture()
        add(data,'hd_en','5001','River Runner');add(data,'hd_jp','5001','旧名称')
        add(data,'aok_jp','5001','別概念名')
        report=build_audit(data,RULES)
        ids={o['occurrence_id'] for o in report['occurrences'] if o['string_id']=='5001'}
        self.assertFalse(any(f['kind']=='historical_jp_variation' and ids.intersection(f['occurrence_ids'])
                             for f in report['findings']))

    def test_existing_review_reference_is_readable_but_not_applied(self):
        report=build_audit(fixture(),RULES)
        report['review_references']=[dict(ledger='reviews/example.json',string_id='5001',
            signature='signed',binding_signature=None,adopted_value_sha256='hash',decision='restore',
            proposed_jp='旧訳',authority='explicit_user_decisions',notes_summary='human note',
            notes_reference={'ledger':'reviews/example.json','string_id':'5001'},
            evidence_status='matches',reference_only=True)]
        rows=list(csv.DictReader(io.StringIO(artifacts(report)['review.tsv']),delimiter='\t'))
        row=next(r for r in rows if json.loads(r['english'])=='River Runner')
        refs=json.loads(row['existing_review_references'])
        self.assertEqual(refs[0]['decision'],'restore')
        self.assertEqual(refs[0]['proposed_jp'],'旧訳')
        self.assertTrue(refs[0]['reference_only'])
        self.assertEqual(refs[0]['evidence_status'],'matches')
        self.assertIsNone(json.loads(row['reviewer_decision']))

    def test_unknown_escape_and_incomplete_input_fail_closed(self):
        from tools.localization.parser import parse_text, Issue
        data=fixture()
        data['de_jp'].add(parse_text(r'5001 "bad\q"','de_jp/key-value-strings-utf8.txt'))
        report=build_audit(data,RULES)
        self.assertNotIn('5001',{o['string_id'] for o in report['occurrences']})
        self.assertTrue(report['diagnostics']['issues'])
        data['de_en'].issues.append(Issue('encoding_error','bad.txt',1,'synthetic invalid UTF-8'))
        with self.assertRaises(ValueError):build_audit(data,RULES)

    def test_longer_action_name_is_not_a_partial_match(self):
        data=fixture()
        add(data,'de_en','6002','Create River Runner Knight')
        add(data,'de_jp','6002','川走者騎士の作成')
        report=build_audit(data,RULES)
        self.assertNotIn('6002',{o['string_id'] for o in report['occurrences']})

    def test_shared_label_multiple_anchors_stays_unresolved(self):
        data=fixture()
        # 14001 is offset-linked to both Help IDs (12000 and 11000).
        add(data,'de_en','25001',r'Create <b>River Runner<b> (<cost>)\nInfantry.')
        add(data,'de_jp','25001',r'<b>第二走者<b>の作成')
        report=build_audit(data,RULES)
        self.assertNotIn('14001',{o['string_id'] for o in report['occurrences']})
        self.assertTrue(any('multiple_structural_anchors' in u['reasons'] for u in report['unresolved']))
        ids={c['concept_id'] for c in report['concepts']}
        self.assertTrue(all(set(u['candidate_concept_ids']) <= ids for u in report['unresolved']))

    def test_all_source_spans_and_relations_are_reviewable(self):
        data=fixture();report=build_audit(data,RULES)
        cids={c['concept_id'] for c in report['concepts']}
        oids={o['occurrence_id'] for o in report['occurrences']}
        for o in report['occurrences']:
            for n,key in [('de_en','en'),('de_jp','jp')]:
                span=o[key+'_span']
                if span is not None:
                    self.assertEqual(data[n].resolved(o['string_id']).value[slice(*span)],o[key+'_term'])
        for f in report['findings']:
            self.assertTrue(set(f['concept_ids']) <= cids)
            self.assertTrue(set(f['occurrence_ids']) <= oids)
            self.assertIsNone(f['reviewer_decision'])
        for rel in report['relations']:
            if rel['status']=='supported':self.assertIn(rel['concept_id'],cids)

    def test_determinism_readonly_signatures_and_tsv_roundtrip(self):
        data=fixture();before=copy.deepcopy(data)
        report=build_audit(data,RULES)
        self.assertEqual(data,before)
        self.assertEqual(artifacts(report),artifacts(build_audit(data,RULES)))
        rows=list(csv.DictReader(io.StringIO(artifacts(report)['occurrences.tsv']),delimiter='\t'))
        decoded=[{k:json.loads(v) for k,v in row.items()} for row in rows]
        self.assertEqual(decoded,report['occurrences'])
        replace(data,'de_jp','5001','別走者')
        new=build_audit(data,RULES)
        self.assertEqual(report['concepts'][0]['concept_id'],new['concepts'][0]['concept_id'])
        self.assertNotEqual(report['findings'][0]['evidence_signature'],new['findings'][0]['evidence_signature'])

    def test_export_guard_manifest_and_no_overwrite(self):
        report=build_audit(fixture(),RULES)
        Path('reports/phase2a').mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir='reports/phase2a') as temp:
            target=Path(temp)/'run'
            paths=write_artifacts(report,target,Path('source'))
            self.assertTrue(paths)
            manifest=json.loads((target/'manifest.json').read_text(encoding='utf8'))
            from tools.localization.restoration import digest
            for name,h in manifest['artifact_sha256'].items():
                self.assertEqual(digest((target/name).read_text(encoding='utf8')),h)
            with self.assertRaises(ValueError):write_artifacts(report,target,Path('source'))
            with self.assertRaises(ValueError):write_artifacts(report,Path('reports/phase2a'),Path('source'))
            with self.assertRaises(ValueError):write_artifacts(report,Path('source/forbidden'),Path('source'))
            with self.assertRaises(ValueError):write_artifacts(report,Path(temp)/'bad',Path(temp))

    def test_cli_and_existing_input_diagnostic_exit_code(self):
        data=fixture();add(data,'hd_en','9','a');add(data,'hd_en','9','b')
        Path('reports/phase2a').mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir='reports/phase2a') as temp:
            with patch('tools.localization.__main__.load_datasets',return_value=data), \
                 patch('sys.stdout',new_callable=io.StringIO), patch('sys.stderr',new_callable=io.StringIO):
                self.assertEqual(main(['term-audit','--output-dir',str(Path(temp)/'run')]),1)


class LocalTermAuditTests(unittest.TestCase):
    @unittest.skipUnless(Path('source/de/en/key-value/key-value-strings-utf8.txt').exists(),'Optional local source missing')
    def test_real_baseline_and_representatives_readonly(self):
        report=build_audit(load_datasets(Path('source')))
        self.assertEqual(report['statistics']['baseline_groups'],72)
        self.assertEqual(report['statistics']['baseline_ids'],152)
        def by_id(sid):return next(o for o in report['occurrences'] if o['string_id']==sid)
        self.assertEqual(by_id('5039')['concept_id'],by_id('14039')['concept_id'])
        self.assertNotEqual(by_id('5039')['jp_term'],by_id('14039')['jp_term'])
        self.assertEqual(by_id('5033')['concept_id'],by_id('14033')['concept_id'])
        self.assertEqual(by_id('5033')['concept_id'],by_id('26033')['concept_id'])
        self.assertNotEqual(by_id('405015')['concept_id'],by_id('405016')['concept_id'])
        self.assertTrue(any(f['kind']=='jp_collision_candidate' and
            {by_id('405015')['concept_id'],by_id('405016')['concept_id']}.issubset(f['concept_ids']) for f in report['findings']))

        fire=by_id('5426')['concept_id']; galley=by_id('5160')['concept_id']
        fast_unit=by_id('5429')['concept_id']; fast_tech=by_id('7243')['concept_id']
        self.assertEqual(len({fire,galley,fast_unit,fast_tech}),4)
        self.assertNotEqual(fast_unit,fast_tech)
        unresolved={u['string_id']:u for u in report['unresolved']}
        self.assertEqual(unresolved['19279']['candidate_concept_ids'],[fire])
        self.assertEqual(set(unresolved['17242']['candidate_concept_ids']),{fast_unit,fast_tech})
        self.assertEqual(unresolved['12441']['candidate_concept_ids'],[fire])
        self.assertEqual(next(c['state'] for c in report['coverage'] if c['string_id']=='12441'),'not_classified')

        relic=by_id('5350')['concept_id']
        self.assertEqual(next(c for c in report['concepts'] if c['concept_id']==relic)['category'],'game_object')
        self.assertTrue(all(not any(o['string_id']==sid and o['concept_id']==relic for o in report['occurrences'])
                            for sid in ('5082','46520','65817','64618')))
        self.assertEqual(unresolved['10425']['candidate_concept_ids'],[relic])
        self.assertEqual(unresolved['40106']['candidate_concept_ids'],[relic])
        historical={next(o['string_id'] for o in report['occurrences']
                         if o['occurrence_id'] in f['occurrence_ids']) for f in report['findings']
                    if f['kind']=='historical_jp_variation'}
        self.assertTrue({'5426','5350'} <= historical)
        self.assertNotIn('5364',historical)


if __name__=='__main__':unittest.main()
