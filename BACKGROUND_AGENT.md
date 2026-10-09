# Local background work — 0.13.0

The Windows agent can now continue saved autonomous goals without leaving the chat window open. A local worker runs in the logged-in Windows account. It shares the persistent goal queue, checkpoints, app catalog and STOP state with the GUI. It needs no Cloudflare connection for local work.

## Setup once

After `windows\Setup.cmd`, open `windows\Start.cmd` and choose **Background & schedules**. Enable **Start the background worker when I log in to Windows**. To make model calls after a restart, enter the provider key locally and enable **Remember this key encrypted for this Windows account**. Choose **Save settings**, then **Start worker now**. Close the agent window when you want the worker to take over. `windows\Worker.cmd` is an alternative foreground launcher.

Windows DPAPI encrypts the saved key for the current account. No plaintext key file, startup argument or cloud upload is created. This relies on Windows account security; it does not protect the key against code already running as that account. Environment credentials take precedence over the encrypted file. Moving to another account or computer requires configuring its own key. Login startup changes only this application's current-user `Run` value and needs no administrator privileges. Disabling the option removes that value; **Forget key** through the CLI removes the encrypted file.

The worker executes only tasks submitted with autonomous permission. It does not grant permission to older supervised tasks or invent new tasks. It waits while the GUI is open, Windows is locked, or recent input means the desktop has not been idle for five seconds. Availability is checked again at task checkpoints and before journaled writes. User activity after execution begins is not a guaranteed interruption mechanism: use **Ctrl+Alt+F12**, GUI **STOP**, or `app-agent pause-jobs` to pause work. Resume through **Saved goals → Resume safe jobs** or `app-agent resume-jobs`.

The worker watches registry/installer changes and performs periodic local inventory reconciliation. Documentation study is a separate opt-in setting; when enabled, it uses the existing parallel study pipeline and prioritizes submitted goals. The existing optional daily study budget remains configurable; **0 means uncapped**. This release adds no daily job cap. Provider requests still incur the provider's charges and quota limits. Cached verified recipes/plans avoid model calls when applicable; unfamiliar or changed tasks may need research and planning.

## Schedules

In **Background & schedules**, enter a goal in the chat task box, set the delay, optionally enable **Repeat at this interval**, and select **Schedule current task**. The schedule retains that exact task, autonomous mode and vision permission. A future occurrence selects the appropriate app at execution time; it does not preserve the current window selection. Supervised schedules wait for the GUI rather than executing in the background.

One schedule has at most one outstanding occurrence. Missed repeated slots coalesce into the latest due occurrence instead of replaying every missed action. A failure, cancellation or uncertain effect pauses automatic repetition. Pausing a schedule fences its active goal before subsequent actions, separately from the global queue pause. **Resume future runs** can resume a clean paused occurrence; after a clean failed recurring occurrence it starts future work only. It cannot replay an uncertain action. Cancellation preserves earlier evidence and prevents future runs.

CLI commands use the same local data folder as the GUI:

```text
app-agent remember-key
app-agent enable-startup
app-agent submit "Calculate 23 plus 19 and verify the result." --autonomous
app-agent schedule "Calculate 2 plus 2 and verify the result." --at 2026-10-10T09:00:00+08:00 --every-minutes 60 --autonomous
app-agent schedules
app-agent pause-schedule SCHEDULE_ID
app-agent resume-schedule SCHEDULE_ID
app-agent cancel-schedule SCHEDULE_ID
app-agent worker-status
app-agent disable-startup
app-agent forget-key
```

ISO timestamps require an explicit UTC offset or `Z`. Repetition intervals range from one minute to 31 days. Scheduling does not clear an existing STOP state. Missing or rejected credentials wait for a new key; provider/network failures retain the existing bounded retry rules. An interrupted unverified action remains `needs_review`, including after a Windows lock. This prevents blind duplication; it is not an exactly-once guarantee from external apps.

## Persistence and validation

Schedules and occurrence IDs are stored transactionally in `jobs.sqlite3`. OS-owned worker and GUI locks prevent duplicate instances for one data folder and release on process termination. The persistent desktop lease coordinates this worker and queued GUI tasks; it does not coordinate independently launched legacy remote helpers or third-party automation. `worker-status.json` contains states, process/job IDs and timestamps, with no task text or key. Detailed local queue/catalog evidence remains private user data.

All 410 cloud tests pass from both the repository and the freshly installed release wheel. New tests use real SQLite, actual process termination and a cached multi-app task through the durable runtime with simulated desktop/model adapters. Windows mutex, desktop availability, DPAPI and registry operations are exercised through simulated native bindings. Headless UI tests cover the settings and schedule controls. Native Windows login startup, real lock/unlock recovery and microphone-to-task operation have not been verified in this session. No live Windows helper is connected.

This worker reduces repeated manual restarts and task supervision. Discovery and documentation remain evidence about software; they do not prove mastery of every operation. Universal app coverage, advanced browser/mail workflows and repeated live reliability remain unfinished.
