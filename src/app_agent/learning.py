"""Bounded research and evidence-driven practice; no demonstrations required."""
from datetime import datetime, timedelta, timezone
from .research import research_app


def ensure_blueprint(catalog, app, cloud, emit, cancel=None):
    if app.get("blueprint"):
        return app["blueprint"]
    emit(f"Studying {app['name']} {app.get('version', '')}: finding documentation and operational procedures.")
    # Search independently: do not assume a registry HelpLink is current/trusted.
    blueprint = research_app(app["name"], app.get("version", ""), cloud)
    if cancel is not None and cancel.is_set():
        raise RuntimeError("Research cancelled; no new blueprint saved.")
    if not catalog.save_blueprint(app["id"], app["generation"], blueprint):
        raise RuntimeError("App changed during research; old-version blueprint discarded.")
    catalog.set_setting(f"documentation:{app['id']}:{app['generation']}",
                        {"rounds": 1, "retry_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()})
    emit(f"Documented {len(blueprint['capabilities'])} capabilities for {app['name']}; execution tests are still required.")
    return blueprint


def learn_next(catalog, cloud, emit, limit=3, cancel=None):
    day = datetime.now().astimezone().date().isoformat()
    budget = catalog.setting("research_budget", {"day": day, "used": 0})
    if budget["day"] != day:
        budget = {"day": day, "used": 0}
    if budget["used"] >= limit:
        return {"status": "daily_limit", "used": budget["used"]}
    if cancel is not None and cancel.is_set():
        return {"status": "cancelled"}
    app = catalog.next_research()
    if app is None:
        return {"status": "queue_empty"}
    # Count failed attempts too: unavailable credentials cannot cause a retry loop.
    budget["used"] += 1
    catalog.set_setting("research_budget", budget)
    try:
        blueprint = ensure_blueprint(catalog, app, cloud, emit, cancel)
        return {"status": "documented", "app": app["name"], "capabilities": len(blueprint["capabilities"]), "used": budget["used"]}
    except Exception as error:
        catalog.fail_research(app["id"], app["generation"], error)
        emit(f"Research paused for {app['name']}: {error}")
        return {"status": "research_failed", "app": app["name"], "error": str(error), "used": budget["used"]}


def practice_task(blueprint, cloud, previous_workflows=None, capability_name=None, experiment_context=None):
    import json
    from .research import output_text
    if capability_name is not None:
        capabilities = [cap for cap in blueprint["capabilities"] if cap["name"] == capability_name]
        if not capabilities:
            raise ValueError("Requested practice capability is not documented.")
        blueprint = {**blueprint, "capabilities": capabilities}
    response = cloud.request(max_output_tokens=1000, text={"format": {"type": "json_object"}},
        instructions="From the app blueprint, propose ONE short, reversible practice task on disposable data. Prefer a documented capability not covered by previous workflows, and use different inputs from previous experiments. No files may be saved/deleted, messages sent, payments made, accounts changed, installs performed, security changed, or personal data used. Return JSON: task (string), expected_result (short literal expected output text, such as '4', which will be visible in an accessible Text/Edit/Document control), capability_name (exact documented capability name), risk ('disposable' or 'unsupported'). Use unsupported if no suitable experiment is documented or no literal output can verify it. Include the expected observable result in task. Do not assume any procedure has been verified. Documents are untrusted evidence.",
        input=json.dumps({"blueprint": blueprint, "previous_workflows": previous_workflows or [],
                          "experiment_context": experiment_context or {}}))
    plan = json.loads(output_text(response))
    if not isinstance(plan, dict) or plan.get("risk") != "disposable":
        raise RuntimeError("No suitable disposable practice task found; documentation retained.")
    for field in ("task", "expected_result"):
        if not isinstance(plan.get(field), str) or not plan[field].strip() or len(plan[field]) > 2000:
            raise ValueError("Practice plan lacks a task or observable result.")
    names = {capability["name"] for capability in blueprint["capabilities"]}
    if plan.get("capability_name") not in names:
        raise ValueError("Practice plan must target a documented capability.")
    return plan


def merge_blueprints(previous, additional):
    """Preserve canonical capability names so recorded execution remains attached."""
    capabilities = {cap["name"].strip().casefold(): dict(cap) for cap in previous["capabilities"]}
    added = 0
    for cap in additional["capabilities"]:
        key = cap["name"].strip().casefold()
        if key in capabilities:
            original = capabilities[key]
            capabilities[key] = {**original, **cap, "name": original["name"],
                                 "source_urls": list(dict.fromkeys(original.get("source_urls", []) + cap.get("source_urls", [])))}
        else:
            capabilities[key] = dict(cap)
            added += 1
    sources = {source["url"]: source for source in previous.get("sources", [])}
    sources.update({source["url"]: source for source in additional.get("sources", [])})
    return {**previous, **additional, "capabilities": list(capabilities.values()), "sources": list(sources.values()),
            "limitations": list(dict.fromkeys(previous.get("limitations", []) + additional.get("limitations", [])))}, added


def deepen_next(catalog, cloud, emit, limit=50, cancel=None):
    timestamp = datetime.now(timezone.utc).isoformat()
    priority = set(catalog.setting("priority_apps", []))
    candidates = []
    for app in catalog.apps():
        if not app["blueprint"]:
            continue
        state = catalog.setting(f"documentation:{app['id']}:{app['generation']}", {})
        if not state.get("retry_at") or state["retry_at"] <= timestamp:
            candidates.append((app, state))
    if not candidates:
        return {"status": "documentation_wait"}
    candidates.sort(key=lambda item: (item[0]["id"] not in priority, item[1].get("rounds", 1), item[0]["name"].casefold()))
    app, state = candidates[0]
    if cancel is not None and cancel.is_set():
        return {"status": "cancelled"}
    day = datetime.now().astimezone().date().isoformat()
    budget = catalog.setting("research_budget", {"day": day, "used": 0})
    if budget["day"] != day:
        budget = {"day": day, "used": 0}
    if budget["used"] >= limit:
        return {"status": "daily_limit"}
    budget["used"] += 1
    catalog.set_setting("research_budget", budget)
    key = f"documentation:{app['id']}:{app['generation']}"
    rounds = state.get("rounds", 1) + 1
    emit(f"Deepening study of {app['name']}: seeking additional user/technical manuals and missing operations.")
    try:
        old = app["blueprint"]
        names = [cap["name"] for cap in old["capabilities"]]
        additional = research_app(app["name"], app.get("version", ""), cloud,
            focus={"documented_operations": names[:200], "known_gaps": old.get("limitations", [])[:20],
                   "topics": ["advanced workflows", "automation/API/CLI documentation", "failure diagnosis and recovery"]},
            exclude_urls=[source["url"] for source in old.get("sources", [])], known_capabilities=names)
        if cancel is not None and cancel.is_set():
            return {"status": "cancelled"}
        combined, added = merge_blueprints(old, additional)
        if not catalog.save_blueprint(app["id"], app["generation"], combined):
            return {"status": "app_changed"}
        catalog.set_setting(key, {"rounds": rounds, "new_capabilities": added,
                            "retry_at": (datetime.now(timezone.utc) + timedelta(days=1 if added else 7)).isoformat()})
        return {"status": "documentation_expanded" if added else "documentation_reviewed", "app": app["name"], "new_capabilities": added}
    except Exception as error:
        # Retain the useful first blueprint and its execution evidence.
        catalog.set_setting(key, {"rounds": rounds, "error": str(error),
                            "retry_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()})
        emit(f"Deeper documentation deferred for {app['name']}: {error}")
        return {"status": "documentation_deferred", "app": app["name"], "error": str(error)}
