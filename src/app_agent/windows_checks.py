"""Real Windows checks. Calculator smoke requires no cloud credential."""
import importlib.util
import os
import re
import subprocess
import sys
import threading
import time
from .desktop import WindowsDesktop, foreground_window


class CalculatorDetectionError(RuntimeError):
    def __init__(self, message, details):
        super().__init__(message)
        self.details = details


def doctor():
    report = {"platform": sys.platform, "python": sys.version.split()[0],
              "api_key_present": bool(os.getenv("AGENT_API_KEY") or os.getenv("OPENAI_API_KEY")),
              "dependencies": {name: importlib.util.find_spec(name) is not None
                               for name in ("tkinter", "pywinauto", "sounddevice", "numpy")}}
    if sys.platform == "win32" and report["dependencies"]["pywinauto"]:
        try:
            report["visible_windows"] = len(WindowsDesktop.windows())
        except Exception as error:
            report["desktop_error"] = str(error)
    return report


def calculator_smoke(cancel=None):
    if sys.platform != "win32":
        raise RuntimeError("Calculator smoke test requires Windows.")
    cancel = cancel or threading.Event()
    if cancel.is_set():
        raise RuntimeError("Calculator test stopped.")
    subprocess.Popen(["calc.exe"])
    desktop = None
    deadline = time.monotonic() + 45
    candidates = {}
    mode_attempted = set()
    unrelated = set()
    required = {"num2Button", "CalculatorResults", "equalButton", "plusButton", "minusButton", "divideButton"}
    while time.monotonic() < deadline:
        if cancel.is_set():
            raise RuntimeError("Calculator test stopped.")
        windows = sorted(WindowsDesktop.windows(), key=lambda item: item[1].casefold() != "calculator")
        for handle, title in windows:
            if cancel.is_set():
                raise RuntimeError("Calculator test stopped.")
            if handle in unrelated and title.casefold() != "calculator":
                continue
            try:
                candidate = WindowsDesktop(handle)
                observation = candidate.observe()
            except Exception as error:
                if title.casefold() == "calculator":
                    candidates[handle] = {"window_handle": handle, "accessibility_error": str(error)}
                continue
            ids = {control["automation_id"] for control in observation["controls"]
                   if control.get("visible", True) and control.get("enabled", True)}
            recognizable = {"num2Button", "CalculatorResults"} <= ids
            if recognizable or title.casefold() == "calculator":
                candidates[handle] = {"window_handle": handle, "control_count": len(observation["controls"]),
                                      "control_limit_reached": len(observation["controls"]) >= 251,
                                      "automation_ids": sorted(identity for identity in ids if identity),
                                      "missing_required_ids": sorted(required - ids),
                                      "standard_mode_attempted": handle in mode_attempted}
            else:
                unrelated.add(handle)
            if required <= ids:
                desktop = candidate
                break
            # Calculator can reopen in a converter or another non-arithmetic
            # view. Alt+1 selects Standard; never send it to a browser or editor.
            known_frame = title.casefold() == "calculator" and candidate.window.class_name() in {
                "ApplicationFrameWindow", "Windows.UI.Core.CoreWindow", "WinUIDesktopWin32WindowClass"}
            if (recognizable or known_frame) and handle not in mode_attempted:
                candidate.window.set_focus()
                if cancel.is_set() or foreground_window() != handle:
                    candidates[handle]["mode_error"] = "Calculator did not receive foreground focus; no shortcut sent."
                    continue
                candidate.window.type_keys("%1", set_foreground=False)
                mode_attempted.add(handle)
                candidates[handle]["standard_mode_attempted"] = True
                cancel.wait(0.25)
                break  # Re-read this preferred Calculator after mode changes.
        if desktop:
            break
        cancel.wait(0.25)
    if desktop is None:
        raise CalculatorDetectionError("Calculator arithmetic controls unavailable after startup and Standard-mode recovery. See recorded control diagnostics.",
                                       {"calculator_candidates": list(candidates.values())[:8], "startup_timeout_seconds": 45})

    def press(automation_id):
        if cancel.is_set():
            raise RuntimeError("Calculator test stopped.")
        observation = desktop.observe()
        matches = [control for control in observation["controls"] if control["automation_id"] == automation_id]
        if len(matches) != 1:
            raise RuntimeError(f"Calculator control unavailable: {automation_id}")
        target = matches[0]
        kind = next((kind for kind in ("invoke", "click") if kind in target.get("actions", [])), None)
        if kind is None:
            raise RuntimeError(f"Calculator button exposes no supported action: {automation_id}")
        desktop.act({"kind": kind, "target": target["id"]})
        cancel.wait(0.15)

    checks = []
    for sequence, expected in ((["num2Button", "num3Button", "plusButton", "num1Button", "num9Button", "equalButton"], "42"),
                               (["num8Button", "divideButton", "num2Button", "equalButton"], "4"),
                               (["num9Button", "minusButton", "num3Button", "equalButton"], "6")):
        ids = {control["automation_id"] for control in desktop.observe()["controls"]}
        if "clearButton" in ids:
            press("clearButton")
        else:
            # Esc is Calculator's clear-all shortcut. Send only to its window.
            desktop.window.set_focus()
            if cancel.is_set() or foreground_window() != desktop.window.handle:
                raise RuntimeError("Calculator did not receive focus; no clear shortcut sent.")
            desktop.window.type_keys("{ESC}", set_foreground=False)
            cancel.wait(0.15)
        for button in sequence:
            press(button)
        observation = desktop.observe()
        result = next(control["name"] for control in observation["controls"] if control["automation_id"] == "CalculatorResults")
        numbers = re.findall(r"\d+", result)
        if not numbers or numbers[-1] != expected:
            raise RuntimeError(f"Calculator result mismatch: expected {expected}, observed {result!r}")
        checks.append({"expected": expected, "observed": result, "passed": True})
    return {"checks": checks, "passed": len(checks),
            "window_handle": desktop.window.handle, "process_id": desktop.window.process_id(),
            "note": "Calculator remains open; its current calculation was changed."}
