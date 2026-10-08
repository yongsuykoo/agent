import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch
from app_agent.catalog import Catalog
from app_agent.runner import TaskRunner
from app_agent.task_director import TaskDirector
from app_agent.workflow_replay import guard
from app_agent.research import DeferredCloud
from test_catalog import app,snapshot
from test_task_director import Desktop,Cloud


class ReplayTests(unittest.TestCase):
    def learned(self, directory):
        desktop=Desktop(True);cloud=Cloud()
        record=TaskRunner(desktop,cloud,lambda *args:True,lambda text:None,directory).run(
            'Calculate 23 plus 19 and verify 42.',required_result_text='42',result_control_id='CalculatorResults')
        self.assertEqual(record['outcome'],'result_observed')
        self.assertIsNotNone(record['replay_recipe'])
        return json.loads(json.dumps(record['replay_recipe']))

    def test_repeated_verified_workflow_executes_with_zero_model_calls_and_fresh_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            recipe=self.learned(directory);desktop=Desktop(True);cloud=Mock()
            result=TaskRunner(desktop,cloud,lambda *args:True,lambda text:None,directory).run(recipe['task'],
                previous_workflows=[{'recipe':recipe}],required_result_text='42',result_control_id='CalculatorResults')
            cloud.request.assert_not_called();self.assertEqual(result['outcome'],'result_observed')
            self.assertEqual(result['execution_mode'],'local_replay');self.assertEqual(len(desktop.actions),1)

    def test_changed_initial_data_never_blindly_replays_and_calls_planner(self):
        with tempfile.TemporaryDirectory() as directory:
            recipe=self.learned(directory);desktop=Desktop(True);desktop.value='5'
            cloud=Mock(wraps=Cloud())
            result=TaskRunner(desktop,cloud,lambda *args:True,lambda text:None,directory).run(recipe['task'],
                previous_workflows=[{'recipe':recipe}],required_result_text='42',result_control_id='CalculatorResults')
            self.assertGreater(cloud.request.call_count,0);self.assertEqual(result['execution_mode'],'cloud')

    def test_permission_denial_and_process_change_prevent_replay_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            recipe=self.learned(directory)
            for process_change in (False,True):
                desktop=Desktop(True);cloud=Mock(wraps=Cloud())
                def permit(action, observation):
                    if process_change:
                        original=desktop.observe
                        desktop.observe=lambda:{**original(),'process_id':99}
                        return True
                    return False
                result=TaskRunner(desktop,cloud,permit,lambda text:None,directory).run(recipe['task'],max_steps=16,
                    previous_workflows=[{'recipe':recipe}],required_result_text='42',result_control_id='CalculatorResults')
                self.assertEqual(desktop.actions,[])
                self.assertEqual(result['outcome'],'blocked' if process_change else 'cancelled')
                cloud.request.assert_not_called()

    def test_wrong_postcondition_returns_to_cloud_without_claiming_success(self):
        with tempfile.TemporaryDirectory() as directory:
            recipe=self.learned(directory);desktop=Desktop(True)
            desktop.act=lambda action:setattr(desktop,'value','145')
            cloud=Mock(wraps=Cloud())
            result=TaskRunner(desktop,cloud,lambda *args:True,lambda text:None,directory).run(recipe['task'],max_steps=1,
                previous_workflows=[{'recipe':recipe}],required_result_text='42',result_control_id='CalculatorResults',effect_timeout=0)
            self.assertNotEqual(result['outcome'],'result_observed');self.assertEqual(result['execution_mode'],'mixed')

    def test_verified_multi_app_plan_and_workflows_repeat_with_no_cloud_calls_then_invalidate_after_update(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog=Catalog(directory);editor={**app(identity='start:editor'),'name':'Editor','aliases':['Editor']}
            catalog.sync(snapshot([app(),editor]));task='Calculate 23 plus 19 and put the result in Editor.'
            cloud=Mock(wraps=Cloud());desktops={app()['id']:Desktop(True),editor['id']:Desktop()}
            resolve=lambda selected,cancel:desktops[selected['id']]
            with patch('app_agent.task_director.ensure_blueprint',side_effect=RuntimeError('No manual')):
                first=TaskDirector(catalog,cloud,lambda *args:True,lambda text:None,directory,resolve=resolve).run(task)
                first_calls=cloud.request.call_count
                desktops={app()['id']:Desktop(True),editor['id']:Desktop()};cloud.reset_mock()
                unavailable=Mock(side_effect=RuntimeError('No provider credential configured'))
                second=TaskDirector(catalog,DeferredCloud(unavailable),lambda *args:True,lambda text:None,directory,resolve=resolve).run(task)
                cloud.request.assert_not_called()
                unavailable.assert_not_called()
                self.assertEqual(second['outcome'],'steps_verified');self.assertEqual(first_calls,5)
                catalog.sync(snapshot([app(version='2'),editor]));cloud.reset_mock()
                TaskDirector(catalog,cloud,lambda *args:True,lambda text:None,directory,resolve=resolve).run(task)
                self.assertGreater(cloud.request.call_count,0)
            catalog.close()

    def test_numeric_output_verification_does_not_accept_substring_matches(self):
        from app_agent.runner import result_matches
        desktop=Desktop(True);desktop.value='142'
        self.assertFalse(result_matches(desktop.observe(),'42'))
