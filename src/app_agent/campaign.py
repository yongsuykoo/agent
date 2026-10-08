"""Persistent cross-app study and capability experiments within existing grants."""
import re
import json
from datetime import datetime, timedelta, timezone

from .app_practice import consume_practice_budget
from .learning import deepen_next, practice_task
from .runner import TaskRunner


def cloud_blocked(error):
    return bool(re.search(r"HTTP (?:401|403|429)\b|needs AGENT_API_KEY", str(error)))


def consume_planning_budget(catalog, limit):
    return catalog.consume_budget("planning_budget", limit) is not None


def prepare_next_experiment(catalog, app, cloud, emit, daily_limit=50, cancel=None):
    capability = catalog.next_practice_capability(app["id"], app["generation"])
    if capability is None:
        return {"status": "no_ready_capability"}
    if cancel is not None and cancel.is_set():
        return {"status": "cancelled"}
    if not consume_planning_budget(catalog, daily_limit):
        return {"status": "planning_daily_limit"}
    emit(f"Designing an experiment for {app['name']}: {capability}")
    try:
        plan = practice_task(app["blueprint"], cloud, catalog.workflows(app["id"], app["generation"]), capability_name=capability, cancel=cancel)
        if cancel is not None and cancel.is_set():
            return {"status": "cancelled"}
        if not catalog.save_practice_plan(app["id"], app["generation"], plan):
            return {"status": "app_changed"}
        return {"status": "experiment_ready", "app": app["name"], "capability": capability}
    except Exception as error:
        if cancel is not None and cancel.is_set():
            return {"status": "cancelled"}
        catalog.defer_practice_plan(app["id"], app["generation"], capability, error)
        emit(f"Experiment deferred for {app['name']} / {capability}: {error}")
        return {"status": "cloud_blocked" if cloud_blocked(error) else "experiment_deferred", "error": str(error)}


def study_campaign(catalog, cloud, emit, daily_limit=50, max_apps=5, max_plans=3, cancel=None, research_workers=3):
    if any(type(value) is not int for value in (daily_limit, max_apps, max_plans, research_workers)) or daily_limit < 0 or not 0 <= max_apps <= 50 or not 0 <= max_plans <= 50 or not 1 <= research_workers <= 4:
        raise ValueError("Zero daily usage is uncapped; batches are 0–50 and parallel workers 1–4.")
    previous = catalog.setting("campaign_state", {})
    timestamp = datetime.now(timezone.utc).isoformat()
    if previous.get("retry_at") and previous["retry_at"] > timestamp:
        return {"status": "waiting_for_cloud_retry", "overview": catalog.learning_overview()}
    research, planning = [], []
    status = "progress"
    from .parallel_study import study_batch
    from .installation_watch import study_preview
    preview=study_preview(catalog,cloud,emit,daily_limit,cancel) if max_apps else {'status':'no_candidate'}
    attempted=preview['status'] in ('preview_documented','preview_failed')
    if attempted:research.append(preview)
    if preview['status']=='cancelled' or cloud_blocked(preview.get('error','')):
        status='cancelled' if preview['status']=='cancelled' else 'cloud_blocked'
    else:
        batch,status=study_batch(catalog,cloud,emit,daily_limit,max_apps-int(attempted),research_workers,cancel)
        research.extend(batch)
        if attempted and status=='queue_empty':status='progress'
    if status == "queue_empty" and max_apps:
        result = deepen_next(catalog, cloud, emit, daily_limit, cancel)
        research.append(result)
        status = "cloud_blocked" if cloud_blocked(result.get("error", "")) else result['status']
    if status not in ("cancelled", "cloud_blocked"):
        priority = set(catalog.setting("priority_apps", []))
        for _ in range(max_plans):
            if cancel is not None and cancel.is_set():
                status = "cancelled"
                break
            counts = {(row[0], row[1]): row[2] for row in catalog.db.execute(
                "SELECT app_id,generation,COUNT(*) FROM practice_plans GROUP BY app_id,generation")}
            apps = sorted(catalog.apps(), key=lambda app: (app["id"] not in priority,
                           counts.get((app["id"], app["generation"]), 0), not bool(app.get("app_id")), app["name"].casefold()))
            candidate = next((app for app in apps if app.get('role') != 'platform' and app["blueprint"] and catalog.next_practice_capability(app["id"], app["generation"])), None)
            if candidate is None:
                break
            result = prepare_next_experiment(catalog, candidate, cloud, emit, daily_limit, cancel)
            planning.append(result)
            if result["status"] in ("cancelled", "cloud_blocked"):
                status = result["status"]
                break
            if result["status"] == "planning_daily_limit":
                break
    overview = catalog.learning_overview()
    if status in ("queue_empty", "documentation_wait") and overview["apps_research_deferred"]:
        status = "research_retry_wait"
    if status in ("queue_empty", "documentation_wait") and planning:
        status = "progress"
    report = {"status": status, "updated": datetime.now(timezone.utc).isoformat(),
              "research": research, "planning": planning, "overview": overview}
    if status == "cloud_blocked":
        report["retry_at"] = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    catalog.set_setting("campaign_state", report)
    output = catalog.data_dir / "learning-report.json"
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary.replace(output)
    emit(f"Learning campaign: {overview['apps_documented']}/{overview['apps_detected']} apps documented; "
         f"{overview['capabilities_tested_once']}/{overview['documented_capabilities']} capabilities have observed tests; "
         f"{overview['experiments_ready']} experiments ready.")
    emit(f"Learning report: {output}")
    return report


def practice_one(catalog, app, cloud, desktop, approve, emit, data_dir, cancel=None, daily_limit=50, practice_limit=3, max_steps=24):
    if cancel is not None and cancel.is_set():
        return {"status": "cancelled"}
    plan = catalog.ready_practice_plan(app["id"], app["generation"])
    if plan is None:
        prepared = prepare_next_experiment(catalog, app, cloud, emit, daily_limit, cancel)
        if prepared["status"] != "experiment_ready":
            return prepared
        plan = catalog.ready_practice_plan(app["id"], app["generation"])
    if plan is None or not consume_practice_budget(catalog, practice_limit):
        return {"status": "practice_daily_limit"}
    if not catalog.claim_practice_plan(app["id"], app["generation"], plan["capability_name"]):
        return {"status": "experiment_already_claimed"}
    emit(f"Independent experiment in {app['name']} / {plan['capability_name']}: {plan['task']}")
    record = TaskRunner(desktop, cloud, approve, emit, data_dir, cancel).run(
        plan["task"], app["blueprint"], max_steps=max_steps,
        previous_workflows=catalog.workflows(app["id"], app["generation"]), required_result_text=plan["expected_result"])
    record["capability_name"] = plan["capability_name"]
    saved = catalog.finish_practice_plan(app["id"], app["generation"], record)
    return {"status": "experiment_observed" if saved else "experiment_failed", "app": app["name"],
            "capability": plan["capability_name"], "outcome": record["outcome"], "actions_executed": record["actions_executed"]}
