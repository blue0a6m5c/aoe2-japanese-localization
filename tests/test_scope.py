"""Synthetic occurrence-level scope checks; no official localization fixtures."""
import copy
import csv
import io
import json
import unittest
import contextlib
import tempfile
from pathlib import Path
from unittest.mock import patch

from tests.test_gameplay import synthetic, add, RULES
from tests.test_human_reviews import ledger
from tools.localization.analysis import Dataset
from tools.localization.gameplay import build_inventory
from tools.localization.scope import build_scope, conflicts, render_audit, CLASSES
from tools.localization.__main__ import main


def build(data=None,human=None):
    data=synthetic() if data is None else data
    human=ledger(data,['5001'],jp='旧走者') if human is None else human
    return build_scope(data,human,build_inventory(data,RULES))


class ScopeTests(unittest.TestCase):
    def test_name_and_linked_heading_required(self):
        report=build()
        rows=report['rows']
        self.assertEqual(next(r for r in rows if r['related_string_id']=='5001')['scope_class'],'required')
        self.assertEqual(next(r for r in rows if r['related_string_id']=='26001')['scope_class'],'required')
        self.assertFalse(report['conflicts'])

    def test_all_85_generated_adjudications_are_audited(self):
        data={n:Dataset(n) for n in ('de_en','de_jp','hd_en','hd_jp','aok_jp','aoc_jp')}
        ids=[]
        for i in range(85):
            sid=str(50000+i); ids.append(sid)
            for n,text in [('de_en',f'River Unit {i:02}'),('hd_en',f'River Unit {i:02}'),
                           ('de_jp',f'新名称{i:02}'),('hd_jp',f'旧名称{i:02}'),('aok_jp',f'旧名称{i:02}')]:
                add(data,n,sid,text)
            add(data,'de_en',str(71000+i),f'Create <b>River Unit {i:02}<b> (<cost>)\\nUnique Infantry.')
        human=ledger(data,ids,jp='人間の裁定')
        report=build(data,human)
        self.assertEqual(report['decision_count'],85)
        self.assertEqual(set(report['audited_decision_ids']),set(ids))
        self.assertFalse(report['no_occurrence_decisions'])

    def test_no_mutation_and_deterministic_tsv(self):
        data=synthetic(); human=ledger(data,['5001'])
        before_data=copy.deepcopy(data); before_human=copy.deepcopy(human)
        first=build(data,human); second=build(data,human)
        self.assertEqual(render_audit(first),render_audit(second))
        self.assertEqual(data,before_data)
        self.assertEqual(human,before_human)
        rows=list(csv.DictReader(io.StringIO(render_audit(first)),delimiter='\t'))
        self.assertEqual(len(rows),first['total'])
        self.assertTrue(all(json.loads(r['source_path']) for r in rows))

    def test_body_recommended_generic_text_review_and_consistent_heading(self):
        data=synthetic()
        data['de_jp'].entries['26001']=[]
        add(data,'de_jp','26001',r'<b>旧走者<b>の作成')
        add(data,'de_en','40001',r'Create <b>Stone Sentinel<b> (<cost>)\nStrong against River Runner.')
        add(data,'de_jp','40001',r'<b>石の衛兵<b>の作成\n川の走者に強い。')
        add(data,'de_en','40002','A traveller follows a river.')
        add(data,'de_jp','40002','川の走者について語る文章。')
        rows=build(data)['rows']
        self.assertEqual(next(r for r in rows if r['related_string_id']=='26001')['scope_class'],'already_consistent')
        self.assertEqual(next(r for r in rows if r['related_string_id']=='40001')['scope_class'],'recommended')
        self.assertEqual(next(r for r in rows if r['related_string_id']=='40002')['scope_class'],'review')

    def test_longer_other_unit_is_unrelated_not_change_candidate(self):
        data=synthetic()
        add(data,'de_en','5003','Silver Runner')
        add(data,'de_jp','5003','銀川の走者')
        add(data,'de_en','26003',r'Create <b>Silver Runner<b> (<cost>)\nUnique Infantry.')
        add(data,'de_jp','26003',r'<b>銀川の走者<b>の作成')
        rows=[r for r in build(data)['rows'] if r['related_string_id'] in ('5003','26003')]
        self.assertTrue(rows)
        self.assertTrue(all(r['scope_class']=='unrelated' and not r['change_candidate'] for r in rows))

    def test_duplicate_input_is_review(self):
        data=synthetic()
        add(data,'de_jp','40001','川の走者')
        add(data,'de_jp','40001','川の走者')
        add(data,'de_en','40001','River Runner')
        report=build(data)
        self.assertIn('40001',report['duplicate_input_ids'])
        self.assertTrue(all(r['scope_class']=='review' for r in report['rows'] if r['related_string_id']=='40001'))

    def test_button_with_description_only_targets_name(self):
        data=synthetic()
        add(data,'de_en','90001','Create River Runner (Moves quickly)')
        add(data,'de_jp','90001','川の走者の作成 (素早く移動する)')
        row=next(r for r in build(data)['rows'] if r['related_string_id']=='90001')
        self.assertEqual(row['scope_class'],'required')
        self.assertEqual(row['matched_jp'],'川の走者')
        self.assertEqual(row['related_type'],'button_with_description')

    def test_already_spelled_adopted_body_is_not_a_change_candidate(self):
        data=synthetic()
        add(data,'de_en','40001',r'Create <b>Stone Sentinel<b> (<cost>)\nStrong against River Runner and River Runners.')
        add(data,'de_jp','40001',r'<b>石の衛兵<b>の作成\n旧走者と旧走者に強い。')
        rows=[r for r in build(data)['rows'] if r['related_string_id']=='40001']
        self.assertTrue(rows)
        self.assertTrue(all(r['scope_class']=='review' and not r['change_candidate'] for r in rows))

    def test_multiple_decisions_share_id_and_conflicting_slot_is_reported(self):
        data=synthetic()
        for n,v in [('de_en','River Runner'),('hd_en','River Runner'),('de_jp','川の走者'),('hd_jp','旧走者'),('aok_jp','旧走者')]:
            add(data,n,'7001',v)
        add(data,'de_en','28001',r'Upgrade to <b>River Runner<b> (<cost>)\nImproves units.')
        add(data,'de_jp','28001',r'<b>川の走者<b>へのアップグレード')
        human=ledger(data,['5001','7001'],jp='旧走者')
        same=build(data,human)
        self.assertIn('26001',same['multiple_decision_references'])
        self.assertEqual(same['conflict_count'],0)
        human['records'][1]['proposed_jp']='別の採用訳'
        conflicting=build(data,human)
        self.assertGreater(conflicting['conflict_count'],0)

    def test_different_body_spans_are_not_conflict(self):
        def row(s,a,b,jp):
            return dict(decision_string_id=s,source_path='synthetic',source_line=1,related_string_id='99',
                        scope_class='recommended',start=a,end=b,effective_jp=jp)
        self.assertEqual(conflicts([row('1',0,3,'案A'),row('2',4,7,'案B')]),[])
        a=row('1',0,3,'案A'); b=row('2',0,3,'案B'); b['scope_class']='unrelated'
        self.assertEqual(conflicts([a,b]),[])

    def test_stale_and_other_content_are_never_required(self):
        data=synthetic(); human=ledger(data,['5001'])
        add(data,'de_en','40001','River Runner','ancient.txt')
        add(data,'de_jp','40001','川の走者','ancient.txt')
        report=build(data,human)
        self.assertEqual(next(r for r in report['rows'] if r['related_string_id']=='40001')['scope_class'],'review')
        add(data,'hd_en','26001','Changed reference')
        report=build(data,human)
        self.assertIn('5001',report['stale_decisions'])
        self.assertFalse(any(r['change_candidate'] for r in report['rows']))

    def test_cli_filter_report_guard_and_no_source_or_ledger_write(self):
        data=synthetic(); human=ledger(data,['5001'],jp='旧走者')
        before_data=copy.deepcopy(data); before_human=copy.deepcopy(human)
        Path('reports').mkdir(exist_ok=True)
        with patch('tools.localization.__main__.load_datasets',return_value=data), patch('tools.localization.scope.load_ledger',return_value=human):
            out=io.StringIO()
            with contextlib.redirect_stdout(out),contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['scope-review','--class','required','--limit','1']),0)
            self.assertEqual(len(json.loads(out.getvalue())['rows']),1)
            with tempfile.TemporaryDirectory(dir='reports') as directory,contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                args=['scope-audit','--output-dir',directory]
                self.assertEqual(main(args),0)
                saved={p.name:p.read_bytes() for p in Path(directory).iterdir()}
                self.assertEqual(len(saved),4)
                self.assertEqual(main(args),2)
                self.assertEqual(saved,{p.name:p.read_bytes() for p in Path(directory).iterdir()})
                self.assertEqual(main(['scope-audit','--output-dir','source/scope-test']),2)
                self.assertFalse(Path('source/scope-test').exists())
        self.assertEqual(data,before_data)
        self.assertEqual(human,before_human)


if __name__=='__main__': unittest.main()
