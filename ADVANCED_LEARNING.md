# Version 0.3.0: wider app controls and independent practice

The previous Windows run demonstrated autonomous Calculator practice. This release extends the architecture to unfamiliar apps. It does not claim that every app is now fully understood or supported.

## New capabilities

- Windows accessibility control now includes Invoke, editable values, selection, toggles with explicit desired state, expand/collapse, scroll, and bounded control-click fallback. Password controls are excluded. Editable document fallback escapes literal text so shortcut characters are not interpreted as arbitrary hotkeys.
- Observations include control actions, visible values, and selection/toggle/scroll state. After execution, the agent waits up to two seconds for observable change. Errors are fed into fresh planning with documentation recovery guidance; it stops after three action failures or repeated actions without observed effect.
- Optional selected-app screenshots support visual planning and coordinate clicks inside the selected window. Image coordinates are checked, resizing is detected, and approval is invalidated when the captured view changes. Screenshot bytes are sent to the model only after explicit per-task consent and are not saved to sessions. Image hashes are retained as evidence. Screen captures may contain overlapping windows: avoid confidential data.
- Screenshot-only completion is labeled `visual_result_assessed`, separately from accessible text/value matching (`result_observed`). A model's image assessment is weaker evidence than a dedicated functional validator.
- Practice tasks now identify a documented capability. Apps & knowledge reports observed runs, visual assessments, failed attempts, and untested capabilities separately. A successful test does not verify all features.
- Beyond Calculator, users can grant session-only permission for specific controls in one existing app window/process. The agent then creates and attempts a documented disposable task without demonstrations or per-step approval. Newly appearing controls, other windows/processes, password fields, and visual coordinate clicks do not inherit that grant.

## Windows test sequence

1. Download the current repository, extract to a new folder, and run windows/Setup.cmd, then windows/Start.cmd. Confirm the title shows 0.3.0. Existing catalog memory remains under LOCALAPPDATA/AppAgent.
2. Test the Calculator task again with screenshots off. Check that each executed action is followed by a state change and that the result is correct. The prior redundant Clear action should be less likely with the wait/check loop; Windows testing must confirm this.
3. Open a fresh disposable Notepad document. Select its window and request `Type exactly: Hello from my personal agent`. Approve the action or authorize that task. Do not use an existing document: value/text entry can replace its contents. Do not save the experiment.
4. For a less accessible app, enable `Use selected-app screenshots for visual control`, then run a short reversible task. Consent explains which images are shared. Start with per-action approval. The model must support image input. Visual-only completion remains a model assessment, not a guarantee.
5. For independent practice in another app, first open exactly one disposable window of that app. In Apps & knowledge select the app and click `Grant practice on specific controls…`. Choose only the controls you authorize. The grant is permission, not a demonstration of how to use them. Avoid controls that save, delete, send, purchase, install, or change account/security settings.
6. Leave background study enabled and the agent open. At the next maintenance pass it can generate an experiment from the documented blueprint and attempt it within that grant. Background practice is limited to three attempts per local day across apps, with at most one attempt per app version per day. Generic practice is capped at 12 steps. Unsupported controls or missing permissions stop the attempt.
7. Inspect capability coverage and session evidence. STOP revokes generic practice grants and pauses study. Grants also disappear on restart and cannot be used for a different app version.

## Remaining limits

This is still a Windows test release. Cloud tests use simulated Windows controls, images, and models. New control patterns, literal document input, screen capture, visual clicks, and generic practice require actual Windows acceptance testing. Different apps implement accessibility differently; unsupported dialogs and multi-app operations can still block tasks. Granting controls does not make experiments risk-free: use disposable data and review the scope.

Automatic discovery and research continue as described in LEARNING_RELEASE.md. Universal reliable operation, complete reverse engineering of closed-source apps, unrestricted background troubleshooting, and automatic safe sandbox creation for arbitrary software remain unresolved work. Progress is measured by per-capability evidence, not a claim of complete understanding.
