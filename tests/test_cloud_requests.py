import io
import json
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from app_agent.research import CloudResearcher


class CloudRequestTests(unittest.TestCase):
    def test_json_mode_adds_json_instruction_to_input(self):
        response = Mock()
        response.read.return_value = b'{"status":"completed","output":[]}'
        opener = Mock()
        opener.open.return_value.__enter__ = Mock(return_value=response)
        opener.open.return_value.__exit__ = Mock(return_value=False)
        with patch("app_agent.research.build_opener", return_value=opener):
            CloudResearcher(key="test-key").request(input='{"app":"Calculator"}', text={"format": {"type": "json_object"}})
        payload = json.loads(opener.open.call_args.args[0].data)
        self.assertIn("JSON", payload["input"])
        self.assertIn('{"app":"Calculator"}', payload["input"])

    def test_message_list_json_mode_preserves_original_messages(self):
        response = Mock()
        response.read.return_value = b'{"status":"completed","output":[]}'
        opener = Mock()
        opener.open.return_value.__enter__ = Mock(return_value=response)
        opener.open.return_value.__exit__ = Mock(return_value=False)
        messages = [{"role": "user", "content": "Extract capabilities"}]
        with patch("app_agent.research.build_opener", return_value=opener):
            CloudResearcher(key="test-key").request(input=messages, text={"format": {"type": "json_object"}})
        payload = json.loads(opener.open.call_args.args[0].data)
        self.assertIn("JSON", payload["input"][0]["content"])
        self.assertEqual(payload["input"][1:], messages)
        self.assertEqual(len(messages), 1)

    def test_pasted_logs_rejected_without_echoing_value(self):
        value = "No app blueprint found.\nError: secret-pasted-value"
        with self.assertRaises(RuntimeError) as raised:
            CloudResearcher(key=value)
        self.assertNotIn(value, str(raised.exception))
        self.assertNotIn("secret-pasted-value", str(raised.exception))

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
