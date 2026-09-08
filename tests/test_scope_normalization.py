"""Small, constructed display strings; source values remain lossless."""
import copy
import unittest

from tests.test_gameplay import synthetic, add, RULES
from tests.test_human_reviews import ledger
from tools.localization.gameplay import build_inventory
from tools.localization.scope import layout_key, comparison_fields, build_scope
from tools.localization.duplicate_audit import audit_duplicates


class NormalizedScopeTests(unittest.TestCase):
    def test_layout_keys_preserve_nonlayout_syntax(self):
        self.assertEqual(layout_key(r'チュートン\nナイト'),layout_key('チュートン ナイト'))
        self.assertEqual(layout_key(r'射手\n育成所'),layout_key('射手育成所'))
        self.assertEqual(layout_key('射手\n\t育成所'),layout_key('射手育成所'))
        self.assertNotEqual(layout_key(r'射手\\n育成所'),layout_key('射手育成所'))
        self.assertNotEqual(layout_key('<b>射手育成所'),layout_key('射手育成所'))
        self.assertNotEqual(layout_key('Ａ'),layout_key('A'))
        self.assertEqual(layout_key(r'%s\q'),r'%s\q')

    def test_literal_and_normalized_results_are_separate(self):
        result=comparison_fields(r'射手\n育成所','射手育成所')
        self.assertFalse(result['literal_stored_value_equal'])
        self.assertTrue(result['normalized_equal'])
        self.assertTrue(result['normalized_equivalent'])
        self.assertIsNone(comparison_fields(None,'射手育成所')['normalized_equal'])

    def test_named_display_regressions(self):
        cases=[('Crossbowman','石弓兵','石弓射手',r'石弓\n射手'),
               ('Longbowman','ロングボウ兵','ロングボウ',r'ロング\nボウ'),
               ('Teutonic Knight','チュートン騎士','チュートン ナイト',r'チュートン\nナイト'),
               ('Archery Range','弓兵育成所','射手育成所',r'射手\n育成所')]
        for en,current,canonical,display in cases:
            with self.subTest(name=en):
                data=synthetic()
                for n,text in [('de_en',en),('hd_en',en),('de_jp',current),('hd_jp',canonical),('aok_jp',canonical)]:
                    data[n].entries['5001']=[]; add(data,n,'5001',text)
                data['de_en'].entries['26001']=[]
                add(data,'de_en','26001',f'Create <b>{en}<b> (<cost>)\\nSynthetic unit.')
                add(data,'de_en','14001',en)
                add(data,'de_jp','14001',display)
                inv=build_inventory(data,RULES); human=ledger(data,['5001'],decision='restore',jp=canonical)
                before=copy.deepcopy(data)
                report=build_scope(data,human,inv)
                r=next(r for r in report['rows'] if r['related_string_id']=='14001' and r['related_type']=='name')
                self.assertEqual(r['literal_scope_class'],'required')
                self.assertEqual(r['scope_class'],'already_consistent')
                self.assertFalse(r['change_candidate'])
                self.assertEqual(r['matched_jp'],display)
                self.assertEqual(data,before)

    def test_keep_de_royal_janissary_still_requires_help_consistency(self):
        data=synthetic()
        for n,text in [('de_en','Royal Janissary'),('hd_en','Royal Janissary'),('de_jp','近衛イェニチェリ')]:
            data[n].entries['5001']=[]; add(data,n,'5001',text)
        data['de_en'].entries['26001']=[]; data['de_jp'].entries['26001']=[]
        add(data,'de_en','26001',r'Create <b>Royal Janissary<b> (<cost>)\nSynthetic unit.')
        add(data,'de_jp','26001',r'<b>王家のイェニチェリ<b>の作成')
        human=ledger(data,['5001'],decision='keep_de',jp='近衛イェニチェリ')
        report=build_scope(data,human,build_inventory(data,RULES))
        r=next(r for r in report['rows'] if r['related_string_id']=='26001')
        self.assertEqual(r['scope_class'],'required')
        self.assertEqual(r['effective_decision'],'keep_de')
        self.assertEqual(r['effective_jp'],'近衛イェニチェリ')
        self.assertFalse(r['normalized_equal'])

    def test_duplicate_value_and_provenance_axes_and_no_resolution(self):
        data=synthetic()
        add(data,'de_jp','9001','同値','one.txt'); add(data,'de_jp','9001','同値','two.txt')
        add(data,'de_jp','9002','甲','one.txt'); add(data,'de_jp','9002','乙','two.txt')
        add(data,'de_jp','9003','同じ位置','one.txt'); add(data,'de_jp','9003','同じ位置','one.txt')
        result=audit_duplicates(data)
        self.assertEqual(result['total'],3)
        self.assertEqual(result['value_counts']['same_value_safe'],2)
        self.assertEqual(result['value_counts']['different_values'],1)
        self.assertEqual(result['provenance_counts']['cross_file'],2)
        self.assertEqual(result['provenance_counts']['repeated_same_location'],1)
        self.assertIsNone(data['de_jp'].resolved('9001'))
        self.assertEqual(len(result['rows'][0]['occurrences']),2)
        data['de_jp'].invalid_ids.add('9003')
        self.assertEqual(audit_duplicates(data)['value_counts']['other_invalid'],1)


if __name__=='__main__': unittest.main()
