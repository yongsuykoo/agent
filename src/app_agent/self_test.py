"""Automatic Windows checks against disposable Notepad data and Calculator.

UIA calls stay on the caller's COM thread. Never use an existing user document.
"""
import json
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version

from .desktop import WindowsDesktop, foreground_window
from .runner import TaskRunner, exact_text_goal
from .practice_policy import calculator_action
from .windows_checks import calculator_smoke, doctor
from .discovery import scan_apps
from .catalog import Catalog
from .learning import ensure_blueprint, practice_task, PracticeUnavailable, merge_blueprints
from .research import research_app
from .campaign import practice_one
from .app_practice import create_grant, grants_action


class SkipCheck(RuntimeError):
    pass


def run_checks(checks, report_path, cancel, emit, *, scope=None):
    """Persist after each check; one failure does not hide independent results."""
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        package_version = version("app-agent")
    except PackageNotFoundError:
        package_version = "unknown"
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "checks": [],
              "agent_version": package_version,
              "report_path": str(report_path), "scope": scope or "Named automatic checks only; optional Office checks use fresh test files; not universal app certification"}
    for name, check in checks:
        if cancel.is_set():
            item = {"name": name, "status": "cancelled"}
        else:
            emit(f"Self-test: {name}")
            try:
                details = check()
                item = {"name": name, "status": "passed", "details": details}
            except SkipCheck as error:
                item = {"name": name, "status": "skipped", "reason": str(error)}
            except Exception as error:
                item = {"name": name, "status": "failed", "error": str(error)}
                if getattr(error, "details", None) is not None:
                    item["details"] = error.details
        report["checks"].append(item)
        report["counts"] = {status: sum(c["status"] == status for c in report["checks"])
                            for status in ("passed", "failed", "skipped", "cancelled")}
        counts = report["counts"]
        report["status"] = ("cancelled" if counts["cancelled"] else "failed" if counts["failed"]
                            else "partial" if counts["skipped"] else "passed")
        temporary = report_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(report_path)
        emit(f"Self-test {name}: {item['status']}" + (f" — {item.get('error') or item.get('reason')}" if item.get('error') or item.get('reason') else ""))
    emit(f"Self-test report: {report_path}")
    return report


def editor(observation):
    matches = [c for c in observation["controls"] if c["type"] in ("Edit", "Document")
               and c["visible"] and c["enabled"] and c.get("password") is False
               and "type" in c.get("actions", [])]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one editable document, found {len(matches)}; no text written.")
    return matches[0]


def wait_until(function, cancel, timeout=15):
    deadline = time.monotonic() + timeout
    while not cancel.is_set():
        value = function()
        if value:
            return value
        if time.monotonic() >= deadline:
            raise RuntimeError("Timed out waiting for the expected app state.")
        cancel.wait(0.2)
    raise RuntimeError("Self-test stopped.")


class NotepadFixture:
    def __init__(self, directory, cancel):
        self.path = Path(directory) / ("agent-self-test-" + uuid.uuid4().hex + ".txt")
        self.cancel = cancel
        self.desktop = None
        self.identity = None

    def open(self):
        self.path.write_text("", encoding="utf-8")
        subprocess.Popen(["notepad.exe", str(self.path)])
        def locate():
            matches = [(handle, title) for handle, title in WindowsDesktop.windows()
                       if self.path.stem.casefold() in title.casefold()]
            if len(matches) > 1:
                raise RuntimeError("Disposable Notepad window is ambiguous; refusing to automate.")
            if not matches:
                return None
            desktop = WindowsDesktop(matches[0][0])
            snapshot = desktop.observe()
            editor(snapshot)
            return desktop
        self.desktop = wait_until(locate, self.cancel)
        snapshot = self.desktop.observe()
        self.identity = (snapshot["window_handle"], snapshot["process_id"])
        return {"test_file": str(self.path), "window_handle": self.identity[0]}

    def observe(self):
        if self.cancel.is_set():
            raise RuntimeError("Self-test stopped.")
        if self.desktop is None:
            raise SkipCheck("Disposable Notepad fixture could not be opened.")
        snapshot = self.desktop.observe()
        if (snapshot["window_handle"], snapshot["process_id"]) != self.identity or self.path.stem.casefold() not in snapshot["window"].casefold():
            raise RuntimeError("Notepad fixture identity changed; refusing to automate.")
        return snapshot

    def approve(self, action, observation):
        current = self.observe()
        if self.cancel.is_set() or (observation.get("window_handle"), observation.get("process_id")) != self.identity:
            return False
        target = editor(current)
        return action.get("kind") == "type" and action.get("target") == target["id"]

    def replace(self, text):
        snapshot = self.observe()
        target = editor(snapshot)
        self.desktop.act({"kind": "type", "target": target["id"], "text": text})
        wait_until(lambda: editor(self.observe()).get("value") == text, self.cancel, timeout=5)
        return {"expected_text": text, "exact_match": True, "actions_executed": 1}

    def save(self):
        expected = editor(self.observe()).get("value")
        self.desktop.window.set_focus()
        if self.cancel.is_set() or foreground_window() != self.identity[0]:
            raise RuntimeError("Test window did not get foreground focus; no save shortcut sent.")
        # Save the already-created disposable file, never a user-selected path.
        self.desktop.window.type_keys("^s", set_foreground=False)
        def saved():
            raw = self.path.read_bytes()
            encoding = "utf-16" if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else "utf-8-sig"
            return raw.decode(encoding).replace("\r\n", "\n") == expected.replace("\r\n", "\n")
        wait_until(saved, self.cancel, timeout=5)
        return {"file": str(self.path), "disk_text_matches_editor": True}


def learning_experiment(fixture, cloud, run_dir, cancel, emit):
    """Research and practice from scratch using only the disposable editor."""
    if cloud is None:
        raise SkipCheck("Cloud reasoning not requested or no API key available.")
    fixture.observe()
    catalog = Catalog(Path(run_dir) / "learning-test")
    blueprint = None
    try:
        # This isolated identity is a test fixture, not a discovered app version.
        # Unknown version applicability must remain a documentation limitation.
        app = {"id": "fixture:notepad", "name": "Microsoft Windows Notepad", "version": "",
               "source": "self-test", "app_id": None}
        catalog.sync({"apps": [app], "complete_sources": ["self-test"]})
        current = catalog.get(app["id"])
        blueprint = ensure_blueprint(catalog, current, cloud, emit, cancel)
        observed_editor = editor(fixture.observe())
        context = {
            "workspace": "A new disposable Notepad test document",
            "permitted_actions": ["Replace document text using the existing editable control"],
            "observed_controls": [{key: observed_editor.get(key) for key in
                                   ("name", "type", "class_name", "automation_id", "actions", "enabled", "visible")}],
            "required_task_form": "Replace the document text with exactly: <your own short test text>",
            "verification": "expected_result must be exactly your chosen document text; choose a documented text-entry operation",
            "forbidden_actions": ["Save", "Open another document", "Invoke menus", "Change settings"]}
        try:
            plan = practice_task(blueprint, cloud, experiment_context=context, cancel=cancel)
        except PracticeUnavailable:
            if cancel.is_set():
                raise RuntimeError("Self-test stopped.")
            emit("No documented experiment fits the observed editor scope; studying additional documentation once.")
            options = {"focus": {"practice_scope": context, "purpose": "Find documented workflows applicable to these observed controls"},
                       "known_capabilities": [cap["name"] for cap in blueprint["capabilities"]]}
            if observed_editor.get("class_name") == "Edit" and "type" in observed_editor.get("actions", []):
                # A positively identified native control has its own public
                # technical reference; app-name searches can return a different
                # app version's AI features instead of applicable primitives.
                options["urls"] = ["https://learn.microsoft.com/en-us/windows/win32/controls/edit-controls",
                                   "https://learn.microsoft.com/en-us/windows/win32/controls/about-edit-controls"]
            else:
                options["exclude_urls"] = [source["url"] for source in blueprint.get("sources", [])]
            additional = research_app(app["name"], app["version"], cloud, **options)
            if cancel.is_set():
                raise RuntimeError("Self-test stopped.")
            blueprint, _ = merge_blueprints(blueprint, additional)
            if not catalog.save_blueprint(app["id"], current["generation"], blueprint):
                raise RuntimeError("App changed during follow-up study; no experiment executed.")
            plan = practice_task(blueprint, cloud, experiment_context=context, cancel=cancel)
        if cancel.is_set():
            raise RuntimeError("Self-test stopped.")
        if exact_text_goal(plan["task"]) != plan["expected_result"]:
            raise RuntimeError("Generated experiment must request exact editor text matching its expected result; no experiment executed.")
        # A pre-existing result cannot satisfy the experiment accidentally.
        fixture.replace("")
        current = catalog.get(app["id"])
        grant = create_grant(current, fixture.observe(), [editor(fixture.observe())["id"]])
        if not catalog.save_practice_plan(app["id"], current["generation"], plan):
            raise RuntimeError("Generated experiment could not be queued.")
        result = practice_one(catalog, current, cloud, fixture.desktop,
            lambda action, observation: fixture.approve(action, observation) and grants_action(grant, action, observation),
            emit, run_dir, cancel, max_steps=12)
        if (result["status"] != "experiment_observed" or result["outcome"] != "result_observed"
                or result["actions_executed"] < 1 or editor(fixture.observe()).get("value") != plan["expected_result"]):
            raise RuntimeError("Autonomous learning experiment failed: " + json.dumps(result))
        return {**result, "generated_task": plan["task"], "exact_match": True,
                "documentation_sources": [source["url"] for source in blueprint.get("sources", [])],
                "documented_capabilities": len(blueprint["capabilities"]), "overview": catalog.learning_overview()}
    except Exception as error:
        if blueprint is not None:
            error.details = {**getattr(error, "details", {}),
                             "documentation_sources": [source["url"] for source in blueprint.get("sources", [])],
                             "documented_capability_names": [cap["name"] for cap in blueprint["capabilities"]]}
        raise
    finally:
        catalog.close()


def self_test(data_dir, cloud=None, emit=print, cancel=None, with_voice=False, with_office=False):
    if sys.platform != "win32":
        raise RuntimeError("Live self-test needs an interactive Windows computer; cloud Linux cannot control your PC.")
    cancel = cancel or threading.Event()
    run_dir = Path(data_dir) / "self-tests" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    run_dir.mkdir(parents=True)
    fixture = NotepadFixture(run_dir, cancel)
    calculator_fixture = {}

    def native_calculator():
        details = calculator_smoke(cancel)
        calculator_fixture.update(window_handle=details["window_handle"], process_id=details["process_id"])
        return details

    def inventory():
        snapshot = scan_apps()
        catalog = Catalog(data_dir)
        try:
            changes = catalog.sync(snapshot)
        finally:
            catalog.close()
        if snapshot.get("warnings"):
            raise RuntimeError("Inventory scan incomplete: " + "; ".join(snapshot["warnings"]))
        if not snapshot["apps"]:
            raise RuntimeError("Inventory returned no installed apps.")
        return {"apps_detected": len(snapshot["apps"]), "changes": changes}

    def prerequisites():
        report = doctor()
        report["api_key_present"] = cloud is not None or report.get("api_key_present", False)
        if report.get("desktop_error") or not report.get("visible_windows") or not all(report["dependencies"].values()):
            raise RuntimeError("Interactive desktop prerequisites missing: " + json.dumps(report))
        return report

    def model_text(text):
        if cloud is None:
            raise SkipCheck("Cloud reasoning not requested or no API key available; native checks still run.")
        fixture.observe()
        result = TaskRunner(fixture.desktop, cloud, fixture.approve, emit, run_dir, cancel).run(
            "Replace the document text with exactly: " + text, max_steps=8, effect_timeout=1)
        if result["outcome"] != "result_observed" or editor(fixture.observe()).get("value") != text or result["actions_executed"] < 1:
            raise RuntimeError(f"Model-driven text task did not execute and verify the requested edit: {result['outcome']}.")
        return {"outcome": result["outcome"], "actions_executed": result["actions_executed"], "exact_match": True}

    def voice_command():
        if cloud is None:
            raise SkipCheck("Speech transcription requires the locally enabled cloud credential.")
        from .voice import synthetic_test_audio, transcribe
        phrase = "Replace the document text with exactly: Voice command verified"
        audio = synthetic_test_audio(run_dir / "voice-command.wav", phrase)
        if cancel.is_set():
            raise RuntimeError("Self-test stopped.")
        transcript = transcribe(audio)
        if not isinstance(transcript, str) or re.findall(r"\w+", transcript.casefold()) != re.findall(r"\w+", phrase.casefold()):
            raise RuntimeError("Speech transcript differs from the known test utterance; no editor action executed.")
        target = exact_text_goal(transcript)
        if target is None or cancel.is_set():
            raise RuntimeError("Speech command cannot be routed to the disposable editor; no action executed.")
        fixture.replace("")
        result = TaskRunner(fixture.desktop, cloud, fixture.approve, emit, run_dir, cancel).run(transcript, max_steps=8, effect_timeout=1)
        if result["outcome"] != "result_observed" or result["actions_executed"] < 1 or editor(fixture.observe()).get("value") != target:
            raise RuntimeError("Speech command did not execute and verify its exact editor output.")
        return {"audio_source": "Windows SAPI synthetic utterance; microphone not tested", "transcript": transcript,
                "exact_match": True, "actions_executed": result["actions_executed"], "outcome": result["outcome"]}

    def model_calculator():
        if cloud is None:
            raise SkipCheck("Cloud reasoning not requested or no API key available.")
        if not calculator_fixture:
            raise SkipCheck("The native Calculator check did not establish a test window; no other window is selected.")
        identity = (calculator_fixture["window_handle"], calculator_fixture["process_id"])
        desktop = WindowsDesktop(identity[0])
        observation = desktop.observe()
        if (observation.get("window_handle"), observation.get("process_id")) != identity or not {
                "CalculatorResults", "num2Button", "equalButton"} <= {c["automation_id"] for c in observation["controls"]}:
            raise RuntimeError("The tested Calculator window closed or changed identity; no other window is selected.")
        def approve(action, snapshot):
            return not cancel.is_set() and (snapshot["window_handle"], snapshot["process_id"]) == identity and calculator_action(action, snapshot)
        result = TaskRunner(desktop, cloud, approve, emit, run_dir, cancel).run(
            "Clear the current calculation. Calculate 17 plus 28 and verify the result is 45.", max_steps=24, effect_timeout=1,
            required_result_text="45", result_control_id="CalculatorResults")
        display = next(c["name"] for c in desktop.observe()["controls"] if c["automation_id"] == "CalculatorResults")
        if result["outcome"] != "result_observed" or re.findall(r"\d+", display)[-1:] != ["45"] or result["actions_executed"] < 1:
            last = next((entry.get("error") or entry.get("action", {}).get("reason") for entry in reversed(result["history"])
                         if entry.get("error") or entry.get("action")), "No planner action")
            raise RuntimeError(f"Model-driven Calculator failed: outcome={result['outcome']}, actions={result['actions_executed']}, display={display!r}, last step={last}. Full evidence: {run_dir / 'sessions.jsonl'}")
        return {"outcome": result["outcome"], "actions_executed": result["actions_executed"], "display": display}

    checks = [("runtime prerequisites", prerequisites), ("installed-app inventory", inventory),
              ("Calculator three native calculations", native_calculator), ("open disposable Notepad", fixture.open),
              ("Notepad native text entry", lambda: fixture.replace("Hello from my personal agent")),
              ("Notepad exact replacement", lambda: fixture.replace("My agent can operate Notepad.")),
              ("Notepad literal punctuation and Unicode", lambda: fixture.replace("Literal + ^ % {braces} (text) — 你好")),
              ("Notepad multiline text", lambda: fixture.replace("First line\r\nSecond line")),
              ("Notepad save and disk verification", fixture.save),
              ("AI Notepad text replacement", lambda: model_text("The agent ran its own Windows test.")),
              ("AI Notepad second distinct task", lambda: model_text("Autonomous replacement verified.")),
              ("AI Calculator task", model_calculator),
              ("AI documentation-to-practice learning", lambda: learning_experiment(fixture, cloud, run_dir, cancel, emit))]
    if with_voice:
        checks.append(("AI synthetic speech-to-editor command", voice_command))
    if with_office:
        from .office_checks import office_smoke
        checks.extend(("Native "+family+" file creation and content verification",
                       lambda family=family:office_smoke(data_dir,run_dir,family,cancel)) for family in ('excel','word'))
        emit("Optional Office tests create new Excel/Word files and leave those test documents open. Existing user documents are not edited. No provider calls for Office checks.")
    emit("Self-test uses a new disposable Notepad file and clears Calculator. Please leave the desktop untouched until it finishes. STOP cancels remaining checks.")
    report = run_checks(checks, run_dir / "report.json", cancel, emit)
    emit("Self-test complete. The disposable Notepad file and session evidence remain in " + str(run_dir))
    return report
