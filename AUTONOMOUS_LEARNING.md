# Autonomous learning campaign — 0.5.0

The goal is to discover software, study it without demonstrations, and learn to operate it through verified experiments. This release implements persistent research and experiment scheduling. It does not certify full understanding of every app.

## Start on Windows

1. Close the old agent. Download the GitHub ZIP, extract into a new folder, run `windows\Setup.cmd`, then `windows\Start.cmd`. Confirm **0.6.1** in the current title. Existing memory under `%LOCALAPPDATA%\AppAgent` is retained. For cloud-directed testing instead, see [WINDOWS_CONNECTION.md](WINDOWS_CONNECTION.md) and start Connect.cmd with the normal agent closed.
2. Enter your API key in the masked startup prompt. Click **Learn all apps**, then leave the agent open. This enables up to **50 app research attempts and 50 experiment designs per local day**. These use paid provider calls; one app study can make several calls. Lower the visible Daily app limit and click **Apply / resume** to reduce both budgets. Failed requests count.
3. Enable **Auto-practice Calculator** and accept its scope for arithmetic experiments. For another app, open disposable data, select the app in **Apps & knowledge**, and use **Grant practice on specific controls…**. This is permission; you do not teach a procedure or supply a task. The agent designs experiments from documentation.
4. Background practice uses these permissions and shares **three attempts per local day across apps**, with at most 24 planning steps per attempt. **Practice app** can also run a prepared experiment with task/step approval; manual practice is separate from that background budget.

Campaign settings and budgets survive restart; generic control grants do not. A key entered in the GUI stays in process memory and must be entered again after restart unless supplied through your local environment. Calculator's explicitly enabled practice setting persists. STOP pauses learning and revokes generic grants; Apply / resume restarts study. There is no Windows service: learning runs while the agent is open.

## Research and execution

- Scans registered desktop, Start-menu and Store apps every five minutes. New apps are queued; a version change invalidates current documentation and experiments.
- Searches cited public manuals, retrieves HTML/text pages, and extracts sourced operations, prerequisites, inputs, troubleshooting and recovery steps.
- Studies up to five apps and prepares up to three experiments per maintenance cycle, within daily budgets. After initial documentation is covered, it searches additional manuals for missing workflows and technical details. Studies adding capabilities become eligible after a day; no-growth studies wait seven days.
- Persists experiments, exclusive execution leases, outcomes and retries. Unsupported experiments wait a day. Completed practice waits six hours before a new experiment for that capability. Cloud authentication/quota failures pause campaign retries for at least fifteen minutes.
- Attempts documented, model-classified disposable tasks through permitted controls. Model risk classification is not a sandbox guarantee. Other windows, new controls, password fields and coordinate clicks do not inherit generic grants.
- Reobserves the window, verifies expected output, and saves successful version-specific workflows. It aims for two observed execution runs per documented capability before prioritizing others. Two runs are evidence of those experiments, not exhaustive coverage.

Research never calls desktop APIs. Native control stays on its existing automation worker. Experiments can take focus and occupy that worker; use STOP before unrelated desktop work during an experiment.

## Evidence and reports

The main window shows documented apps, capabilities with observed tests, and ready experiments. **Apps & knowledge** shows per-capability counts, queued/deferred plans, errors and saved workflows. Visual assessments are separate. Merely seeing a pre-existing correct result does not verify a practice capability.

`%LOCALAPPDATA%\AppAgent\learning-report.json` stores the latest campaign-cycle report. Session evidence and the catalog remain local. For newer counts after practice, query the live catalog:

```powershell
.venv\Scripts\python.exe -m app_agent.cli learning-report
# One documentation/planning cycle; does not operate apps:
.venv\Scripts\python.exe -m app_agent.cli study-campaign --daily-limit 50 --max-apps 5 --max-plans 3
```

A zero-change inventory log means the installed-app list is unchanged. `daily_limit` means the selected research budget is used; it resumes the next local day. Neither means all software has been learned.

## Validation and remaining work

Regression tests cover persistent queues/budgets, restart recovery, app changes, exclusive claims, cancellation, cloud throttling, fair scheduling, deeper research preserving evidence, scoped practice, and zero-action/visual evidence distinctions. A simulated unfamiliar editor uses documentation and a grant without a demonstration. UI tests cover chat availability during research and manual reuse of queued experiments.

The uploaded **0.4.6** Windows report passed all 12 native/model Notepad and Calculator checks. **0.5.0 Self-test adds a thirteenth check**: independently research Notepad documentation into an isolated catalog, generate its own exact-text experiment, and run it through the persistent queue with permission limited to the disposable editor. It verifies the actual editor text and records documentation sources and capability evidence. This adds search/model usage charges. Missing cloud credentials skip this check; unavailable documentation or a failed experiment is reported as failure without hiding earlier results.

The **0.5.0** campaign and new self-test still need live Windows validation. Simulations cannot establish that unfamiliar real apps expose usable controls or that a live model will plan correctly. You do not need to enter a Notepad command: click **Self-test** to run the checks automatically.

Portable/unregistered software is not comprehensively detected. PDF/JavaScript-only manuals, private documentation, arbitrary binary reverse engineering, app-specific API/CLI execution, automatic disposable workspaces for arbitrary apps, multi-app workflows, and unattended system repairs are not implemented. Documenting an API does not make it executable by this controller. Voice stages a transcript for chat execution. Troubleshooting suggests tests; applying a fix requires an authorized task. These remain parts of the full goal.
