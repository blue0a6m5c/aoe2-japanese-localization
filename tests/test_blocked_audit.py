import copy
import unittest

from tests.test_patch_plan import fixture, plan
from tools.localization.blocked_audit import audit_blocked, layout_proposal, render_table, causes, token_parts
from tools.localization.patch_plan import tokens


def audit(f):
    data,ledger,scope=f
    return audit_blocked(data,ledger,scope['rows'],scope)


class BlockedAuditTests(unittest.TestCase):
    def test_elite_unchanged_component(self):
        proposed,reason=layout_proposal(r'精鋭\nベルセルク','エリート ベルセルク')
        self.assertEqual(proposed,r'エリート\nベルセルク')
        self.assertIn('ベルセルク',reason)
        self.assertEqual(tokens(proposed),[r'\n'])

    def test_normalized_names_need_no_change(self):
        for current,canonical in [(r'チュートン\nナイト','チュートン ナイト'),
                                  (r'射手\n育成所','射手育成所')]:
            self.assertIsNone(layout_proposal(current,canonical)[0])

    def test_help_markup_and_placeholder_preserved(self):
        f=fixture('Elite Runner',r'精鋭\n走者','エリート 走者')
        result=audit(f)
        self.assertEqual(result['statistics']['auto_resolvable_locations'],2)
        help_row=next(r for r in result['rows'] if r['string_id']=='26001')
        self.assertEqual(help_row['proposed_after'],r'<b>エリート\n走者<b>の作成 (<cost>)\n説明は保持。%s <hp>')
        self.assertEqual(help_row['tokens_before'],help_row['tokens_after'])

    def test_unsafe_transfer_is_manual(self):
        for current,canonical in [(r'旧甲\n旧乙','新甲 新乙'),(r'旧甲\n共通','新甲共通'),
                (r'旧甲\n共通\n末尾','新甲 共通 末尾'),(r'旧甲\\n共通','新甲 共通'),
                (r'<b>旧甲\n共通<b>','新甲 共通'),(r'旧甲\n%s','新甲 %s')]:
            with self.subTest(current=current):
                self.assertIsNone(layout_proposal(current,canonical)[0])

    def test_preserves_spaces_around_break_not_offsets(self):
        proposed,_=layout_proposal('短 \n 共通','非常に長い 共通')
        self.assertEqual(proposed,'非常に長い \n 共通')

    def test_other_safety_failures_remain_blocked(self):
        f=fixture('Elite Runner',r'精鋭\n走者','エリート 走者')
        f[2]['rows'][0]['source_sha256']='wrong'
        result=audit(f)
        self.assertGreater(result['statistics']['manual_review_locations'],0)
        self.assertGreater(result['statistics']['cause_counts']['source_hash']['source_locations'],0)

    def test_merge_identical_requests_and_reject_conflict(self):
        f=fixture('Elite Runner',r'精鋭\n走者','エリート 走者')
        r=copy.deepcopy(next(r for r in f[2]['rows'] if r['scope_class']=='required'))
        f[2]['rows'].append(r)
        result=audit(f)
        self.assertEqual(result['statistics']['additional_operations'],2)
        self.assertEqual(result['statistics']['auto_resolvable_candidates'],3)
        r['effective_jp']='別の 走者'
        result=audit(f)
        self.assertEqual(result['statistics']['manual_review_locations'],1)

    def test_deterministic_readonly_and_saved_plan_guard(self):
        f=fixture('Elite Runner',r'精鋭\n走者','エリート 走者')
        snapshot=copy.deepcopy(f)
        first=audit(f)
        self.assertEqual(render_table(first),render_table(audit(f)))
        self.assertEqual(f,snapshot)
        p=plan(f)
        audit_blocked(f[0],f[1],f[2]['rows'],f[2],expected_plan={k:v for k,v in p.items() if k!='blocked'},expected_blocked=p['blocked'])
        with self.assertRaises(ValueError):
            audit_blocked(f[0],f[1],f[2]['rows'],f[2],expected_plan={})

    def test_cause_categories_and_token_parts(self):
        rows=[dict(matched_jp=r'<b>旧\n%s',effective_jp='新')]
        self.assertEqual(causes({'reasons':['technical_structure_changed']},rows),
                         ['layout_whitespace','markup_tag','placeholder'])
        for reason,category in [('expected_current_value_mismatch','expected_current_value'),
            ('source_hash_mismatch:path','source_hash'),('overlapping_span_conflict','overlap'),
            ('nonunique_or_missing_occurrence','nonunique_span'),('decision_signature_mismatch','other')]:
            self.assertEqual(causes({'reasons':[reason]},[]),[category])
        self.assertEqual(causes({'reasons':['nonunique_or_missing_occurrence']},[],True),['duplicate_id'])
        self.assertEqual(token_parts('<i><cost>%s')['placeholder'],['<cost>','%s'])

    def test_separate_occurrences_never_resolved_by_id(self):
        from dataclasses import replace
        f=fixture('Elite Runner',r'精鋭\n走者','エリート 走者')
        # Duplicate the exact source occurrence: cannot establish a unique value.
        entry=f[0]['de_jp'].entries['5001'][0]
        f[0]['de_jp'].entries['5001'].append(replace(entry))
        result=audit(f)
        self.assertFalse(result['auto_resolvable'])
        self.assertGreater(result['statistics']['cause_counts']['duplicate_id']['source_locations'],0)

    def test_cli_generates_only_audit_reports_and_refuses_overwrite(self):
        import contextlib
        import io
        import json
        from pathlib import Path
        import tempfile
        from unittest.mock import patch
        from tools.localization.__main__ import main
        from tools.localization.scope import render_audit
        from tools.localization.patch_plan import build_plan,read_audit
        f=fixture('Elite Runner',r'精鋭\n走者','エリート 走者')
        with tempfile.TemporaryDirectory(dir='reports') as temp:
            root=Path(temp); scope=root/'scope'; scope.mkdir(); saved=root/'plan'; saved.mkdir()
            ledger=root/'ledger.json'; ledger.write_text(json.dumps(f[1]),encoding='utf8')
            (scope/'scope-audit.tsv').write_text(render_audit(f[2]),encoding='utf8')
            (scope/'scope-metadata.json').write_text(json.dumps({k:v for k,v in f[2].items() if k!='rows'}),encoding='utf8')
            rows,meta,hashes=read_audit(scope)
            p=build_plan(f[0],f[1],rows,meta,hashes)
            (saved/'patch-plan.json').write_text(json.dumps({k:v for k,v in p.items() if k!='blocked'}),encoding='utf8')
            (saved/'blocked.json').write_text(json.dumps(p['blocked']),encoding='utf8')
            args=['blocked-audit','--scope-dir',str(scope),'--ledger',str(ledger),
                  '--plan-dir',str(saved),'--output-dir',str(root/'output')]
            protected={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch('tools.localization.__main__.load_datasets',return_value=f[0]),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(args),0)
                self.assertNotEqual(main(args),0)
            self.assertEqual({p.name for p in (root/'output').iterdir()},
                             {'blocked-audit.tsv','blocked-summary.md','auto-resolvable.json','manual-review.json'})
            from tools.localization.blocked_audit import json_artifacts
            expected=json_artifacts(audit(f))
            for path in (root/'output').glob('*.json'):
                with path.open(encoding='utf8') as stream:
                    actual=json.load(stream)
                # CLI includes byte hashes of the fixture input files.
                expected[path.name]['audit_artifact_hashes']=hashes
                self.assertEqual(actual,expected[path.name])
                self.assertTrue(path.read_bytes().isascii())
            self.assertTrue(all(p.read_bytes()==content for p,content in protected.items()))

    def test_17415_generated_artifact_round_trip(self):
        import json
        from pathlib import Path
        import tempfile
        from tools.localization.blocked_audit import json_artifacts,serialize_json,verify_json,load_json,render_manual_review
        from tools.localization.__main__ import write_report,main
        from unittest.mock import patch
        import contextlib
        import io
        f=fixture('Parthian Tactics','新参照','パルティアン戦術',compact=('17415',r'パルティア\n戦術'))
        result=audit(f)
        expected=json_artifacts(result)
        self.assertEqual([x['string_id'] for x in expected['manual-review.json']['locations']],['17415'])
        with tempfile.TemporaryDirectory(dir='reports') as temp:
            root=Path(temp)
            for name,obj in expected.items():
                path=root/name
                write_report(path,serialize_json(obj),Path('source'))
                # Integration assertion on the generated bytes, not on render output.
                with path.open(encoding='utf8') as stream: actual=json.load(stream)
                self.assertEqual(actual,obj)
                verify_json(path,obj)
                self.assertEqual(json.loads(path.read_bytes().decode('cp932')),obj)
            manual=load_json(root/'manual-review.json')
            request=manual['locations'][0]['requests'][0]
            self.assertEqual(request['current'],r'パルティア\n戦術')
            self.assertEqual(request['canonical'],'パルティアン戦術')
            self.assertIn('Parthian Tactics',render_manual_review(manual))
            out=io.StringIO()
            with patch('tools.localization.__main__.load_datasets',side_effect=AssertionError('Must only read artifact')),contextlib.redirect_stdout(out):
                self.assertEqual(main(['blocked-review','--input',str(root/'manual-review.json')]),0)
            self.assertIn(r'パルティア\n戦術',out.getvalue())
            # Reproduce the user's exact default-decoding path on Windows PS 5.1.
            import shutil
            import subprocess
            powershell=shutil.which('powershell.exe')
            if powershell:
                literal=str((root/'manual-review.json').resolve()).replace("'","''")
                script="$ErrorActionPreference='Stop'; $x=Get-Content -Raw -LiteralPath '"+literal+"' | ConvertFrom-Json; [string]::Join(',', [int[]][char[]]$x.locations[0].requests[0].canonical)"
                check=subprocess.run([powershell,'-NoProfile','-NonInteractive','-Command',script],capture_output=True,text=True)
                self.assertEqual(check.returncode,0,check.stderr)
                self.assertEqual(check.stdout.strip(),','.join(str(ord(c)) for c in 'パルティアン戦術'))

    def test_unicode_json_serialization_and_corruption_detection(self):
        import json
        from pathlib import Path
        import tempfile
        from tools.localization.blocked_audit import serialize_json,verify_json,load_json
        value={'日本語':'パルティアン戦術「引用」"\\n\n\t\r\\😀','nested':['射手育成所','神殿']}
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'artifact.json'
            path.write_text(serialize_json(value),encoding='utf8')
            with path.open(encoding='utf8') as stream: self.assertEqual(json.load(stream),value)
            verify_json(path,value)
            with self.assertRaises(ValueError): verify_json(path,{'different':'値'})
            for broken in ['{"current": "unterminated}', '{"x":NaN}', '{"x":1,"x":2}']:
                path.write_text(broken,encoding='utf8')
                with self.assertRaises(ValueError): load_json(path)
        with self.assertRaises(ValueError): serialize_json({'x':float('nan')})

    def test_local_artifacts_integration_when_sources_available(self):
        import json
        from pathlib import Path
        import tempfile
        from tools.localization.analysis import load_datasets
        from tools.localization.human_reviews import load_ledger,DEFAULT_LEDGER
        from tools.localization.patch_plan import read_audit
        from tools.localization.blocked_audit import json_artifacts,serialize_json,verify_json
        from tools.localization.__main__ import write_report
        from tests.local_pipeline import inputs
        item=inputs()
        result=audit_blocked(*(item[k] for k in ('data','ledger','rows','meta','hashes')))
        artifacts=json_artifacts(result)
        manual=artifacts['manual-review.json']['locations']
        self.assertEqual({x['string_id'] for x in manual},{'14130','14169','14452','14456','14457','14573',
            '17074','17081','17375','17381','17384','17393','17415'})
        self.assertEqual(len(manual),13)
        self.assertEqual(sum(x['candidate_count'] for x in manual),21)
        row=next(x for x in manual if x['string_id']=='17415')['requests'][0]
        self.assertEqual(row['current'],r'パルティア\n戦術')
        self.assertEqual(row['canonical'],'パルティアン戦術')
        with tempfile.TemporaryDirectory(dir='reports') as temp:
            for name,obj in artifacts.items():
                path=Path(temp)/name
                write_report(path,serialize_json(obj),Path('source'))
                with path.open(encoding='utf8') as stream: self.assertEqual(json.load(stream),obj)
                verify_json(path,obj)
