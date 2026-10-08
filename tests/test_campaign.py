import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from app_agent.catalog import Catalog
from app_agent.campaign import prepare_next_experiment, practice_one, study_campaign
from app_agent.app_practice import create_grant, grants_action
from test_catalog import app, snapshot
from test_runner import FakeCloud, FakeDesktop


def blueprint():
    return {"capabilities": [{"name": "Add", "steps": ["Use addition"], "expected_result": "Sum"},
                              {"name": "Subtract", "steps": ["Use subtraction"], "expected_result": "Difference"}]}


def plan(capability="Add"):
    return {"task": "Calculate and verify 42", "expected_result": "42", "capability_name": capability, "risk": "disposable"}


class Planner:
    def __init__(self):
        self.calls = []
    def request(self, **payload):
        request = json.loads(payload["input"])
        self.calls.append(request)
        name = request["blueprint"]["capabilities"][0]["name"]
        return {"output": [{"content": [{"type": "output_text", "text": json.dumps(plan(name))}]}]}


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.catalog = Catalog(self.directory.name)
        self.apps = [app(identity="a"), {**app(identity="b"), "name": "Editor"}]
        self.catalog.sync(snapshot(self.apps))
    def tearDown(self):
        self.catalog.close()
        self.directory.cleanup()
    def document(self):
        for current in self.catalog.apps():
            self.catalog.save_blueprint(current["id"], current["generation"], blueprint())
    def run_campaign(self, cloud=None, **kwargs):
        return study_campaign(self.catalog, cloud or Planner(), lambda text: None, **kwargs)

    def test_researching_all_apps_does_not_claim_tested_capabilities(self):
        with patch("app_agent.learning.research_app", return_value=blueprint()):
            report = self.run_campaign(max_apps=5, max_plans=2)
        self.assertTrue(report["overview"]["initial_documentation_complete"])
        self.assertEqual(report["overview"]["apps_documented"], 2)
        self.assertEqual(report["overview"]["documented_capabilities"], 4)
        self.assertEqual(report["overview"]["capabilities_tested_once"], 0)
        self.assertEqual(report["overview"]["capabilities_without_observed_test"], 4)
        self.assertEqual(report["overview"]["experiments_ready"], 2)
        saved = json.loads((Path(self.directory.name) / "learning-report.json").read_text())
        self.assertEqual(saved, self.catalog.setting("campaign_state"))

    def test_daily_research_budget_survives_restart(self):
        with patch("app_agent.learning.research_app", return_value=blueprint()) as research:
            self.run_campaign(daily_limit=1, max_apps=5, max_plans=0)
            self.catalog.close()
            self.catalog = Catalog(self.directory.name)
            result = self.run_campaign(daily_limit=1, max_apps=5, max_plans=0)
            self.assertEqual(research.call_count, 1)
        self.assertEqual(result["status"], "daily_limit")
        self.assertEqual(result["overview"]["apps_queued"], 1)

    def test_auth_failure_stops_batch_and_throttles_retry(self):
        with patch("app_agent.learning.research_app", side_effect=RuntimeError("Cloud request failed (HTTP 401)")) as research:
            result = self.run_campaign(max_apps=5, research_workers=1)
            self.assertEqual(result["status"], "cloud_blocked")
            retry = self.run_campaign(max_apps=5)
            self.assertEqual(retry["status"], "waiting_for_cloud_retry")
            self.assertEqual(research.call_count, 1)
        self.assertEqual(self.catalog.setting("research_budget")["used"], 1)

    def test_experiments_are_balanced_between_apps_and_planning_is_bounded(self):
        self.document()
        planner = Planner()
        self.run_campaign(planner, daily_limit=2, max_apps=0, max_plans=5)
        self.assertEqual(len(planner.calls), 2)
        self.assertEqual(self.catalog.setting("planning_budget")["used"], 2)
        for current in self.catalog.apps():
            self.assertIsNotNone(self.catalog.ready_practice_plan(current["id"], current["generation"]))
        self.run_campaign(planner, daily_limit=2, max_apps=0, max_plans=5)
        self.assertEqual(len(planner.calls), 2)

    def test_ready_plan_survives_restart_and_lease_prevents_duplicate_claim(self):
        self.document()
        self.catalog.save_practice_plan("a", 1, plan())
        self.catalog.close()
        self.catalog = Catalog(self.directory.name)
        self.assertEqual(self.catalog.ready_practice_plan("a", 1), plan())
        self.assertTrue(self.catalog.claim_practice_plan("a", 1, "Add"))
        self.assertFalse(self.catalog.save_practice_plan("a", 1, plan()))
        self.assertFalse(self.catalog.defer_practice_plan("a", 1, "Add", "Concurrent planning failure"))
        self.assertEqual(self.catalog.practice_plan("a", 1, "Add")["status"], "running")
        self.assertFalse(self.catalog.claim_practice_plan("a", 1, "Add"))
        self.assertIsNone(self.catalog.ready_practice_plan("a", 1))
        with self.catalog.db:
            self.catalog.db.execute("UPDATE practice_plans SET retry_at='2000-01-01T00:00:00+00:00'")
        self.assertEqual(self.catalog.ready_practice_plan("a", 1), plan())
        self.assertTrue(self.catalog.claim_practice_plan("a", 1, "Add"))
        self.assertEqual(self.catalog.practice_plan("a", 1, "Add")["attempts"], 2)

    def test_removed_app_cannot_prepare_or_claim_experiments(self):
        self.document()
        self.catalog.save_practice_plan("a", 1, plan())
        self.catalog.sync(snapshot([self.apps[1]]))
        self.assertFalse(self.catalog.save_practice_plan("a", 1, plan()))
        self.assertFalse(self.catalog.claim_practice_plan("a", 1, "Add"))
        self.assertIsNone(self.catalog.ready_practice_plan("a", 1))

    def test_app_update_invalidates_old_plans_and_counts(self):
        self.document()
        self.catalog.save_practice_plan("a", 1, plan())
        self.catalog.sync(snapshot([app(version="2", identity="a"), self.apps[1]]))
        self.assertIsNone(self.catalog.ready_practice_plan("a", 1))
        self.assertFalse(self.catalog.claim_practice_plan("a", 1, "Add"))
        self.assertFalse(self.catalog.save_practice_plan("a", 1, plan()))
        self.assertEqual(self.catalog.learning_overview()["experiments_ready"], 0)
        self.assertEqual(self.catalog.get("a")["status"], "queued")

    def test_unsupported_capability_is_deferred_and_next_capability_is_selected(self):
        self.document()
        cloud = Mock()
        cloud.request.return_value = {"output": [{"content": [{"type": "output_text", "text": '{"risk":"unsupported"}'}]}]}
        result = prepare_next_experiment(self.catalog, self.catalog.get("a"), cloud, lambda text: None)
        self.assertEqual(result["status"], "experiment_deferred")
        self.assertEqual(self.catalog.next_practice_capability("a", 1), "Subtract")
        self.assertEqual(self.catalog.practice_plan("a", 1, "Add")["status"], "deferred")

    def test_cancellation_during_planning_saves_no_plan(self):
        self.document()
        cancel = threading.Event()
        planner = Planner()
        original = planner.request
        def request(**payload):
            result = original(**payload)
            cancel.set()
            return result
        planner.request = request
        result = prepare_next_experiment(self.catalog, self.catalog.get("a"), planner, lambda text: None, cancel=cancel)
        self.assertEqual(result["status"], "cancelled")
        self.assertIsNone(self.catalog.practice_plan("a", 1, "Add"))

    def test_granted_experiment_executes_and_does_not_stop_learning_other_capabilities(self):
        self.document()
        self.catalog.save_practice_plan("a", 1, plan())
        cloud = FakeCloud([{"kind": "invoke", "target": 1, "reason": "Calculate"},
                           {"kind": "finish", "expected_text": "42", "reason": "Verify"}])
        result = practice_one(self.catalog, self.catalog.get("a"), cloud, FakeDesktop(), lambda a, o: True,
                              lambda text: None, self.directory.name)
        self.assertEqual(result["status"], "experiment_observed")
        self.assertEqual(result["actions_executed"], 1)
        self.assertEqual(self.catalog.coverage("a", 1)[0]["observed_runs"], 1)
        self.assertEqual(self.catalog.next_practice_capability("a", 1), "Subtract")
        self.assertEqual(self.catalog.learning_overview()["capabilities_tested_repeatedly"], 0)
        self.assertEqual(len(self.catalog.workflows("a", 1)), 1)

    def test_unfamiliar_editor_uses_documentation_and_grant_without_a_demonstration(self):
        self.catalog.save_blueprint("b", 1, {"capabilities": [{"name": "Write greeting", "steps": ["Replace text in the editor"], "expected_result": "The greeting is visible"}]})
        class Editor:
            def __init__(self):
                self.value = ""
            def observe(self):
                return {"window": "Editor", "window_handle": 41, "process_id": 81,
                        "controls": [{"id": 1, "name": "New editor", "type": "Document", "automation_id": "unfamiliar-editor",
                                      "actions": ["type"], "value": self.value, "password": False, "enabled": True, "visible": True}]}
            def act(self, action):
                self.value = action["text"]
        desktop = Editor()
        current = self.catalog.get("b")
        grant = create_grant(current, desktop.observe(), [1])
        cloud = FakeCloud([{"risk": "disposable", "task": "Type exactly: Self-taught experiment", "expected_result": "Self-taught experiment", "capability_name": "Write greeting"},
                           {"kind": "type", "text": "Self-taught experiment", "target": 1, "reason": "Use documented text entry"},
                           {"kind": "finish", "expected_text": "Self-taught experiment", "reason": "Verified"}])
        result = practice_one(self.catalog, current, cloud, desktop, lambda a, o: grants_action(grant, a, o),
                              lambda text: None, self.directory.name)
        self.assertEqual(result["status"], "experiment_observed")
        self.assertEqual(desktop.value, "Self-taught experiment")
        self.assertEqual(self.catalog.coverage("b", 1)[0]["observed_runs"], 1)

    def test_permission_denial_executes_nothing_and_is_not_saved_as_success(self):
        self.document()
        self.catalog.save_practice_plan("a", 1, plan())
        desktop = FakeDesktop()
        result = practice_one(self.catalog, self.catalog.get("a"), FakeCloud([{"kind": "invoke", "target": 1, "reason": "Calculate"}]),
                              desktop, lambda a, o: False, lambda text: None, self.directory.name)
        self.assertEqual(result["status"], "experiment_failed")
        self.assertEqual(desktop.actions, [])
        self.assertEqual(self.catalog.workflows("a", 1), [])
        self.assertEqual(self.catalog.coverage("a", 1)[0]["failed_attempts"], 1)

    def test_observing_existing_result_does_not_verify_a_practice_capability(self):
        self.document()
        self.catalog.save_practice_plan("a", 1, plan())
        desktop = FakeDesktop()
        desktop.actions.append({"prior": True})
        result = practice_one(self.catalog, self.catalog.get("a"), FakeCloud([{"kind": "finish", "expected_text": "42", "reason": "Already present"}]),
                              desktop, lambda a, o: True, lambda text: None, self.directory.name)
        self.assertEqual(result["status"], "experiment_failed")
        self.assertEqual(self.catalog.workflows("a", 1), [])
        self.assertEqual(self.catalog.learning_overview()["capabilities_tested_once"], 0)

    def test_failed_attempt_count_does_not_drop_older_failures(self):
        self.document()
        failed = {"task": "Try", "capability_name": "Add", "outcome": "blocked", "actions_executed": 0, "history": []}
        for _ in range(25):
            self.catalog.record_practice("a", 1, failed)
        self.assertEqual(self.catalog.coverage("a", 1)[0]["failed_attempts"], 25)

    def test_existing_workflow_does_not_prevent_new_experiment(self):
        self.document()
        record = {"task": "Add", "capability_name": "Add", "outcome": "result_observed", "actions_executed": 1, "history": []}
        self.catalog.save_workflow("a", 1, record)
        result = prepare_next_experiment(self.catalog, self.catalog.get("a"), Planner(), lambda text: None)
        self.assertEqual(result["capability"], "Subtract")
        self.assertIsNotNone(self.catalog.ready_practice_plan("a", 1))

    def test_repeated_observed_tests_stop_scheduling_that_capability(self):
        self.document()
        observed = {"task": "Add", "capability_name": "Add", "outcome": "result_observed", "actions_executed": 1, "history": []}
        for _ in range(2):
            self.catalog.save_workflow("a", 1, observed)
        self.assertEqual(self.catalog.next_practice_capability("a", 1), "Subtract")
        self.assertEqual(self.catalog.learning_overview()["capabilities_tested_repeatedly"], 1)
        self.catalog.save_practice_plan("a", 1, plan())
        self.assertIsNone(self.catalog.ready_practice_plan("a", 1))
        self.assertFalse(self.catalog.claim_practice_plan("a", 1, "Add"))

    def test_visual_assessment_does_not_count_as_observed_or_repeated_test(self):
        self.document()
        observed = {"task": "Add", "capability_name": "Add", "outcome": "visual_result_assessed", "actions_executed": 1, "history": []}
        for _ in range(2):
            self.catalog.save_workflow("a", 1, observed)
        overview = self.catalog.learning_overview()
        self.assertEqual(overview["capabilities_visually_assessed"], 1)
        self.assertEqual(overview["capabilities_tested_once"], 0)
        self.assertEqual(overview["capabilities_tested_repeatedly"], 0)
