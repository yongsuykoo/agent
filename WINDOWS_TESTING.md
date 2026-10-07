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
