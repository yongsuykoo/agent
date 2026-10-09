"""Selection validation and live context reconciliation; real DOM tests are smoke checks."""
import copy
import unittest
from unittest.mock import Mock
from app_agent.browser import Browser
from app_agent.runner import validate_action,reconcile_action,result_matches
from app_agent.workflow_replay import guard
from test_browser import Adapter,control


class NestedControlsTests(unittest.TestCase):
    def setUp(self):
        self.target=control(7,'Delivery','ComboBox',['select'],value='standard',state={
            'context':{'url':'https://example.com/embedded','path':[{'kind':'frame','host':2,'url':'https://example.com/embedded'}]},
            'options':[{'value':'standard','label':'Standard','enabled':True,'selected':True},
                       {'value':'express','label':'Express 世界','enabled':True,'selected':False},
                       {'value':'blocked','label':'Unavailable','enabled':False,'selected':False}]})
        self.target['automation_id']='dom:7'
        self.snapshot={**Adapter().start('https://example.com').observe(),'controls':[control(0,'Page','Window'),self.target]}
        self.action={'kind':'select','target':7,'automation_id':'dom:7','target_name':'Delivery','text':'express','reason':'Choose the exact advertised value.'}
    def test_enabled_exact_option_value_validates_and_reconciles(self):
        self.assertEqual(validate_action(self.action,self.snapshot,True)['text'],'express')
        self.assertEqual(reconcile_action(self.action,self.snapshot,copy.deepcopy(self.snapshot))['target'],7)
    def test_label_disabled_unknown_or_unbounded_option_is_not_a_selection(self):
        for value in ('Express 世界','blocked','missing',None,2,'x'*2001):
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'option value'):
                validate_action({**self.action,'text':value},self.snapshot,True)
    def test_duplicate_values_cannot_disambiguate_by_numeric_index_or_label(self):
        self.target['state']['options'].append({'value':'express','label':'Another','enabled':True,'selected':False})
        with self.assertRaises(ValueError):validate_action(self.action,self.snapshot,True)
    def test_changed_option_label_enablement_selection_and_context_cancel_approval(self):
        variants=[]
        for key,value in (('label','Changed'),('enabled',False),('selected',True)):
            after=copy.deepcopy(self.snapshot);after['controls'][1]['state']['options'][1][key]=value;variants.append(after)
        after=copy.deepcopy(self.snapshot);after['controls'][1]['state']['context']['path'][0]['url']='https://example.com/replaced';variants.append(after)
        after=copy.deepcopy(self.snapshot);after['controls'][1]['value']='express';variants.append(after)
        after=copy.deepcopy(self.snapshot);after['controls'][1]['actions']=[];variants.append(after)
        for after in variants:
            with self.subTest(after=after):
                self.assertIsNone(reconcile_action(self.action,self.snapshot,after))
                if after['controls'][1]['actions']:self.assertNotEqual(guard(self.snapshot),guard(after))
    def test_browser_rejects_unknown_or_disabled_choices_before_evaluation(self):
        browser=Browser(check_url=lambda url:None);browser.controls={7:self.target};browser.evaluate=Mock();browser.url='https://example.com'
        for value in ('blocked','missing',None):
            with self.assertRaises(ValueError):browser.act({'kind':'select','target':7,'text':value})
        browser.evaluate.assert_not_called()
        browser.evaluate.return_value=True;browser.act({'kind':'select','target':7,'text':'express'});browser.evaluate.assert_called_once()
    def test_dropdown_value_and_label_do_not_prove_saved_output(self):
        self.target['value']='Saved: Hello';self.target['name']='Saved: Hello'
        self.assertFalse(result_matches(self.snapshot,'Saved: Hello',result_control_id='page:output'))
    def test_desktop_selection_item_without_text_preserves_existing_contract(self):
        desktop={**self.snapshot,'url':None,'controls':[control(8,'List row','ListItem',['select'])]}
        action={'kind':'select','target':8,'automation_id':'dom:8','target_name':'List row','reason':'Select the accessible desktop row.'}
        self.assertEqual(validate_action(action,desktop,True)['target'],8)


if __name__=='__main__':unittest.main()
