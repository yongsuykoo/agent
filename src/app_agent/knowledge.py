"""Persist research separately from capabilities verified by execution."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class KnowledgeStore:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS blueprints (name TEXT PRIMARY KEY, body TEXT NOT NULL)")

    def create(self, name, version=""):
        name = name.strip()
        if not name:
            raise ValueError("Application name must not be empty.")
        blueprint = {"name": name, "version": version, "sources": [], "capabilities": [],
                     "updated_at": datetime.now(timezone.utc).isoformat()}
        with self.db:
            self.db.execute("INSERT INTO blueprints VALUES (?, ?)", (name.casefold(), json.dumps(blueprint)))
        return blueprint

    def get(self, name):
        row = self.db.execute("SELECT body FROM blueprints WHERE name = ?", (name.casefold(),)).fetchone()
        if row is None:
            raise KeyError(f"No blueprint for {name}")
        return json.loads(row[0])

    def close(self):
        self.db.close()

    def save_research(self, blueprint):
        """Replace an unverified blueprint; protect future execution evidence."""
        key = blueprint["name"].casefold()
        try:
            existing = self.get(key)
        except KeyError:
            existing = None
        if existing and any(cap.get("status") == "verified" for cap in existing["capabilities"]):
            raise ValueError("Research cannot overwrite verified capabilities.")
        with self.db:
            self.db.execute("INSERT INTO blueprints VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET body=excluded.body",
                            (key, json.dumps(blueprint)))
