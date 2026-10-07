# Windows test release

The current version is 0.3.0. See ADVANCED_LEARNING.md for wider Windows control, recovery, visual mode, and practice grants. See LEARNING_RELEASE.md for discovery, monitoring, and background study. The newest additions require real Windows acceptance testing.

This is a supervised prototype ready for initial Windows testing, not a completed universal computer agent. It researches apps without demonstrations and attempts tasks through Windows accessibility controls. Each mutation requires approval. Apps with custom inaccessible controls, canvas interfaces, elevated windows, complex dialogs, or unsupported UI Automation patterns may block it.

## Quick start

1. Use Windows 10/11 with an interactive desktop, internet access, and Python 3.11 or newer from python.org. Include the Python launcher and Tcl/Tk when installing Python.
2. Extract the entire test kit to a writable folder. Do not run inside the ZIP.
3. Double-click `windows\Setup.cmd`. It creates a private Python environment, installs dependencies, and runs core tests.
4. Double-click `windows\Test.cmd`. This opens Calculator and checks `23 + 19 = 42`, `8 / 2 = 4`, and `9 - 3 = 6`. It clears the existing calculation and leaves Calculator open. No API key is required.
5. Double-click `windows\Start.cmd`. Enter an OpenAI API key in the masked prompt. It is kept in memory for that session, not saved to disk. Leaving it blank permits local inspection only. API usage is billed by the provider.
6. Open Calculator, select Standard mode, click Refresh windows, and select its window. Set the research name to Windows Calculator.
7. Click Research app. Confirm that the returned blueprint has real source URLs and capabilities marked `documented_unverified`. Apps & knowledge displays version-specific catalog blueprints.
8. Enter `Calculate 23 plus 19 and verify the result`, click Run task, consent to sharing the selected window's text, and review each proposed action before approving it. With no stored blueprint, Run researches the app first.

The command-line and PowerShell alternatives remain available in `windows`.

## Acceptance checklist

- Installation finishes and all core tests pass.
- The offline Calculator test reports three passed checks.
- Inspect window displays Calculator controls and automation IDs.
- Research completes with source-backed procedures, without demonstrations.
- Chat task displays 42 and reports `result_observed`. Check the actual screen yourself: a text match is supporting evidence, not proof of general correctness.
- Rejecting an action causes no click or text entry.
- STOP, Esc in the agent window, and global Ctrl+Alt+F12 prevent subsequent actions. An action already executing cannot be undone; an in-flight cloud request can take up to 90 seconds to return.
- Push-to-talk records only after consent. Finish recording transcribes the command into the chat box; it does not execute it. Recording automatically finishes after 55 seconds.
- Troubleshoot explains observations, possible causes, and reversible tests for your entered problem. To apply a suggested fix, request it as a task; every action still requires approval. It does not automatically change system settings.
- Session evidence is saved locally after task completion, cancellation, or failure.

## Data and boundaries

OpenAI receives app names, task text, public documentation, selected-window control text, and voice recordings when those features are used. Never select a window containing confidential information unless you authorize that sharing. No screen images or local documents are automatically uploaded. Research is not permission to execute documentation instructions.

Blueprints and task session evidence are stored under `%LOCALAPPDATA%\AppAgent`. Session records can contain sensitive text you typed or visible in the selected window. They are ordinary local files, not encrypted by the app. Close the agent and delete that folder to reset memory. Do not include it in support uploads without reviewing its contents.

The runner supports accessibility Invoke and Edit value patterns in one selected window. It has no model-supplied shell execution, installer, arbitrary file-editing, or automatic administrator elevation tools. A fixed read-only PowerShell script is used for OS app discovery. Button invocation can still change or delete app data: review approvals carefully and start with disposable data. Automatic app selection and launching use discovered Start-menu identities. Complex multi-app navigation, visual fallback, autonomous repair, model retraining, and universal app coverage remain future work.

## Troubleshooting setup

- Python unavailable: install Python 3.11+ and its launcher, reopen the folder, and rerun Setup.cmd.
- UI cannot start: check Tcl/Tk was included in Python installation.
- Missing microphone: enable Windows microphone access and select a working default input device. Chat remains available without audio.
- Cloud HTTP 401/403: check API key validity and model access. HTTP 429: check quota/rate limits. `AGENT_MODEL` defaults to `gpt-4.1`; a replacement must support Responses API, web search, and JSON output.
- Cloud HTTP 400: version 0.1.1 uses `web_search_preview` with automatic tool selection and reports the provider's message and rejected parameter. If it still fails, share that diagnostic text, never your API key. Live API compatibility cannot be confirmed without an authenticated request.
- Documentation unavailable: check internet access and the publisher's site. CLI `research --source https://...` can select a public HTML/text manual explicitly.
- Calculator not found: use Standard mode and a non-elevated interactive session. Close extra Calculator windows and rerun the test.
- A task reports blocked/error: retain the session evidence locally, inspect the selected window, and try a supported control. Do not disable Windows security or run the agent as administrator to bypass inaccessible apps.

Cloud validation: core, planner, adapter, and voice transport tests use simulated Windows/model/audio components. Public Calculator documentation retrieval was checked live. Actual Windows UI, microphone capture, global hotkey, and authenticated model requests require the Windows acceptance checks above.

## Updating the prototype

Version 0.1.3 fixes JSON-mode input validation for research extraction and desktop planning. It explicitly requests JSON in the input message, as required by the API. Thirty automated tests pass; authenticated end-to-end behavior still requires Windows testing.

Close the agent, download the current repository ZIP from GitHub, extract into a new folder, and rerun Setup.cmd then Start.cmd. App memory remains in `%LOCALAPPDATA%\AppAgent`. Version 0.1.1 includes improved API compatibility and detailed error reporting; its 27 automated tests passed in the cloud.

### Classic Notepad text entry (0.3.2)

Native Windows Edit controls now use a window- and process-checked Win32 adapter when UI Automation omits text-entry patterns. Password and read-only styles block writes. Inspect window should list `type` for the blank Notepad Text Editor, and subsequent observations read its text back. This path has simulated regression coverage; live Windows validation remains required.

### Exact text completion (0.3.3)

The session log now prints the submitted Task command. Explicit `Type exactly:` and `Replace the document text with exactly:` commands require the whole observed editor value to match the requested text. A premature finish is rejected and replanned, with a bounded verification failure if it repeats. General tasks still use model-selected expected results and do not have this deterministic exact-text guarantee.

### Windows setup test fix (0.3.4)

Desktop adapter unit tests now mock the native-edit boundary on every platform so fake window handles cannot reach ctypes Windows APIs. Setup.cmd distinguishes Python environment creation, dependency installation, and test failures. All 74 tests pass in cloud, and all 11 adapter tests pass with the Windows platform branch simulated and native package imports blocked. Actual Windows Setup.cmd validation remains a local test.
# Automatic self-test (0.4.0)

After setup, click **Self-test** in the agent. It reuses the API key already entered for that session. Alternatively, `windows\SelfTest.cmd` prompts for the key securely and runs the same suite. Leave the desktop untouched while the suite works. The GUI STOP button cancels remaining checks; an in-flight API request can take up to 90 seconds to return. Close no test windows during execution.

The suite checks runtime prerequisites, installed-app inventory, three Calculator calculations, a new disposable Notepad document, text entry, exact replacement, literal punctuation, Unicode, multiline text, and saving with independent disk verification. With a key, it also runs two model-driven Notepad tasks and one model-driven Calculator task. The model can type only into the fixture editor and invoke only approved arithmetic controls. Existing user documents are not selected. Calculator's current calculation changes. The test document remains open, and its files remain under `%LOCALAPPDATA%\AppAgent\self-tests`.

Every run saves `report.json` and model task session evidence under its own timestamped directory. Each check reports passed, failed, skipped, or cancelled. Missing cloud credentials produce skipped checks and an overall partial result. Failures do not prevent independent checks from running. These checks verify the named operations only; they do not certify every installed application's capabilities. No screenshot upload is used by this suite.

`windows\Test.cmd` runs the core regression tests and the native self-test without requesting a cloud key. GitHub Actions is configured to run simulated regression tests on Windows and Linux with Python 3.11 and 3.14. Hosted regression jobs do not run the interactive Windows suite or call a live model. A configured workflow is not evidence of a passed CI run.

### Updating an existing installation (0.4.1)

Close App Agent before setup. Setup reuses an existing Python environment instead of copying its running executable again. Start scripts launch the Python module directly so the console launcher app-agent.exe is not held open by the agent. An earlier failed pip uninstall may leave invalid-distribution warnings; extract into a fresh folder to recover without deleting the old installation or its data. A WinError 5 alone does not establish a need to run as administrator.

### Windows fixture newline fix (0.4.2)

The simulated Notepad save now writes literal line endings instead of asking Python to translate already-present CRLF sequences. The Windows failure was reproduced in cloud with Windows newline translation before the fix. All 86 tests pass afterwards, including an explicit regression that runs the complete simulated self-test suite under Windows newline translation. Live desktop results are still reported separately by Self-test.

### Windows report fixes (0.4.3)

The received live Windows report showed 9 passed and 3 failed checks: inventory, native Notepad editing, and both AI Notepad edits passed; Calculator native detection, Notepad save, and AI Calculator verification failed. The save check now calls the pointer-sized user32 GetForegroundWindow API directly. UIA pattern-availability probes use the correct 300xx property identifiers. The Calculator sandbox permits accessible clicks on the same arithmetic-only control allowlist. Native calculations no longer require clearButton: a focus-checked Escape clears Calculator when that ID is absent. AI calculation failures now include outcome, action count, display text and last step, with full session evidence retained. The API-key-present flag accounts for a key entered directly into the CLI client. All 90 cloud regression tests pass; the revised live Windows checks remain to be run.

### Reuse the tested Calculator window (0.4.4)

The latest received Windows report has 11 passed checks and one failure: AI Calculator selection was ambiguous with multiple Calculator windows. The native check now returns the window handle and process ID. The AI check reuses that exact fixture instead of scanning for a unique Calculator. A closed window or changed process is rejected without switching to another app. All 91 regression tests pass, including multiple-window and changed-process checks. Live confirmation of this final fix remains pending.

### Stable action identity and completion recovery (0.4.5)

The supplied Windows session trace showed the model describing Seven but selecting control 44 (Eight), leading to 18 + 28 = 46. It then returned unsupported success objects. Desktop planning now requests a strict JSON action schema. Control actions must identify the intended control with its observed automation ID and/or name; unique identities resolve the current numeric index, and conflicting/ambiguous identities are rejected. Numeric indexes alone are rejected for model actions. Failed completion checks feed a corrective error back to the planner, up to the bounded recovery limit. The AI Calculator test supplies an independent required result of 45 and binds numeric verification to CalculatorResults; it allows 24 planning steps so one full correction can fit. This does not guarantee that a live model will always choose the right identities or recover successfully. All 95 regression tests pass, including the actual Seven/Eight index mismatch, wrong-result recovery, and rejection of 145, -45, or 45.5 as 45. Reports now include the installed agent version.

### Calculator startup and mode recovery (0.4.6)

The 0.4.5 Windows report showed 10 passed checks, failed Calculator detection, and a correctly skipped AI Calculator check. It supplied no Calculator control diagnostics, so the cause is not proven. Native discovery now prioritizes Calculator windows, allows 45 seconds for startup, and inspects visible/enabled arithmetic controls. A recognized Calculator with missing arithmetic controls can be switched to Standard mode using foreground-checked Alt+1; English-titled Calculator frames have an additional known-class check, so a similarly titled browser is not sent shortcuts. Failed discovery persists candidate control IDs, missing required IDs, accessibility errors, mode-recovery status, and whether the observation control limit was reached. All 98 regression tests pass, including mode switching, rejecting unrelated windows, and preserving failed-check diagnostics. Actual Windows confirmation remains pending.

### Confirmed live Windows milestone (0.4.6)

The subsequently uploaded 0.4.6 report passed all 12 checks: zero failures, skipped checks or cancellations. Runtime was Windows with Python 3.14.0; inventory found 404 apps with no scan warnings. Native Calculator results were 42, 4 and 6. All Notepad editing and independent disk-save checks passed, both AI Notepad tasks executed and verified one edit each, and the AI Calculator task executed 7 actions and displayed 45. This confirms the interactive suite on that computer. It does not certify the remaining installed apps, voice input, all controls, or arbitrary troubleshooting. No further rerun of this suite is needed without a relevant code change or new failure.


### Persistent learning campaign (0.5.0)

See [AUTONOMOUS_LEARNING.md](AUTONOMOUS_LEARNING.md) for Learn all apps. The agent now batches documentation research, prepares per-capability experiments, retains retry queues across restarts, and searches additional manuals after initial coverage. Documentation runs separately from native automation. Manual Practice app reuses prepared experiments. Approval snapshots reject changed window handles/processes. These changes have simulated regression coverage; the new campaign has not been tested on an interactive Windows desktop in the cloud.

After updating to a fresh folder, starting the campaign begins research and planning. With Calculator permission or disposable-app control grants, the agent runs its own experiments and records outcomes; users do not enter procedures. Inspect Apps & knowledge and learning-report.json for coverage and failures. Existing Self-test remains the automatic native/model check. Provider calls incur usage charges. Completed documentation or two experiments do not establish full application mastery.

The 0.5.0 suite adds check 13, AI documentation-to-practice learning. It researches Notepad from scratch in an isolated test catalog, asks the model to choose documented text entry and generate its own exact-text experiment, queues/claims it, and permits typing only in the disposable fixture editor. It verifies actual editor contents and records sources and per-capability evidence. It never grants document saving, menus or other windows to that model task. This additional check incurs research/search/model charges; missing credentials skip it, and research/planning/execution failures are reported independently. The new live result is pending.

### Cloud-directed Windows testing (0.6.0)

[WINDOWS_CONNECTION.md](WINDOWS_CONNECTION.md) describes the locally launched Connect.cmd companion. After pairing, the controller can run self-tests and retrieve reports directly; users do not enter test commands or upload evidence manually. Other app tasks require specific local control grants. Real protocol/loopback HTTP tests pass in the cloud; native task execution in those regressions is simulated. WinGet installation, the outbound relay, and live desktop pairing remain pending. The prior 0.4.6 twelve-check live report remains valid evidence for that release; publishing a connection helper does not establish a newer live result.

### PowerShell execution-policy launcher fix (0.6.1)

The received Windows error showed Connect.ps1 blocked before the companion started. Connect.cmd now launches a Python bootstrap directly; no PowerShell execution-policy change is made. The bootstrap installs cloudflared through verified WinGet when needed and finds portable links or refreshed registry PATH values. All 154 cloud regression tests pass, including installer failures, stale PATH, and startup with spaces in the folder path. Live companion pairing remains pending.
