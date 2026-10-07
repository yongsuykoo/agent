import tempfile
import threading
import unittest
from unittest.mock import patch, Mock
from app_agent.catalog import Catalog
from app_agent.learning import ensure_blueprint, learn_next, practice_task
from test_catalog import app, snapshot


class LearningTests(unittest.TestCase):
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
