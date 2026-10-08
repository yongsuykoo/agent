import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from app_agent.catalog import Catalog
from app_agent.task_director import TaskDirector, task_plan, task_blueprint, resolve_window, arithmetic_result
from test_catalog import app, snapshot


def reply(value):
    return {'output':[{'content':[{'type':'output_text','text':json.dumps(value)}]}]}


PLAN={'steps':[{'app_id':'start:calculator','task':'Calculate 23 plus 19 and verify 42.','expected_result':'42'},
               {'app_id':'start:editor','task':'Replace the document text with exactly: {{result:1}}','expected_result':'{{result:1}}'}]}


class Desktop:
    def __init__(self, calculator=False):
        self.calculator=calculator;self.value='0' if calculator else '';self.actions=[]
    def observe(self):
        return {'window':'Calculator' if self.calculator else 'Untitled - Editor','window_handle':1 if self.calculator else 2,'process_id':11 if self.calculator else 22,
                'controls':[{'id':1,'name':'Calculate' if self.calculator else 'Text Editor','type':'Button' if self.calculator else 'Edit',
                  'class_name':'Button' if self.calculator else 'Edit','automation_id':'compute' if self.calculator else 'editor','actions':['invoke'] if self.calculator else ['type'],
                  'visible':True,'enabled':True,'value':'' if self.calculator else self.value},
                 {'id':2,'name':'Display is '+self.value,'type':'Text','automation_id':'CalculatorResults','visible':True,'enabled':True,'value':''}]}
    def act(self, action):
        self.actions.append(action);self.value='42' if self.calculator else action['text']


class Cloud:
    def request(self, **payload):
        if payload['text']['format'].get('name')=='personal_task_plan':return reply(PLAN)
        data=json.loads(payload['input']);obs=data['observation'];editor=data['required_exact_editor_text']
        target=obs['controls'][0]
        complete=target['value']==editor if editor is not None else obs['controls'][1]['name']=='Display is 42'
        action={'kind':'finish','reason':'Observed output','expected_text':'42'} if complete else {
            'kind':'type' if editor is not None else 'invoke','reason':'Perform requested step','target':1,
            'automation_id':target['automation_id'],'target_name':target['name'],'text':editor}
        return reply(action)


class TaskDirectorTests(unittest.TestCase):
    def test_real_runner_chains_verified_calculator_output_to_editor_and_saves_both_workflows(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog=Catalog(directory);editor={**app(identity='start:editor'),'name':'Editor','aliases':['Editor']};catalog.sync(snapshot([app(),editor]))
            calculator,document=Desktop(True),Desktop()
            with patch('app_agent.task_director.ensure_blueprint',side_effect=RuntimeError('Manual unavailable')):
                result=TaskDirector(catalog,Cloud(),lambda action,obs:True,lambda text:None,directory,
                    resolve=lambda selected,cancel:calculator if selected['id']=='start:calculator' else document).run('Calculate 23 plus 19 and put the result in Editor.')
            self.assertEqual(result['outcome'],'steps_verified');self.assertEqual(document.value,'42')
            self.assertEqual(len(calculator.actions),1);self.assertEqual(len(document.actions),1)
            self.assertEqual(len(catalog.workflows('start:editor',1)),1)
            self.assertEqual(catalog.interface('start:editor',1)['controls'][0]['value'],'42')
            self.assertIsNone(catalog.get('start:editor')['blueprint'])
            self.assertEqual(json.loads((Path(directory)/'objective-sessions.jsonl').read_text())['outcome'],'steps_verified')
            catalog.close()

    def test_missing_documentation_does_not_disable_observable_operations_or_claim_documented_knowledge(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog=Catalog(directory);catalog.sync(snapshot([app()]));selected=catalog.get(app()['id'])
            with patch('app_agent.task_director.ensure_blueprint',side_effect=RuntimeError('Manual unavailable')):
                result=task_blueprint(catalog,selected,Mock(),lambda text:None,threading.Event(),Desktop().observe())
            self.assertEqual(result['capabilities'],[]);self.assertIsNone(catalog.get(selected['id'])['blueprint'])
            self.assertTrue(result['observed_interface_profile']);catalog.close()

    def test_credentials_failure_still_stops_before_operating(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog=Catalog(directory);catalog.sync(snapshot([app()]));selected=catalog.get(app()['id'])
            with patch('app_agent.task_director.ensure_blueprint',side_effect=RuntimeError('HTTP 401')):
                with self.assertRaisesRegex(RuntimeError,'401'):
                    task_blueprint(catalog,selected,Mock(),lambda text:None,threading.Event(),Desktop().observe())
            catalog.close()

    def test_future_result_and_wrong_arithmetic_are_rejected_before_execution(self):
        apps=[app(),{**app(identity='start:editor'),'name':'Editor'}]
        for changes in ({'task':'Calculate 23 plus 19','expected_result':'41'}, {'task':'Type exactly: {{result:2}}'}):
            plan=json.loads(json.dumps(PLAN));plan['steps'][0].update(changes)
            cloud=Mock();cloud.request.return_value=reply(plan)
            with self.assertRaises(ValueError):task_plan('Calculate 23 plus 19.',apps,cloud)

    def test_failed_first_step_never_reaches_another_app(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog=Catalog(directory);catalog.sync(snapshot([app(),{**app(identity='start:editor'),'name':'Editor'}]))
            resolver=Mock(return_value=Desktop(True));runner=Mock();runner.return_value.run.return_value={'outcome':'blocked','history':[],'actions_executed':0}
            with patch('app_agent.task_director.ensure_blueprint',return_value={}):
                result=TaskDirector(catalog,Cloud(),lambda *a:True,lambda text:None,directory,resolve=resolver,runner=runner).run('Calculate 23 plus 19 and write result in Editor.')
            self.assertEqual(result['outcome'],'blocked');self.assertEqual(resolver.call_count,1);self.assertEqual(result['verified_results'],[]);catalog.close()

    def test_ambiguous_existing_documents_choose_only_a_new_window(self):
        desktop=Mock();desktop.windows.side_effect=[[(1,'A - Editor'),(2,'B - Editor')],[(1,'A - Editor'),(2,'B - Editor'),(3,'Untitled - Editor')]]
        launch=Mock();resolve_window({'name':'Editor','aliases':['Editor']},threading.Event(),desktop=desktop,launch=launch,timeout=0)
        desktop.assert_called_once_with(3);launch.assert_called_once()

    def test_arithmetic_verification_uses_decimal_without_evaluating_commands(self):
        self.assertEqual(arithmetic_result('Calculate 0.1 plus 0.2'),'0.3')
        self.assertEqual(arithmetic_result('Calculate 17 plus 28'),'45')
        self.assertIsNone(arithmetic_result('Run Python to add values'))

    def test_unrelated_plan_cannot_replace_requested_calculation(self):
        cloud=Mock();cloud.request.return_value=reply({'steps':[{'app_id':app()['id'],
            'task':'Inspect window title','expected_result':'Calculator'}]})
        with self.assertRaisesRegex(ValueError,'omitted'):
            task_plan('Calculate 23 plus 19.',[app()],cloud)

    def test_failed_workflow_gets_one_documented_recovery_and_retains_failure_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog=Catalog(directory);catalog.sync(snapshot([app()]))
            cloud=Mock();cloud.request.return_value=reply({'steps':[PLAN['steps'][0]]})
            failed={'task':'Calculate','outcome':'verification_failed','history':[],'actions_executed':0}
            success={'task':'Calculate','outcome':'result_observed','history':[],'actions_executed':1}
            runner=Mock();runner.return_value.run.side_effect=[failed,success]
            with patch('app_agent.task_director.ensure_blueprint',return_value={}), \
                 patch('app_agent.task_director.research_app',return_value={'name':'Calculator','capabilities':[]}) as research:
                result=TaskDirector(catalog,cloud,lambda *args:True,lambda text:None,directory,
                    resolve=lambda *args:Desktop(True),runner=runner).run('Calculate 23 plus 19.')
            self.assertEqual(result['outcome'],'steps_verified')
            self.assertEqual([s['record']['outcome'] for s in result['steps']],['verification_failed','result_observed'])
            research.assert_called_once();self.assertEqual(runner.return_value.run.call_count,2)
            catalog.close()

    def test_process_change_blocks_before_any_desktop_action(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog=Catalog(directory);catalog.sync(snapshot([app()]))
            cloud=Mock();cloud.request.return_value=reply({'steps':[PLAN['steps'][0]]})
            desktop=Mock();initial=Desktop(True).observe();changed={**initial,'process_id':99}
            desktop.observe.side_effect=[initial,changed];runner=Mock()
            with patch('app_agent.task_director.ensure_blueprint',return_value={}):
                result=TaskDirector(catalog,cloud,lambda *args:True,lambda text:None,directory,
                    resolve=lambda *args:desktop,runner=runner).run('Calculate 23 plus 19.')
            self.assertEqual(result['outcome'],'error');runner.assert_not_called();desktop.act.assert_not_called()
            catalog.close()
