import io
import json
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from app_agent.research import CloudResearcher


class CloudRequestTests(unittest.TestCase):
    def test_search_uses_compatible_tool_and_choice(self):
        cloud = CloudResearcher(key="test-key")
        cloud.request = Mock(return_value={"output": [{"content": [{"annotations": [
            {"type": "url_citation", "url": "https://example.com/manual"}]}]}]})
        self.assertEqual(cloud.find_sources("Calculator", ""), ["https://example.com/manual"])
        request = cloud.request.call_args.kwargs
        self.assertEqual(request["tools"], [{"type": "web_search_preview"}])
        self.assertEqual(request["tool_choice"], "auto")

    def test_reports_provider_parameter_without_exposing_key(self):
        key = "sk-secret-for-test"
        error = HTTPError("https://api.openai.com/v1/responses", 400, "Bad request", {},
                          io.BytesIO(json.dumps({"error": {"message": f"Unsupported tool with {key}", "param": "tools[0].type"}}).encode()))
        opener = Mock()
        opener.open.side_effect = error
        with patch("app_agent.research.build_opener", return_value=opener):
            with self.assertRaises(RuntimeError) as raised:
                CloudResearcher(key=key).request(input="test")
        message = str(raised.exception)
        self.assertIn("Unsupported tool", message)
        self.assertIn("tools[0].type", message)
        self.assertNotIn(key, message)

    def test_unreadable_error_body_is_safe(self):
        error = HTTPError("https://api.openai.com/v1/responses", 400, "Bad request", {}, io.BytesIO(b"not json"))
        opener = Mock()
        opener.open.side_effect = error
        with patch("app_agent.research.build_opener", return_value=opener):
            with self.assertRaisesRegex(RuntimeError, "no readable error detail"):
                CloudResearcher(key="test-key").request(input="test")
