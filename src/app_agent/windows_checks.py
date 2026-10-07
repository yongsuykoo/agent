"""Real Windows checks. Calculator smoke requires no cloud credential."""
import importlib.util
import os
import re
import subprocess
import sys
import time
from .desktop import WindowsDesktop


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


def calculator_smoke():
    if sys.platform != "win32":
        raise RuntimeError("Calculator smoke test requires Windows.")
    subprocess.Popen(["calc.exe"])
    desktop = None
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        for handle, title in WindowsDesktop.windows():
            candidate = WindowsDesktop(handle)
            observation = candidate.observe()
            ids = {control["automation_id"] for control in observation["controls"]}
            if {"num2Button", "CalculatorResults", "clearButton"} <= ids:
                desktop = candidate
                break
        if desktop:
            break
        time.sleep(0.25)
    if desktop is None:
        raise RuntimeError("Calculator standard controls not found. Open Calculator in Standard mode and retry.")

    def press(automation_id):
        observation = desktop.observe()
        matches = [control for control in observation["controls"] if control["automation_id"] == automation_id]
        if len(matches) != 1:
            raise RuntimeError(f"Calculator control unavailable: {automation_id}")
        desktop.act({"kind": "invoke", "target": matches[0]["id"]})
        time.sleep(0.15)

    checks = []
    for sequence, expected in ((["num2Button", "num3Button", "plusButton", "num1Button", "num9Button", "equalButton"], "42"),
                               (["num8Button", "divideButton", "num2Button", "equalButton"], "4"),
                               (["num9Button", "minusButton", "num3Button", "equalButton"], "6")):
        press("clearButton")
        for button in sequence:
            press(button)
        observation = desktop.observe()
        result = next(control["name"] for control in observation["controls"] if control["automation_id"] == "CalculatorResults")
        numbers = re.findall(r"\d+", result)
        if not numbers or numbers[-1] != expected:
            raise RuntimeError(f"Calculator result mismatch: expected {expected}, observed {result!r}")
        checks.append({"expected": expected, "observed": result, "passed": True})
    return {"checks": checks, "passed": len(checks), "note": "Calculator remains open; its current calculation was changed."}
