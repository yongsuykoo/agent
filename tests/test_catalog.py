import tempfile
import unittest
from app_agent.catalog import Catalog


def app(version="1", identity="start:calculator"):
    return {"id": identity, "name": "Calculator", "version": version, "app_id": "Calculator!App", "source": "start_menu", "aliases": ["Calculator"]}


def snapshot(apps, complete=("start_menu",)):
    return {"apps": apps, "complete_sources": list(complete), "warnings": []}


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.catalog = Catalog(self.directory.name)
    def tearDown(self):
        self.catalog.close()
        self.directory.cleanup()

    def test_new_scan_repeat_and_version_update(self):
        changes = self.catalog.sync(snapshot([app()]))
        self.assertEqual(changes["new"], ["Calculator"])
        old = self.catalog.get(app()["id"])
        self.assertTrue(self.catalog.save_blueprint(old["id"], old["generation"], {"capabilities": ["addition"]}))
        self.assertEqual(self.catalog.sync(snapshot([app()]))["new"], [])
        self.assertEqual(self.catalog.get(old["id"])["status"], "documented")
        self.assertEqual(self.catalog.sync(snapshot([app("2")]))["updated"], ["Calculator"])
        updated = self.catalog.get(old["id"])
        self.assertIsNone(updated["blueprint"])
        self.assertEqual(updated["generation"], old["generation"] + 1)
        self.assertFalse(self.catalog.save_blueprint(old["id"], old["generation"], {"stale": True}))

    def test_incomplete_scan_does_not_remove_apps(self):
        self.catalog.sync(snapshot([app()]))
        self.assertEqual(self.catalog.sync(snapshot([], complete=()))["removed"], [])
        self.assertEqual(len(self.catalog.apps()), 1)
        self.assertEqual(self.catalog.sync(snapshot([]))["removed"], ["Calculator"])
        self.assertEqual(self.catalog.apps(), [])

    def test_retry_backoff_and_priority(self):
        self.catalog.sync(snapshot([app()]))
        candidate = self.catalog.next_research()
        self.catalog.fail_research(candidate["id"], candidate["generation"], "network error")
        self.assertIsNone(self.catalog.next_research())
        self.assertEqual(self.catalog.get(candidate["id"])["status"], "research_failed")

    def test_workflows_require_agent_actions_and_current_version(self):
        self.catalog.sync(snapshot([app()]))
        current = self.catalog.get(app()["id"])
        record = {"task": "Add", "outcome": "result_observed", "actions_executed": 0, "history": []}
        self.assertFalse(self.catalog.save_workflow(current["id"], current["generation"], record))
        record["actions_executed"] = 1
        self.assertTrue(self.catalog.save_workflow(current["id"], current["generation"], record))
        self.assertEqual(len(self.catalog.workflows(current["id"], current["generation"])), 1)
        self.catalog.sync(snapshot([app("2")]))
        updated = self.catalog.get(current["id"])
        self.assertFalse(self.catalog.save_workflow(current["id"], current["generation"], record))
        self.assertEqual(self.catalog.workflows(updated["id"], updated["generation"]), [])

    def test_settings_survive_reopening(self):
        self.catalog.set_setting("daily_limit", 3)
        self.catalog.close()
        self.catalog = Catalog(self.directory.name)
        self.assertEqual(self.catalog.setting("daily_limit"), 3)

    def test_coverage_separates_observed_results_visual_assessments_and_failures(self):
        self.catalog.sync(snapshot([app()]))
        current = self.catalog.get(app()["id"])
        self.catalog.save_blueprint(current["id"], current["generation"], {"capabilities": [{"name": "Add"}]})
        failed = {"task": "Add", "capability_name": "Add", "outcome": "stalled", "actions_executed": 1, "history": []}
        self.catalog.record_practice(current["id"], current["generation"], failed)
        visual = {**failed, "outcome": "visual_result_assessed"}
        self.catalog.save_workflow(current["id"], current["generation"], visual)
        coverage = self.catalog.coverage(current["id"], current["generation"])[0]
        self.assertEqual(coverage["status"], "visual_result_assessed")
        self.assertEqual(coverage["observed_runs"], 0)
        self.assertEqual(coverage["visual_assessments"], 1)
        self.assertEqual(coverage["failed_attempts"], 1)
