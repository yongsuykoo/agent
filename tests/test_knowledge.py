import sqlite3
import tempfile
import unittest
from pathlib import Path
from app_agent.knowledge import KnowledgeStore


class KnowledgeTests(unittest.TestCase):
    def test_persistence_and_case_insensitive_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "knowledge.sqlite3"
            store = KnowledgeStore(path)
            created = store.create("Calculator", "1")
            self.assertEqual(created["capabilities"], [])
            store.close()
            reopened = KnowledgeStore(path)
            self.assertEqual(reopened.get("calculator"), created)
            with self.assertRaises(sqlite3.IntegrityError):
                reopened.create("CALCULATOR", "2")
            self.assertEqual(reopened.get("Calculator"), created)
            reopened.close()

    def test_missing_and_empty_apps(self):
        with tempfile.TemporaryDirectory() as directory:
            store = KnowledgeStore(Path(directory) / "knowledge.sqlite3")
            with self.assertRaises(KeyError):
                store.get("missing")
            with self.assertRaises(ValueError):
                store.create(" ")
            store.close()
