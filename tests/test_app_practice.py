import copy
import tempfile
import unittest
from app_agent.app_practice import create_grant, grants_action, consume_practice_budget
from app_agent.catalog import Catalog


class PracticeGrantTests(unittest.TestCase):
    def snapshot(self):
        return {"window_handle": 10, "process_id": 20, "controls": [
            {"id": 1, "name": "Expand", "type": "Button", "automation_id": "expand", "visible": True, "enabled": True, "actions": ["invoke"]},
            {"id": 2, "name": "Delete", "type": "Button", "automation_id": "delete", "visible": True, "enabled": True, "actions": ["invoke"]}]}

    def test_only_selected_controls_and_process_are_authorized(self):
        original = self.snapshot()
        grant = create_grant({"id": "app", "generation": 1}, original, [1])
        self.assertTrue(grants_action(grant, {"kind": "invoke", "target": 1}, original))
        self.assertFalse(grants_action(grant, {"kind": "invoke", "target": 2}, original))
        modified = copy.deepcopy(original)
        modified["process_id"] = 21
        self.assertFalse(grants_action(grant, {"kind": "invoke", "target": 1}, modified))
        self.assertFalse(grants_action(grant, {"kind": "click_point", "x": 1, "y": 1}, original))

    def test_empty_password_or_ambiguous_grants_rejected(self):
        for selected in ([], [0], [99]):
            with self.assertRaises(ValueError):
                create_grant({"id": "app", "generation": 1}, self.snapshot(), selected)
        modified = self.snapshot()
        modified["controls"][0]["password"] = True
        with self.assertRaises(ValueError):
            create_grant({"id": "app", "generation": 1}, modified, [1])

    def test_background_practice_budget_is_persistent(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Catalog(directory)
            self.assertTrue(consume_practice_budget(catalog, limit=1))
            catalog.close()
            catalog = Catalog(directory)
            self.assertFalse(consume_practice_budget(catalog, limit=1))
            catalog.close()
