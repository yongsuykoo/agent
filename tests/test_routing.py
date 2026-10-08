import unittest
from unittest.mock import Mock, patch
from app_agent.routing import choose_app, window_matches, launch_app
from test_catalog import app


class RoutingTests(unittest.TestCase):
    def test_explicit_app_name_routes_without_model(self):
        cloud = Mock()
        selected = choose_app("Use Calculator to add 2 and 2", [app()], cloud)
        self.assertEqual(selected["id"], app()["id"])
        cloud.request.assert_not_called()

    def test_model_choice_must_belong_to_inventory(self):
        cloud = Mock()
        cloud.request.return_value = {"output": [{"content": [{"type": "output_text", "text": '{"app_id":"invented"}'}]}]}
        with self.assertRaises(RuntimeError):
            choose_app("Add numbers", [app()], cloud)

    def test_task_inference_chooses_valid_app(self):
        cloud = Mock()
        cloud.request.return_value = {"output": [{"content": [{"type": "output_text", "text": '{"app_id":"start:calculator"}'}]}]}
        self.assertEqual(choose_app("Add 2 and 2", [app()], cloud)["id"], app()["id"])

    def test_window_matching_excludes_sensitive_account_pages(self):
        browser = {"name": "Google Chrome", "aliases": ["Google Chrome"]}
        matches = window_matches(browser, [(1, "API keys - Google Chrome"), (2, "New Tab - Google Chrome"), (3, "Calculator")])
        self.assertEqual(matches, [(2, "New Tab - Google Chrome")])

    def test_photoshop_title_prefix_supports_open_documents_and_excludes_browser_tabs(self):
        photoshop = {'name':'Adobe Photoshop CS2','aliases':['Adobe Photoshop CS2']}
        windows = [(1,'Adobe Photoshop CS2 - [User document @ 100%]'), (2,'Adobe Photoshop'),
                   (3,'Adobe Photoshop - Tutorial - Google Chrome'), (4,'Photoshop 2024 - [Untitled-1]')]
        self.assertEqual(window_matches(photoshop,windows),[windows[0],windows[1],windows[3]])

    def test_launch_only_uses_discovered_start_identity(self):
        with patch("app_agent.routing.subprocess.Popen") as popen:
            launch_app(app())
            popen.assert_called_once_with(["explorer.exe", "shell:AppsFolder\\Calculator!App"])
            for value in ("", "https://example.com", 'App" & command', "App\ncommand"):
                with self.assertRaises(RuntimeError):
                    launch_app({"app_id": value})
