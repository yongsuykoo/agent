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
        self.data_dir = root
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
        CREATE TABLE IF NOT EXISTS practice_plans (app_id TEXT NOT NULL, generation INTEGER NOT NULL,
          capability TEXT NOT NULL, status TEXT NOT NULL, body TEXT, error TEXT, retry_at TEXT,
          attempts INTEGER NOT NULL DEFAULT 0, updated TEXT NOT NULL,
          PRIMARY KEY(app_id,generation,capability));
        CREATE INDEX IF NOT EXISTS workflow_app_generation ON workflows(app_id,generation);
        CREATE INDEX IF NOT EXISTS practice_app_generation ON practice_attempts(app_id,generation,capability);
        """)

    def close(self):
        self.db.close()

    def setting(self, key, default=None):
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self.db:
            self.db.execute("INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))

    def consume_budget(self, key, limit):
        """Reserve an attempt atomically. Zero means no daily application cap."""
        if type(limit) is not int or limit < 0:
            raise ValueError("Usage limit must be a nonnegative integer; zero means uncapped.")
        day = datetime.now().astimezone().date().isoformat()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            budget = self.setting(key, {"day": day, "used": 0})
            if budget["day"] != day:
                budget = {"day": day, "used": 0}
            if limit and budget["used"] >= limit:
                self.db.rollback()
                return None
            budget["used"] += 1
            self.db.execute("INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                            (key, json.dumps(budget)))
            self.db.commit()
            return budget
        except BaseException:
            self.db.rollback()
            raise

    def claim_research(self, identity, generation):
        lease = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
        with self.db:
            cursor = self.db.execute("UPDATE apps SET status='researching',retry_at=? WHERE id=? AND generation=? AND present=1 AND "
                "(status='queued' OR (status IN ('research_failed','researching') AND retry_at<=?))",
                (lease, identity, generation, now()))
        return cursor.rowcount == 1

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
        row = self.db.execute("SELECT * FROM apps WHERE id=? AND present=1", (identity,)).fetchone()
        if row is None:
            raise KeyError("App is no longer in the current inventory.")
        return {**json.loads(row["metadata"]), "generation": row["generation"], "status": row["status"],
                "error": row["error"], "blueprint": json.loads(row["blueprint"]) if row["blueprint"] else None}

    def next_research(self):
        rows = self.db.execute("SELECT id FROM apps WHERE present=1 AND (status='queued' OR (status IN ('research_failed','researching') AND retry_at<=?)) ORDER BY attempts,updated,id", (now(),)).fetchall()
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
                 "status": json.loads(row["record"])["outcome"] + "_once",
                 "recipe": json.loads(row["record"]).get("replay_recipe")} for row in rows]

    def save_interface(self, identity, generation, observation):
        with self.db:
            self.db.execute("INSERT INTO interfaces VALUES (?,?,?,?) ON CONFLICT(app_id,generation) DO UPDATE SET body=excluded.body,observed=excluded.observed", (identity, generation, json.dumps(observation), now()))

    def interface(self, identity, generation):
        row = self.db.execute("SELECT body FROM interfaces WHERE app_id=? AND generation=?", (identity, generation)).fetchone()
        return json.loads(row[0]) if row else None

    def coverage(self, identity, generation):
        try:
            app = self.get(identity)
        except KeyError:
            return []
        if app["generation"] != generation:
            return []
        capabilities = (app["blueprint"] or {}).get("capabilities", [])
        observed, visual = {}, {}
        for row in self.db.execute("SELECT record FROM workflows WHERE app_id=? AND generation=?", (identity, generation)):
            record = json.loads(row[0])
            name = record.get("capability_name")
            if name:
                counts = visual if record["outcome"] == "visual_result_assessed" else observed
                counts[name] = counts.get(name, 0) + 1
        failed = {row[0]: row[1] for row in self.db.execute(
            "SELECT capability,COUNT(*) FROM practice_attempts WHERE app_id=? AND generation=? AND outcome NOT IN ('result_observed','visual_result_assessed') GROUP BY capability", (identity, generation))}
        return [{"name": cap["name"], "observed_runs": observed.get(cap["name"], 0), "visual_assessments": visual.get(cap["name"], 0),
                 "failed_attempts": failed.get(cap["name"], 0),
                 "status": "result_observed" if cap["name"] in observed else "visual_result_assessed" if cap["name"] in visual else "documented_unverified"} for cap in capabilities]

    def record_practice(self, identity, generation, record):
        if not record.get("capability_name"):
            return
        with self.db:
            self.db.execute("INSERT INTO practice_attempts VALUES (?,?,?,?,?,?)", (identity, generation, record["capability_name"], record["outcome"], json.dumps(record), now()))

    def practice_attempts(self, identity, generation):
        return [{"capability": row[0], "outcome": row[1], "evidence": json.loads(row[2]).get("history", [])[-2:]}
                for row in self.db.execute("SELECT capability,outcome,body FROM practice_attempts WHERE app_id=? AND generation=? ORDER BY created DESC LIMIT 20", (identity, generation))]

    def practice_plan(self, identity, generation, capability):
        row = self.db.execute("SELECT * FROM practice_plans WHERE app_id=? AND generation=? AND capability=?", (identity, generation, capability)).fetchone()
        return {**dict(row), "body": json.loads(row["body"]) if row["body"] else None} if row else None

    def next_practice_capability(self, identity, generation, target_runs=2):
        coverage = sorted(self.coverage(identity, generation), key=lambda item: (item["observed_runs"], item["failed_attempts"], item["name"]))
        for capability in coverage:
            if capability["observed_runs"] >= target_runs:
                continue
            plan = self.practice_plan(identity, generation, capability["name"])
            if plan and (plan["status"] == "ready" or (plan["retry_at"] and plan["retry_at"] > now())):
                continue
            if plan and plan["status"] == "running":
                # Recover an expired lease through ready_practice_plan; retain
                # the exact experiment rather than generating another one.
                continue
            return capability["name"]
        return None

    def save_practice_plan(self, identity, generation, plan):
        try:
            app = self.get(identity)
        except KeyError:
            return False
        name = plan.get("capability_name")
        if app["generation"] != generation or name not in {cap["name"] for cap in (app["blueprint"] or {}).get("capabilities", [])}:
            return False
        if plan.get("risk") != "disposable" or any(not isinstance(plan.get(field), str) or not plan[field].strip() for field in ("task", "expected_result")):
            raise ValueError("Only a documented disposable experiment with an expected result can be queued.")
        with self.db:
            changed = self.db.execute("INSERT INTO practice_plans (app_id,generation,capability,status,body,updated) SELECT ?,?,?,'ready',?,? WHERE EXISTS (SELECT 1 FROM apps WHERE id=? AND generation=? AND present=1) ON CONFLICT(app_id,generation,capability) DO UPDATE SET status='ready',body=excluded.body,error=NULL,retry_at=NULL,updated=excluded.updated WHERE practice_plans.status!='running' OR practice_plans.retry_at<=excluded.updated",
                                      (identity, generation, name, json.dumps(plan), now(), identity, generation))
        return changed.rowcount == 1

    def defer_practice_plan(self, identity, generation, capability, error, hours=24):
        if not any(cap["name"] == capability for cap in self.coverage(identity, generation)):
            return False
        retry = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
        with self.db:
            changed = self.db.execute("INSERT INTO practice_plans (app_id,generation,capability,status,error,retry_at,updated) VALUES (?,?,?,'deferred',?,?,?) ON CONFLICT(app_id,generation,capability) DO UPDATE SET status='deferred',error=excluded.error,retry_at=excluded.retry_at,updated=excluded.updated WHERE practice_plans.status!='running' OR practice_plans.retry_at<=excluded.updated",
                            (identity, generation, capability, str(error)[:1000], retry, now()))
        return changed.rowcount == 1

    def ready_practice_plan(self, identity, generation):
        coverage = {cap["name"]: cap for cap in self.coverage(identity, generation)}
        rows = self.db.execute("SELECT * FROM practice_plans WHERE app_id=? AND generation=? AND (status='ready' OR (status='running' AND retry_at<=?)) ORDER BY attempts,updated,capability", (identity, generation, now())).fetchall()
        rows.sort(key=lambda row: coverage.get(row["capability"], {}).get("observed_runs", 0))
        for row in rows:
            if row["capability"] in coverage and coverage[row["capability"]]["observed_runs"] < 2 and row["body"]:
                return json.loads(row["body"])
        return None

    def claim_practice_plan(self, identity, generation, capability):
        if not any(cap["name"] == capability and cap["observed_runs"] < 2 for cap in self.coverage(identity, generation)):
            return False
        timestamp = now()
        lease = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        with self.db:
            changed = self.db.execute("UPDATE practice_plans SET status='running',attempts=attempts+1,retry_at=?,updated=? WHERE app_id=? AND generation=? AND capability=? AND (status='ready' OR (status='running' AND retry_at<=?)) AND EXISTS (SELECT 1 FROM apps WHERE id=? AND generation=? AND present=1)",
                                      (lease, timestamp, identity, generation, capability, timestamp, identity, generation))
        return changed.rowcount == 1

    def finish_practice_plan(self, identity, generation, record):
        capability = record.get("capability_name")
        if not any(cap["name"] == capability for cap in self.coverage(identity, generation)):
            return False
        if record.get("outcome") in ("result_observed", "visual_result_assessed") and record.get("actions_executed", 0) < 1:
            record = {**record, "outcome": "observed_without_execution"}
        self.record_practice(identity, generation, record)
        success = self.save_workflow(identity, generation, record)
        retry = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
        with self.db:
            self.db.execute("UPDATE practice_plans SET status=?,error=?,retry_at=?,updated=? WHERE app_id=? AND generation=? AND capability=?",
                            ("tested" if success else "deferred", None if success else record.get("outcome", "error"), retry, now(), identity, generation, capability))
        return success

    def learning_overview(self):
        apps = self.apps()
        summary = {"apps_detected": len(apps), "apps_documented": 0, "apps_queued": 0, "apps_research_deferred": 0, "apps_researching": 0,
                   "documented_capabilities": 0, "capabilities_tested_once": 0, "capabilities_tested_repeatedly": 0,
                   "capabilities_visually_assessed": 0, "capabilities_without_observed_test": 0, "experiments_ready": 0,
                   "experiments_deferred": 0, "initial_documentation_complete": False, "documentation_rounds": 0}
        for app in apps:
            summary["apps_documented"] += bool(app["blueprint"])
            summary["apps_queued"] += app["status"] == "queued"
            summary["apps_research_deferred"] += app["status"] == "research_failed"
            summary["apps_researching"] += app["status"] == "researching"
            if app["blueprint"]:
                summary["documentation_rounds"] += self.setting(f"documentation:{app['id']}:{app['generation']}", {}).get("rounds", 1)
            coverage = self.coverage(app["id"], app["generation"])
            summary["documented_capabilities"] += len(coverage)
            summary["capabilities_tested_once"] += sum(cap["observed_runs"] > 0 for cap in coverage)
            summary["capabilities_tested_repeatedly"] += sum(cap["observed_runs"] >= 2 for cap in coverage)
            summary["capabilities_visually_assessed"] += sum(cap["visual_assessments"] > 0 for cap in coverage)
            summary["capabilities_without_observed_test"] += sum(cap["observed_runs"] == 0 for cap in coverage)
        for row in self.db.execute("SELECT p.status,COUNT(*) FROM practice_plans p JOIN apps a ON a.id=p.app_id AND a.generation=p.generation AND a.present=1 GROUP BY p.status"):
            if row[0] == "ready":
                summary["experiments_ready"] += row[1]
            elif row[0] == "deferred":
                summary["experiments_deferred"] += row[1]
        summary["initial_documentation_complete"] = bool(apps) and summary["apps_documented"] == len(apps)
        return summary
