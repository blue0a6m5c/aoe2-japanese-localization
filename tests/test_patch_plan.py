"""Constructed sources and user-specified name examples, never full game fixtures."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import contextlib
import io

from tests.test_gameplay import add
from tools.localization.analysis import Dataset
from tools.localization.parser import ParsedFile
from tools.localization.gameplay import build_inventory
from tools.localization.adoption import signature
from tools.localization.scope import build_scope,render_audit
from tools.localization.restoration import digest
from tools.localization.patch_plan import build_plan,tokens,render_tsv
from tools.localization.__main__ import main


def seal(data):
    for ds in data.values():
        files={}
        for entries in ds.entries.values():
            for e in entries: files.setdefault(e.path,[]).append(e)
        ds.files=[]; ds.entries.clear()
        for path,entries in sorted(files.items()):
            entries=[replace(e,line=i+1) for i,e in enumerate(sorted(entries,key=lambda e:e.string_id))]
            raw='\n'.join(e.string_id+' '+e.value for e in entries)
            ds.add(ParsedFile(path,entries=entries,sha256=digest(raw)))


def fixture(en='River Runner',current='新走者',canonical='旧走者',heading=None,decision='restore',compact=None):
    data={n:Dataset(n) for n in ('de_en','de_jp','hd_en','hd_jp','aok_jp','aoc_jp')}
    for n,text in [('de_en',en),('hd_en',en),('de_jp',current),('hd_jp','旧参照'),('aok_jp','旧参照')]:
        add(data,n,'5001',text)
    add(data,'de_en','26001',f'Create <b>{en}<b> (<cost>)\\nSynthetic unit. %s <hp>')
    add(data,'de_jp','26001',f'<b>{heading or current}<b>の作成 (<cost>)\\n説明は保持。%s <hp>')
    if compact:
        add(data,'de_en',compact[0],en)
        add(data,'de_jp',compact[0],compact[1])
    seal(data)
    inv=build_inventory(data); helps=sorted({e['help_id'] for e in inv['rows'][0]['evidence']})
    ledger=dict(review_id='synthetic',reviewer='test user',baseline_ids=['5001'],records=[dict(string_id='5001',
        expected_de_english=en,decision=decision,proposed_jp=canonical,notes='Explicit test choice',help_ids=helps,
        signature=signature(data,'5001',helps))])
    audit=build_scope(data,ledger,inv)
    return data,ledger,audit


def plan(f):
    data,ledger,audit=f
    return build_plan(data,ledger,audit['rows'],audit)


class PatchPlanTests(unittest.TestCase):
    def test_eight_representative_names(self):
        cases=[('Crossbowman','石弓兵','石弓射手'),('Longbowman','ロングボウ兵','ロングボウ'),
               ('Teutonic Knight','チュートン騎士','チュートン ナイト'),('Archery Range','弓兵育成所','射手育成所'),
               ('Royal Janissary','王家のイェニチェリ','近衛イェニチェリ'),
               ('Siege Workshop','攻城兵器工房','包囲攻撃訓練所'),('Rocketry','ロケット技術','砲弾術'),('Perfusion','皆兵','パーフュージョン')]
        for en,current,canonical in cases:
            with self.subTest(en=en):
                result=plan(fixture(en,current,canonical))
                self.assertFalse(result['blocked'])
                self.assertEqual(result['statistics']['patch_operations'],2)
                for op in result['operations']:
                    self.assertEqual(op['replacement'],canonical)
                    self.assertEqual(tokens(op['before']),tokens(op['after']))

    def test_royal_help_only_name_span_keep_de(self):
        result=plan(fixture('Royal Janissary','近衛イェニチェリ','近衛イェニチェリ','王家のイェニチェリ','keep_de'))
        self.assertEqual(len(result['operations']),1)
        op=result['operations'][0]
        self.assertEqual(op['string_id'],'26001')
        self.assertEqual(op['matched_span'],[3,12])
        self.assertEqual(op['after'],r'<b>近衛イェニチェリ<b>の作成 (<cost>)\n説明は保持。%s <hp>')

    def test_normalized_14112_14128_excluded(self):
        for en,current,canonical,compact in [('Teutonic Knight','チュートン騎士','チュートン ナイト',('14112',r'チュートン\nナイト')),
                                              ('Archery Range','弓兵育成所','射手育成所',('14128',r'射手\n育成所'))]:
            f=fixture(en,current,canonical,compact=compact)
            self.assertNotIn(compact[0],[o['string_id'] for o in plan(f)['operations']])
            # Tampering with eligibility cannot turn an equivalent span into a patch.
            for r in f[2]['rows']:
                if r['related_string_id']==compact[0]:
                    r.update(scope_class='required',change_candidate=True,normalized_equal=False,normalized_equivalent=False)
            self.assertTrue(any('normalized_equivalent' in b['reasons'] for b in plan(f)['blocked']))

    def test_hash_current_span_and_fingerprint_fail_closed(self):
        for field,new,reason in [('source_sha256','wrong','occurrence_file_hash_mismatch'),
                                 ('matched_jp','missing','expected_current_span_mismatch'),
                                 ('related_jp','changed','expected_current_value_mismatch'),
                                 ('start',None,'invalid_or_missing_span'),
                                 ('decision_signature','wrong','decision_signature_mismatch')]:
            with self.subTest(field=field):
                f=fixture(); f[2]['rows'][0][field]=new
                result=plan(f)
                self.assertTrue(any(reason in b['reasons'] for b in result['blocked']))
        f=fixture(); f[2]['inputs'][0]['sha256']='changed'
        self.assertEqual(plan(f)['operations'],[])

    def test_identical_requests_merge_conflicting_requests_block(self):
        f=fixture(); f[2]['rows'].append(copy.deepcopy(f[2]['rows'][0]))
        self.assertEqual(plan(f)['statistics']['patch_operations'],2)
        self.assertEqual(max(o['merged_candidate_count'] for o in plan(f)['operations']),2)
        # Different canonical demand, even if an audit row was forged, quarantines the location.
        f[2]['rows'][-1]['effective_jp']='競合する訳'
        result=plan(f)
        self.assertTrue(result['blocked'])
        self.assertNotIn('5001',[o['string_id'] for o in result['operations']])

    def test_structure_change_and_newline_removal_blocked(self):
        for canonical in ('旧走者%s','<b>旧走者','旧走者\\n'):
            result=plan(fixture(canonical=canonical))
            self.assertFalse(result['operations'])
            self.assertTrue(all('technical_structure_changed' in b['reasons'] for b in result['blocked']))
        result=plan(fixture(current=r'新\n走者'))
        self.assertTrue(result['blocked'])

    def test_two_valid_decisions_with_different_replacements_conflict(self):
        data,human,audit=fixture()
        for n,text in [('de_en','River Runner'),('hd_en','River Runner'),('de_jp','新走者'),('hd_jp','旧参照'),('aok_jp','旧参照')]:
            add(data,n,'7001',text)
        add(data,'de_en','28001',r'Upgrade to <b>River Runner<b> (<cost>)\nSynthetic improvement.')
        add(data,'de_jp','28001',r'<b>新走者<b>へのアップグレード')
        seal(data); inv={r['string_id']:r for r in build_inventory(data)['rows']}
        other=copy.deepcopy(human['records'][0]); other.update(string_id='7001',proposed_jp='別の採用名')
        human['records'].append(other)
        for r in human['records']:
            r['help_ids']=sorted({e['help_id'] for e in inv[r['string_id']]['evidence']})
            r['signature']=signature(data,r['string_id'],r['help_ids'])
        audit=build_scope(data,human)
        result=build_plan(data,human,audit['rows'],audit)
        self.assertGreater(result['statistics']['conflicts'],0)
        self.assertTrue(any('replacement_conflict' in b['reasons'] for b in result['blocked']))

    def test_arbitrary_button_verb_cannot_be_replaced(self):
        data,human,audit=fixture()
        add(data,'de_en','9000','Create River Runner')
        add(data,'de_jp','9000','新走者の作成'); seal(data)
        human['records'][0]['signature']=signature(data,'5001',human['records'][0]['help_ids'])
        audit=build_scope(data,human)
        row=next(r for r in audit['rows'] if r['related_string_id']=='9000')
        row.update(start=3,end=6,matched_jp='の作成')
        result=build_plan(data,human,audit['rows'],audit)
        self.assertTrue(any('button_span_not_a_known_name' in b['reasons'] for b in result['blocked']))

    def test_other_duplicate_id_occurrence_never_modified(self):
        data,human,audit=fixture()
        add(data,'de_en','9000','Create River Runner')
        add(data,'de_jp','9000','新走者の作成')
        seal(data)
        human['records'][0]['signature']=signature(data,'5001',human['records'][0]['help_ids'])
        audit=build_scope(data,human)
        # Add a separately scoped occurrence. The original file and audited position remain unchanged.
        add(data,'de_jp','9000','別の対象を意味する','other.txt'); seal(data)
        audit['inputs']=[dict(dataset=n,path=f.path,sha256=f.sha256) for n,d in data.items() for f in d.files]
        result=build_plan(data,human,audit['rows'],audit)
        target=[o for o in result['operations'] if o['string_id']=='9000']
        self.assertEqual(len(target),1)
        self.assertTrue(target[0]['duplicate_dataset_id'])
        self.assertNotIn('other.txt',target[0]['source_path'])
        self.assertEqual(data['de_jp'].entries['9000'][1].value,'別の対象を意味する')
        # Exact same occurrence repeated is ambiguous and must be blocked.
        data['de_jp'].entries['9000'].append(data['de_jp'].entries['9000'][0])
        result=build_plan(data,human,audit['rows'],audit)
        self.assertTrue(any('nonunique_or_missing_occurrence' in b['reasons'] for b in result['blocked']))

    def test_determinism_and_no_mutation(self):
        f=fixture(); original=copy.deepcopy(f)
        first=plan(f); second=plan(f)
        self.assertEqual(first,second)
        self.assertEqual(render_tsv(first),render_tsv(second))
        self.assertEqual(f,original)

    def test_nonrequired_rows_never_generate_operations(self):
        for cls in ('recommended','review','unrelated','already_consistent'):
            f=fixture()
            for r in f[2]['rows']: r['scope_class']=cls
            self.assertEqual(plan(f)['operations'],[])

    def test_cli_only_writes_reports_and_preserves_existing_outputs(self):
        data,human,audit=fixture()
        Path('reports').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir='reports') as directory:
            root=Path(directory); inp=root/'input'; inp.mkdir()
            (inp/'scope-audit.tsv').write_text(render_audit(audit),encoding='utf8')
            (inp/'scope-metadata.json').write_text(json.dumps({k:v for k,v in audit.items() if k!='rows'}),encoding='utf8')
            lp=root/'ledger.json'; lp.write_text(json.dumps(human),encoding='utf8')
            args=['patch-plan','--scope-dir',str(inp),'--ledger',str(lp),'--output-dir',str(root/'out')]
            with patch('tools.localization.__main__.load_datasets',return_value=data),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(args),0)
                saved={p.name:p.read_bytes() for p in (root/'out').iterdir()}
                self.assertEqual(len(saved),4)
                self.assertEqual(main(args),2)
                self.assertEqual(saved,{p.name:p.read_bytes() for p in (root/'out').iterdir()})


if __name__=='__main__': unittest.main()
