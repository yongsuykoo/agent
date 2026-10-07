"""Persistent inventory, version-specific research queues, and workflow evidence."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


class Catalog:
    def __init__(self, data_dir):
        root = Path(data_dir)
        root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(root / "catalog.sqlite3", timeout=20)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS apps (id TEXT PRIMARY KEY, metadata TEXT NOT NULL, present INTEGER NOT NULL,
          generation INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL, blueprint TEXT, error TEXT,
          attempts INTEGER NOT NULL DEFAULT 0, retry_at TEXT, updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS workflows (id INTEGER PRIMARY KEY, app_id TEXT NOT NULL, generation INTEGER NOT NULL,
          task TEXT NOT NULL, outcome TEXT NOT NULL, record TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS scans (time TEXT NOT NULL, report TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS interfaces (app_id TEXT NOT NULL, generation INTEGER NOT NULL, body TEXT NOT NULL,
          observed TEXT NOT NULL, PRIMARY KEY(app_id,generation));
        CREATE TABLE IF NOT EXISTS practice_attempts (app_id TEXT NOT NULL, generation INTEGER NOT NULL,
          capability TEXT NOT NULL, outcome TEXT NOT NULL, body TEXT NOT NULL, created TEXT NOT NULL);
        """)

    def close(self):
        self.db.close()

    def setting(self, key, default=None):
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self.db:
            self.db.execute("INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))

    def sync(self, snapshot):
        changed = {"new": [], "updated": [], "removed": [], "warnings": snapshot.get("warnings", [])}
        seen = set()
        timestamp = now()
        with self.db:
            for app in snapshot["apps"]:
                identity = app["id"]
                seen.add(identity)
                row = self.db.execute("SELECT * FROM apps WHERE id=?", (identity,)).fetchone()
                if row is None:
                    self.db.execute("INSERT INTO apps (id,metadata,present,status,updated) VALUES (?,?,1,'queued',?)", (identity, json.dumps(app), timestamp))
                    changed["new"].append(app["name"])
                else:
                    old = json.loads(row["metadata"])
                    if old.get("version", "") != app.get("version", "") or not row["present"]:
                        self.db.execute("UPDATE apps SET metadata=?,present=1,generation=generation+1,status='queued',blueprint=NULL,error=NULL,attempts=0,retry_at=NULL,updated=? WHERE id=?", (json.dumps(app), timestamp, identity))
                        changed["updated"].append(app["name"])
                    else:
                        self.db.execute("UPDATE apps SET metadata=?,present=1,updated=? WHERE id=?", (json.dumps(app), timestamp, identity))
            complete = set(snapshot.get("complete_sources", []))
            for row in self.db.execute("SELECT * FROM apps WHERE present=1").fetchall():
                app = json.loads(row["metadata"])
                if row["id"] not in seen and app["source"] in complete:
                    self.db.execute("UPDATE apps SET present=0,status='removed',updated=? WHERE id=?", (timestamp, row["id"]))
                    changed["removed"].append(app["name"])
            self.db.execute("INSERT INTO scans VALUES (?,?)", (timestamp, json.dumps(changed)))
        return changed

    def apps(self):
        return [{**json.loads(row["metadata"]), "generation": row["generation"], "status": row["status"],
                 "error": row["error"], "blueprint": json.loads(row["blueprint"]) if row["blueprint"] else None}
                for row in self.db.execute("SELECT * FROM apps WHERE present=1 ORDER BY updated,id")]

    def get(self, identity):
        matches = [app for app in self.apps() if app["id"] == identity]
        if not matches:
            raise KeyError("App is no longer in the current inventory.")
        return matches[0]

    def next_research(self):
        rows = self.db.execute("SELECT id FROM apps WHERE present=1 AND (status='queued' OR (status='research_failed' AND retry_at<=?)) ORDER BY attempts,updated,id", (now(),)).fetchall()
        known = {app["id"]: app for app in self.apps()}
        candidates = [known[row[0]] for row in rows if row[0] in known]
        # Learn user-facing launchable apps before driver/utility registrations.
        priority = set(self.setting("priority_apps", []))
        candidates.sort(key=lambda app: (app["id"] not in priority, not bool(app.get("app_id")), "calculator" not in app["name"].casefold(), app["name"].casefold()))
        return candidates[0] if candidates else None

    def save_blueprint(self, identity, generation, blueprint):
        with self.db:
            cursor = self.db.execute("UPDATE apps SET blueprint=?,status='documented',error=NULL,attempts=0,retry_at=NULL WHERE id=? AND generation=? AND present=1", (json.dumps(blueprint), identity, generation))
        return cursor.rowcount == 1

    def fail_research(self, identity, generation, error):
        row = self.db.execute("SELECT attempts FROM apps WHERE id=?", (identity,)).fetchone()
        attempts = (row[0] if row else 0) + 1
        retry = (datetime.now(timezone.utc) + timedelta(minutes=min(1440, 15 * 2 ** min(attempts - 1, 7)))).isoformat()
        with self.db:
            self.db.execute("UPDATE apps SET status='research_failed',error=?,attempts=?,retry_at=? WHERE id=? AND generation=?", (str(error)[:1000], attempts, retry, identity, generation))

    def save_workflow(self, identity, generation, record):
        if record.get("outcome") not in ("result_observed", "visual_result_assessed") or record.get("actions_executed", 0) < 1:
            return False
        with self.db:
            current = self.db.execute("SELECT generation,present FROM apps WHERE id=?", (identity,)).fetchone()
            if not current or not current["present"] or current["generation"] != generation:
                return False
            self.db.execute("INSERT INTO workflows (app_id,generation,task,outcome,record,created) VALUES (?,?,?,?,?,?)", (identity, generation, record["task"], record["outcome"], json.dumps(record), now()))
        return True

    def workflows(self, identity, generation):
        rows = self.db.execute("SELECT task,record FROM workflows WHERE app_id=? AND generation=? ORDER BY id DESC LIMIT 5", (identity, generation)).fetchall()
        return [{"task": row["task"], "actions": [{"action": entry["executed_action"],
                 "target": next((control for control in entry["observation"]["controls"] if control["id"] == entry["action"].get("target")), {})}
                 for entry in json.loads(row["record"])["history"] if entry.get("execution") == "executed"],
                 "status": json.loads(row["record"])["outcome"] + "_once"} for row in rows]

    def save_interface(self, identity, generation, observation):
        with self.db:
            self.db.execute("INSERT INTO interfaces VALUES (?,?,?,?) ON CONFLICT(app_id,generation) DO UPDATE SET body=excluded.body,observed=excluded.observed", (identity, generation, json.dumps(observation), now()))

    def interface(self, identity, generation):
        row = self.db.execute("SELECT body FROM interfaces WHERE app_id=? AND generation=?", (identity, generation)).fetchone()
        return json.loads(row[0]) if row else None

    def coverage(self, identity, generation):
        app = self.get(identity)
        capabilities = (app["blueprint"] or {}).get("capabilities", [])
        observed, visual = {}, {}
        for row in self.db.execute("SELECT record FROM workflows WHERE app_id=? AND generation=?", (identity, generation)):
            record = json.loads(row[0])
            name = record.get("capability_name")
            if name:
                counts = visual if record["outcome"] == "visual_result_assessed" else observed
                counts[name] = counts.get(name, 0) + 1
        attempts = self.practice_attempts(identity, generation)
        return [{"name": cap["name"], "observed_runs": observed.get(cap["name"], 0), "visual_assessments": visual.get(cap["name"], 0),
                 "failed_attempts": sum(item["capability"] == cap["name"] and item["outcome"] not in ("result_observed", "visual_result_assessed") for item in attempts),
                 "status": "result_observed" if cap["name"] in observed else "visual_result_assessed" if cap["name"] in visual else "documented_unverified"} for cap in capabilities]

    def record_practice(self, identity, generation, record):
        if not record.get("capability_name"):
            return
        with self.db:
            self.db.execute("INSERT INTO practice_attempts VALUES (?,?,?,?,?,?)", (identity, generation, record["capability_name"], record["outcome"], json.dumps(record), now()))

    def practice_attempts(self, identity, generation):
        return [{"capability": row[0], "outcome": row[1], "evidence": json.loads(row[2]).get("history", [])[-2:]}
                for row in self.db.execute("SELECT capability,outcome,body FROM practice_attempts WHERE app_id=? AND generation=? ORDER BY created DESC LIMIT 20", (identity, generation))]
