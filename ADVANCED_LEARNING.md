# App controls and independent practice

Version 0.5.0 uses the persistent campaign in [AUTONOMOUS_LEARNING.md](AUTONOMOUS_LEARNING.md). Research and experiment design require no demonstrations. Execution requires permission for affected app controls.

## Supported controls

- Accessibility Invoke, editable values, selection, explicit toggle state, expand/collapse, scroll and bounded clicks.
- Native Windows Edit entry/readback when UI Automation omits patterns. Parent/process checks and password/read-only guards apply.
- Stable actions bound to observed automation IDs and/or control names. Conflicting identities and changed approval snapshots require replanning.
- Bounded recovery after unsupported actions or failed verification, with version-specific workflows retained as evidence.
- Optional per-task screenshots and coordinate clicks inside the selected window. Separate consent is required; generic background grants exclude coordinate clicks. Images may include overlapping windows. Visual completion is assessed separately from accessible-output verification.

## Permissions and outcomes

**Run task** and manual **Practice app** request step approval, with an option to authorize the remaining task. **Auto-practice Calculator** permits its arithmetic allowlist. **Apps & knowledge → Grant practice on specific controls…** permits selected, unambiguous controls in one existing window/process for the current app version. Generic grants end on STOP or restart. New controls and other windows are excluded.

Explicit `Type exactly:` and `Replace the document text with exactly:` commands require the whole editor value to match. General experiments require the plan's expected text before recording `result_observed`. This is narrower than a dedicated functional validator for every app. A result with no executed action does not verify a practice workflow.

Background experiments share three attempts per local day. A capability becomes eligible after six hours until it has two observed runs. Failed/unsupported operations remain visible as gaps. Controls can change data: grant them in disposable workspaces. Scope enforcement does not create a sandbox.

## Testing status

The 0.4.6 live Windows self-test passed all 12 named Notepad and Calculator checks. Version 0.5.0 adds simulated campaign and UI regressions; live campaign results remain required. Universal operation, unrestricted repairs and complete reverse engineering are unfinished.
