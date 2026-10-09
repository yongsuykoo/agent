# Release 0.17.0 validation

Validated on October 9, 2026 in the Linux cloud workspace. Final fresh-wheel acceptance and signed packaging are in progress. The completed checks are below.

| Check | Result | What it establishes |
| --- | --- | --- |
| Repository regression suite | 512 passed | Existing behavior plus exact option selection, unchanged desktop selection semantics, live option/context reconciliation and independent result requirements |
| Repository automatic browser suite | 19 passed, no failures/skips/cancellations | Actual Chromium processes, retained sessions, nested shadow/frame DOM, dropdown actions and HTTP submissions against owned disposable applications |
| Fresh installed wheel | Pending final check | Clean installation, regression suite, real browser/file checks and package consistency must pass before publication |

Six added browser checks operate a shadow root containing an iframe containing another shadow root. The agent types Unicode text, selects an enabled exact dropdown value, confirms the form and clicks Apply. The fixture server observes one actual submission and the task independently verifies its nested rendered output. A queued repeat checks nested live context guards and replays with zero provider calls. Other checks reject disabled optgroups, duplicate/missing values, changed option labels, changed frame URLs, detached frames, inaccessible contexts and output beyond inspection limits.

The observer protects password values inside supported nested contexts and reports inaccessible frames. DOM traversal and the retained strong node map remain bounded. The first thirteen browser checks continue to cover flat-page operation, authentication across restarts, separate profiles, unsupported controls, stale targets, guarded replay and uncertain-submit recovery. A reviewed deterministic planner drives the fixture tests; no external accounts or provider credentials are used.

The Linux cloud lacks a usable Chromium sandbox. Only the fixed built-in fixture uses the explicit Linux-only test exception. Production tasks and Windows checks retain sandbox and TLS verification. No dependency or startup-service change is required.

Hosted regression logs from the preceding 0.16.0 release revealed failures on all four CI jobs. Windows Python 3.14 compares path creation time with handle change time when using ctime; file reading now binds path/handle by compatible identity fields and retains separate before/after timestamp checks for each. Windows reads also deny concurrent writes/deletes; the mutation test verifies the write is refused while reading and succeeds after interruption releases the handle. Four regressions exercise this distinction and reject replaced identities or changing handle timestamps. Headless interface tests now isolate native registry and installer probes and use normalized blueprint fixtures instead of scanning the runner’s real apps. A recently booted machine now scans immediately before resuming goals and starts its first background study without waiting for an uptime threshold. Browser startup retries locked/partial endpoint files within a fixed deadline, cleanup waits briefly for owned child file handles, and Windows child output no longer holds a log file in the disposable folder. CLI output uses UTF-8 so printing a Unicode result cannot stop a task. Seven lifecycle regressions cover these cases and enforce a bounded wait for supported embedded documents. A deliberately delayed iframe response exercises real loading readiness before planning. The earlier local Linux pass did not establish hosted Windows acceptance.

The existing Windows relay was probed with a signed read-only request and returned HTTP 530 without an authenticated helper response. No Windows desktop job was submitted. Hosted Windows CI now runs real file and browser smoke checks on Python 3.11 and 3.14 after regressions, and uploads only disposable `report.json` files. Retained browser profiles, cookies and keys are excluded. Workflow configuration is not evidence that those hosted checks have passed; their observed results are reported separately.

Native Windows fixture acceptance, arbitrary external-site planning, complete email delivery, real microphone reliability, app-update adaptation and universal installed/future-app understanding remain unfinished. A same-origin DOM observation does not prove service-side delivery or general app mastery.

Credential-free acceptance:

```text
python -m unittest discover -s tests -v
python -m app_agent.cli file-smoke
python -m app_agent.cli browser-smoke
```

On Windows, `windows\TestBrowser.cmd` runs all nineteen browser checks using installed Edge or Chrome. It requires no hosted application, personal account, provider key or manual document.
