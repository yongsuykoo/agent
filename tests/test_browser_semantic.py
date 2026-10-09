"""Semantic browser state participates in approval, replay and result proof."""
import copy
import unittest
from unittest.mock import Mock
from app_agent.browser import Browser,browser_request
from app_agent.browser_semantic_checks import TEXT,EXPECTED
from app_agent.runner import reconcile_action,result_matches,validate_action
from app_agent.workflow_replay import guard
from test_browser import Adapter,control


class SemanticControlsTests(unittest.TestCase):
    def setUp(self):
        self.editor=control(7,'Draft','Edit',['type'],value='Old draft',state={'editor':{'safe':True,'markup':'<p>Old <b>draft</b></p>'},'role':'textbox'})
        self.switch=control(8,'Confirmed','CheckBox',['toggle'],state={'role':'switch','checked':'false','toggle':'off'})
        self.tab=control(9,'Review','TabItem',['click'],state={'role':'tab','selected':'false'})
        self.snapshot={**Adapter().start('https://example.com').observe(),'controls':[self.editor,self.switch,self.tab]}
    def test_multiline_literal_entry_validates_but_is_not_completion_evidence(self):
        action={'kind':'type','text':TEXT,'target':7,'target_name':'Draft','automation_id':'dom:7','reason':'Replace the draft.'}
        self.assertEqual(validate_action(action,self.snapshot,True)['text'],TEXT)
        self.editor['value']=EXPECTED
        self.assertFalse(result_matches(self.snapshot,EXPECTED,result_control_id='page:output'))
    def test_markup_toggle_and_tab_changes_invalidate_approval_and_recipe(self):
        for index,key,value in [(0,'editor',{'safe':True,'markup':'<p>Old <i>draft</i></p>'}),(1,'checked','true'),(2,'selected','true')]:
            with self.subTest(index=index):
                after=copy.deepcopy(self.snapshot);after['controls'][index]['state'][key]=value
                action={'kind':'type' if index==0 else 'toggle' if index==1 else 'click','target':self.snapshot['controls'][index]['id'],'text':'New','state':'on'}
                self.assertIsNone(reconcile_action(action,self.snapshot,after));self.assertNotEqual(guard(self.snapshot),guard(after))
    def test_readonly_or_unavailable_rich_editor_rejected_before_dispatch(self):
        self.editor['actions']=[];browser=Browser(check_url=lambda u:None);browser.controls={7:self.editor};browser.evaluate=Mock()
        with self.assertRaises(ValueError):browser.act({'kind':'type','target':7,'text':'Do not edit'})
        browser.evaluate.assert_not_called()
    def test_switch_requires_explicit_binary_intent(self):
        browser=Browser(check_url=lambda u:None);browser.controls={8:self.switch};browser.evaluate=Mock()
        for state in [None,'mixed',True,'true']:
            with self.subTest(state=state),self.assertRaises(ValueError):browser.act({'kind':'toggle','target':8,'state':state})
        browser.evaluate.assert_not_called()
    def test_tab_label_is_not_rendered_result_proof(self):
        self.tab['name']=EXPECTED;self.tab['state']['selected']='true'
        self.assertFalse(result_matches(self.snapshot,EXPECTED,result_control_id='page:output'))
    def test_semantic_goal_uses_public_task_grammar(self):
        task=f'Open "https://example.com" in a browser and replace Draft and verify exactly: "{EXPECTED}"'
        self.assertEqual(browser_request(task)['expected_result'],EXPECTED)


if __name__=='__main__':unittest.main()
