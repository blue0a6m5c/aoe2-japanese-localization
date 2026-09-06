"""Synthetic gameplay evidence only; no official localization fixtures."""

import contextlib
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.localization.analysis import Dataset
from tools.localization.parser import Entry, ParsedFile, parse_text
from tools.localization.gameplay import build_inventory, filter_rows, render_tsv
from tools.localization.__main__ import main


RULES = dict(name_to_help_offsets=[21000, 12000, 11000], heading_aliases={},
             file_families={'ancient.txt': 'chronicles'}, dlc_help_ids={'synthetic_pack': ['26002']},
             series={'test_line': ['5001', '5002']})


def add(data, dataset, sid, value, file='key-value-strings-utf8.txt'):
    # Entry construction avoids escaping fixtures into an unrelated syntax.
    data[dataset].add(ParsedFile(f'{dataset}/{file}', entries=[Entry(sid, value, f'{dataset}/{file}', 1)]))


def synthetic():
    data = {n: Dataset(n) for n in ('de_en', 'de_jp', 'hd_en', 'hd_jp', 'aoc_jp', 'aok_jp')}
    add(data, 'de_en', '5001', 'River Runner')
    add(data, 'de_en', '26001', r'Create <b>River Runner<b> (<cost>)\nUnique Infantry.')
    add(data, 'de_jp', '5001', '川の走者')
    add(data, 'de_jp', '26001', r'<b>川の走者<b>の作成')
    add(data, 'de_en', '5002', 'Elite River Runner')
    add(data, 'de_en', '26002', r'Create <b>Elite River Runner<b> (<cost>)\nUnique Infantry.')
    add(data, 'de_jp', '5002', '精鋭川の走者')
    add(data, 'de_jp', '26002', r'<b>精鋭川の走者<b>の作成')
    for n, value in [('hd_en','River Runner'), ('hd_jp','旧走者'), ('aok_jp','旧走者')]:
        add(data,n,'5001',value)
    return data


def index(data, rules=RULES):
    return {r['string_id']: r for r in build_inventory(data, rules)['rows']}


class GameplayTests(unittest.TestCase):
    def test_name_link_and_historical_flags(self):
        rows = index(synthetic())
        r = rows['5001']
        self.assertEqual(r['category'], 'unit')
        self.assertEqual(r['label_role'], 'full_name')
        self.assertIn('unique_unit', r['subcategories'])
        self.assertIn('jp_only_changed', r['flags'])
        self.assertIn('legacy_stable_de_changed', r['flags'])
        self.assertEqual(r['datasets']['aoc_jp']['state'], 'missing')
        self.assertIn('de_new_id', rows['5002']['flags'])
        self.assertNotIn('26001', rows)

    def test_no_range_based_classification_or_campaign_sentences(self):
        data = synthetic()
        add(data,'de_en','5003','This unrelated short text')
        add(data,'de_en','60000','The runner says: our journey begins.')
        self.assertNotIn('5003',index(data))
        self.assertNotIn('60000',index(data))

    def test_build_verb_distinguishes_unit_and_building(self):
        data=synthetic()
        for sid,name,body in [('5004','Stone Hall','Used to train a unique unit.'),
                              ('5005','Iron Wagon','Siege Gunpowder Unit with ranged attack.'),
                              ('5006','Unknown Construct','A mysterious item.')]:
            add(data,'de_en',sid,name)
            add(data,'de_en',str(int(sid)+21000),f'Build <b>{name}<b> (<cost>)\\n{body}')
        rows=index(data)
        self.assertEqual([rows[s]['category'] for s in ['5004','5005','5006']],['building','unit','unknown'])

    def test_technology_upgrade_age_and_unique_tech(self):
        data=synthetic()
        for sid,name,action in [('7001','River Wisdom','Research'),('7002','Elite River Runner','Upgrade to'),('7003','Dawn Age','Advance to')]:
            add(data,'de_en',sid,name)
            add(data,'de_en',str(int(sid)+21000),f'{action} <b>{name}<b> (<cost>)\\nImproves things.')
        add(data,'de_en','120000',r'<b>Unique Techs:<b>\n• River Wisdom (more supplies)\n\n<b>Team Bonus:<b>')
        rows=index(data)
        self.assertIn('unique_technology',rows['7001']['subcategories'])
        self.assertIn('unit_upgrade',rows['7002']['subcategories'])
        self.assertEqual(rows['7003']['category'],'age')

    def test_chronicles_not_cross_linked_or_collision_grouped(self):
        data=synthetic()
        add(data,'de_en','6001','River Runner','ancient.txt')
        add(data,'de_jp','6001','古代の走者','ancient.txt')
        add(data,'de_en','27001',r'Create <b>River Runner<b> (<cost>)\nInfantry.','ancient.txt')
        add(data,'de_en','9901','River Runner','unrelated-campaign.txt')
        rows=index(data)
        self.assertEqual(rows['6001']['content_family'],'chronicles')
        self.assertNotIn('jp_label_variation',rows['5001']['flags'])
        self.assertNotIn('9901',rows)

    def test_ambiguity_blocks_legacy_claim(self):
        data=synthetic()
        add(data,'aoc_jp','5001','旧走者','one.dll')
        add(data,'aoc_jp','5001','別の走者','two.dll')
        row=index(data)['5001']
        self.assertIn('input_ambiguity',row['flags'])
        self.assertNotIn('legacy_stable_de_changed',row['flags'])
        self.assertEqual(len(row['datasets']['aoc_jp']['occurrences']),2)

    def test_reused_id_is_not_legacy_restoration_or_new_id(self):
        data=synthetic()
        data['hd_en'].entries['5001']=[Entry('5001','Old Rock','old',1)]
        row=index(data)['5001']
        self.assertIn('historical_english_changed',row['flags'])
        self.assertIn('de_name_not_in_hd_en',row['flags'])
        self.assertNotIn('legacy_stable_de_changed',row['flags'])
        self.assertNotIn('de_new_id',row['flags'])

    def test_incomplete_history_not_reported_as_new(self):
        data=synthetic();del data['aok_jp']
        row=index(data)['5002']
        self.assertIn('history_incomplete',row['flags'])
        self.assertNotIn('de_new_id',row['flags'])

    def test_suspicious_flags_and_missing(self):
        data=synthetic()
        data['de_jp'].entries['5001']=[Entry('5001','River Runner','test',1)]
        r=index(data)['5001']
        self.assertTrue({'latin_remaining','same_as_english','name_help_jp_mismatch'}.issubset(r['flags']))
        del data['de_jp'].entries['5001']
        self.assertIn('missing_de_jp',index(data)['5001']['flags'])

    def test_collision_does_not_merge_different_english_names(self):
        data=synthetic()
        add(data,'de_en','5003','Mountain Runner')
        add(data,'de_en','26003',r'Create <b>Mountain Runner<b> (<cost>)\nInfantry.')
        add(data,'de_jp','5003','川の走者')
        rows=index(data)
        self.assertIn('jp_collision',rows['5001']['flags'])
        self.assertIn('5003',rows['5001']['related_ids'])

    def test_series_never_crosses_content_families(self):
        rows=index(synthetic())
        self.assertEqual(rows['5001']['series'],[])
        rules={**RULES,'dlc_help_ids':{}}
        data=synthetic();data['de_jp'].entries['5002']=[Entry('5002','無関係な語','test',1)]
        rows=index(data,rules)
        self.assertIn('test_line',rows['5001']['series'])
        self.assertIn('series_stem_review',rows['5001']['flags'])

    def test_mismatched_english_heading_stays_unknown(self):
        data=synthetic();data['de_en'].entries['5001']=[Entry('5001','Wrong Label','de_en/key-value-strings-utf8.txt',1)]
        row=index(data)['5001']
        self.assertEqual(row['category'],'unknown')
        self.assertIn('english_name_help_mismatch',row['flags'])

    def test_nonstandard_japanese_bold_is_not_treated_as_name(self):
        data=synthetic()
        data['de_jp'].entries['26001']=[Entry('26001','川の走者<b>の作成<b>','test',1)]
        row=index(data)['5001']
        self.assertIn('jp_heading_structure_review',row['flags'])
        self.assertNotIn('name_help_jp_mismatch',row['flags'])

    def test_tsv_roundtrip_preserves_values_and_ambiguity(self):
        data=synthetic()
        add(data,'aoc_jp','5001','first\tvalue','one.dll')
        add(data,'aoc_jp','5001','second\nvalue','two.dll')
        data['de_jp'].entries['5001']=[Entry('5001','=DANGER()\t"quoted"','test',1)]
        rows=list(index(data).values())
        parsed=list(csv.DictReader(io.StringIO(render_tsv(rows)),delimiter='\t'))
        self.assertEqual(json.loads(parsed[0]['DE JP']),'=DANGER()\t"quoted"')
        self.assertEqual(json.loads(parsed[0]['AoC JP'.upper()])['state'],'ambiguous')
        self.assertTrue(parsed[0]['DE JP'].startswith('"'))

    def test_cli_filter_report_and_determinism(self):
        data=synthetic()
        self.assertEqual(build_inventory(data,RULES),build_inventory(data,RULES))
        out,err=io.StringIO(),io.StringIO()
        with patch('tools.localization.__main__.load_datasets',return_value=data), contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            self.assertEqual(main(['names','--category','unit','--primary','--limit','1']),0)
        self.assertEqual(len(json.loads(out.getvalue())['rows']),1)
        Path('reports').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir='reports') as temp:
            path=Path(temp)/'names.tsv'
            with patch('tools.localization.__main__.load_datasets',return_value=data),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['names','--all','--format','tsv','--output',str(path)]),0)
            self.assertEqual(len(list(csv.DictReader(io.StringIO(path.read_text(encoding='utf-8')),delimiter='\t'))),2)
        with patch('tools.localization.__main__.load_datasets',return_value=data),contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['names','--all']),2)


if __name__=='__main__':
    unittest.main()
