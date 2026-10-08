import tempfile
import json
import threading
import unittest
from unittest.mock import patch, Mock
from app_agent.catalog import Catalog
from app_agent.learning import deepen_next, ensure_blueprint, learn_next, merge_blueprints, practice_task
from test_catalog import app, snapshot


class LearningTests(unittest.TestCase):
    def test_deeper_manuals_add_capabilities_without_losing_observed_workflows(self):
        previous = {"name": "Calculator", "version": "1", "sources": [{"url": "https://example.com/basic"}],
                    "capabilities": [{"name": "Add", "steps": ["Plus"], "source_urls": ["https://example.com/basic"]}], "limitations": ["Technical manual missing"]}
        self.catalog.save_blueprint(app()["id"], 1, previous)
        self.catalog.save_workflow(app()["id"], 1, {"task": "Add", "capability_name": "Add", "outcome": "result_observed", "actions_executed": 1, "history": []})
        additional = {**previous, "sources": [{"url": "https://example.com/technical"}],
                      "capabilities": [{"name": "add", "steps": ["Use documented addition"], "source_urls": ["https://example.com/technical"]},
                                       {"name": "Subtract", "steps": ["Minus"], "source_urls": ["https://example.com/technical"]}]}
        with patch("app_agent.learning.research_app", return_value=additional) as research:
            result = deepen_next(self.catalog, object(), lambda text: None)
        self.assertEqual(result["new_capabilities"], 1)
        self.assertEqual(research.call_args.kwargs["exclude_urls"], ["https://example.com/basic"])
        current = self.catalog.get(app()["id"])["blueprint"]
        self.assertEqual([cap["name"] for cap in current["capabilities"]], ["Add", "Subtract"])
        self.assertEqual(len(current["sources"]), 2)
        self.assertEqual(self.catalog.coverage(app()["id"], 1)[0]["observed_runs"], 1)

    def test_deeper_research_failure_preserves_first_blueprint_and_backs_off(self):
        previous = {"capabilities": [{"name": "Add"}]}
        self.catalog.save_blueprint(app()["id"], 1, previous)
        with patch("app_agent.learning.research_app", side_effect=RuntimeError("No new sources")) as research:
            result = deepen_next(self.catalog, object(), lambda text: None)
            retry = deepen_next(self.catalog, object(), lambda text: None)
            self.assertEqual(research.call_count, 1)
        self.assertEqual(result["status"], "documentation_deferred")
        self.assertEqual(retry["status"], "documentation_wait")
        self.assertEqual(self.catalog.get(app()["id"])["blueprint"], previous)

    def test_deepening_uses_same_daily_budget_as_initial_research(self):
        self.catalog.save_blueprint(app()["id"], 1, {"capabilities": [{"name": "Add"}]})
        from datetime import datetime
        self.catalog.set_setting("research_budget", {"day": datetime.now().astimezone().date().isoformat(), "used": 1})
        with patch("app_agent.learning.research_app") as research:
            result = deepen_next(self.catalog, object(), lambda text: None, limit=1)
        self.assertEqual(result["status"], "daily_limit")
        research.assert_not_called()

    def test_deeper_no_growth_preserves_limitations_and_schedules_later_review(self):
        previous = {"capabilities": [{"name": "Add", "steps": ["Plus"]}], "limitations": ["Unknown API"]}
        self.catalog.save_blueprint(app()["id"], 1, previous)
        with patch("app_agent.learning.research_app", return_value=previous):
            result = deepen_next(self.catalog, object(), lambda text: None)
        self.assertEqual(result["status"], "documentation_reviewed")
        self.assertEqual(result["new_capabilities"], 0)
        self.assertEqual(self.catalog.get(app()["id"])["blueprint"]["limitations"], ["Unknown API"])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.catalog = Catalog(self.directory.name)
        self.catalog.sync(snapshot([app()]))
    def tearDown(self):
        self.catalog.close()
        self.directory.cleanup()

    def test_study_saves_blueprint_and_does_not_repeat(self):
        blueprint = {"capabilities": [{"name": "Add"}]}
        with patch("app_agent.learning.research_app", return_value=blueprint) as research:
            result = learn_next(self.catalog, object(), lambda text: None)
            self.assertEqual(result["status"], "documented")
            self.assertEqual(learn_next(self.catalog, object(), lambda text: None)["status"], "queue_empty")
            research.assert_called_once()

    def test_failed_study_counts_towards_budget_and_backs_off(self):
        with patch("app_agent.learning.research_app", side_effect=RuntimeError("quota")):
            self.assertEqual(learn_next(self.catalog, object(), lambda text: None, limit=1)["status"], "research_failed")
        self.assertEqual(learn_next(self.catalog, object(), lambda text: None, limit=1)["status"], "daily_limit")
        self.assertIsNone(self.catalog.next_research())

    def test_cancelled_research_never_saves_partial_results(self):
        cancel = threading.Event()
        cancel.set()
        with patch("app_agent.learning.research_app", return_value={"capabilities": []}):
            with self.assertRaises(RuntimeError):
                ensure_blueprint(self.catalog, self.catalog.apps()[0], object(), lambda text: None, cancel)
        self.assertIsNone(self.catalog.apps()[0]["blueprint"])

    def test_unsafe_or_unsupported_practice_is_rejected(self):
        cloud = Mock()
        cloud.request.return_value = {"output": [{"content": [{"type": "output_text", "text": '{"risk":"unsupported"}'}]}]}
        with self.assertRaises(RuntimeError):
            practice_task({"capabilities": []}, cloud)
        self.assertEqual(cloud.request.call_count, 1)

    def response(self, plan):
        return {"output": [{"content": [{"type": "output_text", "text": json.dumps(plan)}]}]}

    def test_mismatched_experiment_is_repaired_before_it_can_be_returned(self):
        bad = {"task": "Replace the document text with exactly: First", "expected_result": "Different",
               "capability_name": "Write", "risk": "disposable"}
        good = {**bad, "task": "Replace the document text with exactly: New experiment", "expected_result": "New experiment"}
        context = {"required_task_form": "Replace the document text with exactly: <your own short test text>"}
        cloud = Mock()
        cloud.request.side_effect = [self.response(bad), self.response(good)]
        result = practice_task({"capabilities": [{"name": "Write"}]}, cloud, experiment_context=context)
        self.assertEqual(result, good)
        self.assertEqual(cloud.request.call_count, 2)
        retry = cloud.request.call_args.kwargs
        feedback = json.loads(retry["input"])
        self.assertIn("matching its expected result", feedback["validation_error"])
        self.assertEqual(feedback["previous_plan"], bad)
        schema = retry["text"]["format"]
        self.assertTrue(schema["strict"])
        self.assertFalse(schema["schema"]["additionalProperties"])
        self.assertEqual(schema["schema"]["properties"]["capability_name"]["enum"], ["Write", None])

    def test_invalid_practice_stops_after_three_attempts_without_changing_the_goal(self):
        bad = {"task": "Replace the document text with exactly: First", "expected_result": "Different",
               "capability_name": "Write", "risk": "disposable"}
        cloud = Mock()
        cloud.request.return_value = self.response(bad)
        with self.assertRaisesRegex(RuntimeError, "after three attempts"):
            practice_task({"capabilities": [{"name": "Write"}]}, cloud,
                          experiment_context={"required_task_form": "Replace the document text with exactly: <your own short test text>"})
        self.assertEqual(cloud.request.call_count, 3)

    def test_cancel_during_planning_prevents_retry_and_returning_a_plan(self):
        cancel = threading.Event()
        cloud = Mock()
        def response(**kwargs):
            cancel.set()
            return self.response({"task": "Write", "expected_result": "Text", "capability_name": "Write", "risk": "disposable"})
        cloud.request.side_effect = response
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            practice_task({"capabilities": [{"name": "Write"}]}, cloud, cancel=cancel)
        self.assertEqual(cloud.request.call_count, 1)
