# Persistent Windows goals — 0.11.0

Chat and transcribed voice tasks now enter a local persistent queue. The agent saves the original goal, task permissions, selected window/process when supplied, app-version plan, verified outputs, action journal and recovery state. Closing and reopening the standalone agent retains this work.

The design follows the persistent goals and executor separation discussed in the [Grok Bot overview](https://docs.x.ai/grok-bot/overview), [Meta Muse design](https://introducing.muse.ai/) and [OpenAI Dots announcement](https://openai.com/index/introducing-dots/). This release implements local job ownership; it does not embed those products or reproduce their infrastructure.

## Normal use

Run `windows\Start.cmd` after setup. Submit a goal through **Run task** or push-to-talk. **Saved goals** shows each goal's state, verified step count and exception detail. With autonomous mode enabled, actions within the submitted task follow the existing app/window checks without individual prompts. Safe queued tasks continue when the agent is idle, ahead of background practice and documentation study.

Closing the agent retains safe work for the next launch. **STOP** explicitly pauses the queue across restarts and cancels further task actions. **Saved goals → Resume safe jobs** reactivates safe paused work. **Cancel selected** prevents a late worker result from reactivating a cancelled goal. Starting a new Run task also resumes the safe queue.

The agent must be running on an interactive Windows desktop to execute GUI work. This release does not install an always-running service or replace the Cloudflare connection helper. API keys remain session-local; model calls still require the configured provider. Saved jobs do not contain API keys or controller private keys.

## Recovery rules

| Situation | Behavior |
| --- | --- |
| Restart before any action | Reuse the saved plan and continue. Confirmed process death allows prompt recovery; an unknown owner is protected by a ten-minute renewable lease. |
| Restart after a verified app step | Keep that output and proceed to the next app. Do not repeat the completed step. |
| Transient provider/network failure before a new action | Retry after increasing delays, up to five incident attempts. No daily job cap is imposed. |
| Missing/rejected provider credentials | Wait quietly for credentials; the next launch with a key makes one new attempt. |
| App/OS update before any action | Plan again against the current installation automatically. |
| App/OS update after a partial verified goal | Retain evidence and stop the stale plan. Do not repeat completed steps to rebuild it. |
| Crash/failure after dispatch but before step verification | Mark `needs_review`. Neither queue resume nor restart blindly dispatches that action again. |
| Restart after verified Photoshop exports | Read and verify the saved files again, without another render. Missing/changed files cannot be reported as completed. |
| Selected window/process replaced | Stop instead of attaching to another document. |

`needs_review` remains visible for inspection and cancellation; it has no force-replay button. After checking the actual app state, a user may cancel that goal and submit a new, explicit task. This conservative rule prevents this runtime's automatic retries from duplicating an uncertain send/print/click; it is not an exactly-once guarantee from external applications. Application-specific draft/message/print identifiers are still needed for more automatic recovery of external effects.

## Execution and persistence

`jobs.sqlite3` in the AppAgent data directory stores private local tasks and their evidence. A SQLite write-ahead action record is committed before an actuator call, including calls made by cached workflow replay. Successful dispatch alone does not clear it: a fresh result check and atomic step checkpoint do. File contents and hashes verify native Photoshop exports. Historical UI evidence establishes the planned visible output, not an independent semantic proof of arbitrary goals.

A fenced lease serializes persistent goals sharing that data directory. Ownership, STOP and cancellation are checked before further actions. The existing COM worker serializes foreground tasks and background practice inside the standalone UI. This does not coordinate arbitrary third-party automation or separately launched legacy connection helpers; avoid simultaneous controllers on one desktop.

Independent documentation reading remains parallel. Desktop actions remain serial because a logged-in desktop has one interactive state. This release adds no runtime dependencies and keeps the signed worker protocol compatible with host 0.7.0. Updating a worker wheel does not replace an old standalone UI: the 0.11.0 UI is required for the queue and Saved goals controls. Remote session grants still expire with their connection and are not promoted into permanent permissions.

CLI administration, without desktop actions or model calls:

```text
app-agent submit "Calculate 23 plus 19 and verify the result." --autonomous
app-agent jobs
app-agent pause-jobs
app-agent resume-jobs
app-agent cancel-job JOB_ID
```

`submit` queues the exact user goal; the Windows UI executes it when active. `--vision` authorizes window images for that goal. Without `--autonomous`, action approval remains supervised. The CLI does not automatically unpause an explicitly stopped queue. Job and checkpoint records are private user data; do not publish them in GitHub or support screenshots.

## Validation

Cloud tests cover real SQLite durability, actual child-process exit, cross-connection ownership, delayed retries, cancellation fencing, false-completion rejection and safe two-app continuation. Headless UI tests exercise typed tasks, voice submission, selected-window routing and startup queue continuation. Photoshop tests use real export fixtures with simulated COM/rendering. No new native Windows acceptance or paid-provider run is claimed by these tests.

Persistent jobs are a step toward ongoing responsibility. Reconnecting outbound control, schedules/event-triggered user goals, editable personal memory, broader structured Office/mail tools and universal app coverage remain additional work.
