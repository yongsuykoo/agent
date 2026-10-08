import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app_agent.knowledge import KnowledgeStore
from app_agent.research import CloudResearcher, PageText, public_https, research_app, validate_extraction


DOCUMENT = {"url": "https://example.com/help", "text": "Press plus to add two numbers.",
            "sha256": "test", "retrieved_at": "2026-10-07"}
EXTRACTION = {"capabilities": [{"name": "Add", "steps": ["Press plus"],
                              "expected_result": "The sum", "source_ids": [0], "status": "verified"}],
              "limitations": ["Version unspecified"]}


class ResearchTests(unittest.TestCase):
    def test_invalid_expected_result_is_repaired_using_the_same_documents(self):
        researcher = CloudResearcher(key="test")
        invalid = json.loads(json.dumps(EXTRACTION))
        invalid["capabilities"][0]["expected_result"] = ""
        def response(value):
            return {"output": [{"content": [{"type": "output_text", "text": json.dumps(value)}]}]}
        with patch.object(researcher, "request", side_effect=[response(invalid), response(EXTRACTION)]) as request:
            result = researcher.extract("Calculator", "1", [DOCUMENT])
        self.assertEqual(result["capabilities"][0]["expected_result"], "The sum")
        first, second = [json.loads(call.kwargs["input"]) for call in request.call_args_list]
        self.assertEqual(first["documents"], second["documents"])
        self.assertIn("expected_result", second["validation_feedback"])
        self.assertTrue(request.call_args.kwargs["text"]["format"]["strict"])

    def test_unknown_evidence_is_never_accepted_after_bounded_repair(self):
        researcher = CloudResearcher(key="test")
        invalid = json.loads(json.dumps(EXTRACTION))
        invalid["capabilities"][0]["source_ids"] = [99]
        response = {"output": [{"content": [{"type": "output_text", "text": json.dumps(invalid)}]}]}
        with patch.object(researcher, "request", return_value=response) as request:
            with self.assertRaisesRegex(ValueError, "three validation attempts"):
                researcher.extract("Calculator", "1", [DOCUMENT])
        self.assertEqual(request.call_count, 3)

    def test_deeper_search_excludes_already_studied_citations(self):
        researcher = CloudResearcher(key="test")
        response = {"output": [{"content": [{"annotations": [
            {"type": "url_citation", "url": "https://example.com/old"},
            {"type": "url_citation", "url": "https://example.com/technical"}]}]}]}
        with patch.object(researcher, "request", return_value=response) as request:
            urls = researcher.find_sources("Editor", "1", focus={"known_gaps": ["API"]}, exclude_urls=["https://example.com/old"])
        self.assertEqual(urls, ["https://example.com/technical"])
        self.assertIn("API", request.call_args.kwargs["input"])

    def test_duplicate_capability_names_are_rejected(self):
        duplicate = json.loads(json.dumps(EXTRACTION))
        duplicate["capabilities"].append({**duplicate["capabilities"][0], "name": "add"})
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_extraction(duplicate, [DOCUMENT])

    def test_search_extract_and_persist_pipeline(self):
        class FakeResearcher(CloudResearcher):
            def request(self, **payload):
                if "tools" in payload:
                    return {"output": [{"content": [{"annotations": [
                        {"type": "url_citation", "url": DOCUMENT["url"]}]}]}]}
                sent = json.loads(payload["input"])
                self_test.assertEqual(sent["documents"][0]["text"], DOCUMENT["text"])
                return {"output": [{"content": [{"type": "output_text", "text": json.dumps(EXTRACTION)}]}]}
        self_test = self
        blueprint = research_app("Calculator", "1", FakeResearcher(key="test"), fetcher=lambda url: DOCUMENT)
        self.assertEqual(blueprint["capabilities"][0]["status"], "documented_unverified")
        self.assertNotIn("text", blueprint["sources"][0])
        with tempfile.TemporaryDirectory() as directory:
            store = KnowledgeStore(Path(directory) / "knowledge.db")
            store.save_research(blueprint)
            self.assertEqual(store.get("Calculator"), blueprint)
            store.close()

    def test_reject_unknown_citations(self):
        invalid = json.loads(json.dumps(EXTRACTION))
        invalid["capabilities"][0]["source_ids"] = [7]
        with self.assertRaises(ValueError):
            validate_extraction(invalid, [DOCUMENT])

    def test_reject_empty_steps_and_capabilities(self):
        for result in ({"capabilities": [], "limitations": []},
                       {"capabilities": [{**EXTRACTION["capabilities"][0], "steps": []}], "limitations": []}):
            with self.assertRaises(ValueError):
                validate_extraction(result, [DOCUMENT])

    def test_blocks_private_and_non_https_sources(self):
        for url in ("http://example.com", "file:///tmp/private", "https://user:password@example.com", "https://example.com:8443"):
            with self.assertRaises(ValueError):
                public_https(url)
        with patch("app_agent.research.getproxies", return_value={}), patch("app_agent.research.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]):
            with self.assertRaises(ValueError):
                public_https("https://example.com")

    def test_proxy_resolves_public_hosts_but_blocks_private_literals(self):
        with patch("app_agent.research.getproxies", return_value={"https": "https://proxy.example.com"}), patch("app_agent.research.proxy_bypass", return_value=False):
            self.assertEqual(public_https("https://example.com/help"), "https://example.com/help")
            for url in ("https://127.0.0.1", "https://localhost", "https://host.internal"):
                with self.assertRaises(ValueError):
                    public_https(url)

    def test_hidden_page_content_removed(self):
        parser = PageText()
        parser.feed("<h1>Manual</h1><script>bad()</script><style>hidden</style><p>Add numbers</p>")
        self.assertEqual(parser.parts, ["Manual", "Add numbers"])

    def test_failed_retrieval_does_not_generate(self):
        def fail(url):
            raise RuntimeError("unavailable")
        with self.assertRaises(RuntimeError):
            research_app("Calculator", "", object(), urls=[DOCUMENT["url"]], fetcher=fail)

    def test_verified_knowledge_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            store = KnowledgeStore(Path(directory) / "knowledge.db")
            previous = {"name": "Calculator", "capabilities": [{"status": "verified"}]}
            store.save_research(previous)
            with self.assertRaises(ValueError):
                store.save_research({"name": "Calculator", "capabilities": []})
            self.assertEqual(store.get("Calculator"), previous)
            store.close()
