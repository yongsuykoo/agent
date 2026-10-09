# Unattended sessions

Version 0.23.0 adds a durable, bounded unattended session. It can run for any positive duration up to ten hours, records its deadline and phase in `unattended.sqlite3`, and resumes after a worker restart. A watchdog starts the worker, backs off after failures, and restarts it while the session is active. At the deadline it stops and leaves the queue and evidence on disk.

Use the Windows launcher `windows\Worker.cmd`, or run:

```text
app-agent start-unattended --hours 10
app-agent unattended-status
app-agent stop-unattended
```

The command enables current-account login startup so a reboot or later login can recover the session. Pass `--no-login-startup` when that is not wanted. The provider key remains in the existing encrypted per-user storage; it is never written to startup commands, status files, session rows or logs.

The worker automatically retries transient worker exits with backoff and does not repeat an uncertain desktop action. Documentation learning is read-only and may proceed while Windows is locked if background study is enabled and a provider key is configured. Installation scans and desktop operations wait for an unlocked interactive desktop. The GUI remains a separate lock, and STOP/pause fences the next action. The session deadline is shared by research and action cancellation checkpoints.

This is bounded unattended operation, not a guarantee that every task completes in ten hours. Provider quota, missing credentials, a locked desktop, a user approval, an uncertain external side effect, unsupported app controls, or a failed publisher can leave work queued with evidence and a retry state. Universal mastery of every installed and future application is still not established.
