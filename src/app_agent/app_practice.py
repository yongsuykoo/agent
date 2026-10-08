"""Session-only permissions for specific user-selected app controls."""


def control_identity(control):
    return (control.get("automation_id", ""), control["type"], control["name"])


def create_grant(app, observation, selected_ids):
    if not observation.get("window_handle") or not observation.get("process_id"):
        raise ValueError("Practice permission requires a known window and process.")
    controls = [control for control in observation["controls"] if control["id"] in selected_ids
                and control["id"] != 0 and not control.get("password") and control["enabled"] and control["visible"]]
    if len(controls) != len(set(selected_ids)) or not controls:
        raise ValueError("Select at least one available non-password control.")
    allowed = {control_identity(control): tuple(control.get("actions", [])) for control in controls}
    if len(allowed) != len(controls) or any(not actions for actions in allowed.values()):
        raise ValueError("Selected controls must be unambiguous and support actions.")
    return {"app_id": app["id"], "generation": app["generation"], "window_handle": observation["window_handle"],
            "process_id": observation["process_id"], "controls": allowed}


def grants_action(grant, action, observation):
    if observation.get("window_handle") != grant["window_handle"] or observation.get("process_id") != grant["process_id"]:
        return False
    target = next((control for control in observation["controls"] if control["id"] == action.get("target")), None)
    if not target or target.get("password") or not target["enabled"] or not target["visible"]:
        return False
    return action.get("kind") in grant["controls"].get(control_identity(target), ())


def consume_practice_budget(catalog, limit=3):
    return catalog.consume_budget("practice_budget", limit) is not None
