"""A small explicit sandbox grant; never expand it using model claims."""
import re


def calculator_app(app):
    return app.get("app_id", "").casefold() == "microsoft.windowscalculator_8wekyb3d8bbwe!app"


def calculator_action(action, observation):
    if action.get("kind") not in ("invoke", "click"):
        return False
    controls = observation["controls"]
    ids = {control.get("automation_id") for control in controls}
    if not {"CalculatorResults", "num2Button", "equalButton"} <= ids:
        return False
    target = next((item for item in controls if item["id"] == action.get("target")), None)
    if not target or target.get("type") != "Button":
        return False
    identity = target.get("automation_id", "")
    return bool(re.fullmatch(r"num[0-9]Button", identity)) or identity in {
        "clearButton", "clearEntryButton", "backSpaceButton", "plusButton", "minusButton",
        "multiplyButton", "divideButton", "equalButton", "decimalSeparatorButton", "negateButton"}
