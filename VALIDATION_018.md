# Release 0.18.0 validation

Validated on October 9, 2026. This release adds bounded rich-text replacement, semantic ARIA controls, referenced-label handling and post-focus reconciliation. No all-app completion percentage is inferred.

| Check | Completed result | Evidence |
| --- | --- | --- |
| Repository regressions | 518 passed | Existing behavior plus six semantic-state, approval, recipe and result-proof regressions |
| Actual Linux browser fixtures | 25 passed, none failed/skipped/cancelled | Nineteen existing browser cases plus six rich-text/semantic scenarios |
| Fresh installed wheel | 518 regressions, 25 browser checks, four file checks passed | New symlinked Python environment, normal wheel installation into site-packages and disposable real effects |
| Hosted Ubuntu, Python 3.11 and 3.14 | 518 passed on each | Independent GitHub Actions regression runs |
| Hosted Windows, Python 3.11 and 3.14 | 516 passed and two POSIX-only skips on each | Actual Windows dependencies and process/filesystem semantics |
| Hosted Windows file checks | Four passed on each; no failures/skips/cancellations | Actual file/folder copies, Unicode names, ZIP members and independent byte verification |
| Hosted Windows browser checks | 25 passed on each; no failures/skips/cancellations | Actual Edge/Chrome with the sandbox enabled, HTTP submissions, retained profiles, rich editors and semantic controls |
| Signed worker compatibility | Passed | Existing pinned signature, SHA-256, original 0.7.0 host dependency metadata/protocol and process-isolated read-only child |

[Hosted acceptance run](https://github.com/yongsuykoo/agent/actions/runs/37920923914) tested source commit `a6e90364d087be42cb2f139fc01ca5132d3b05cd`. The release changes only documentation and packaged artifacts after that verified source. The two Windows regression skips are existing POSIX-only registry-symlink and process-lock termination fixtures. Every named browser/file check ran.

The new real browser workflow replaces a previously formatted rich draft with Unicode/multiline text, enables a custom switch, chooses a review tab and submits it. Four actual actions produce one HTTP submission; the task independently verifies the exact rendered saved output and preserves UTF-8 evidence. A queued repeat rechecks rich markup and ARIA guards and performs four actions with zero provider calls. Tests also cover literal script-looking text without creating an image/script, application input notification, empty replacement and actual browser undo; binary toggle idempotence; application radio/menu/option handlers; changed state/markup and focus-time readonly rejection; and protection of readonly, widget/media, oversized and ambiguous controls.

An unsupported editor containing a password widget exports neither its markup nor the password value. Visible referenced labels and their descendants cannot masquerade as completed output. Editor content, tab labels and control values remain ineligible for exact browser proof. The DOM-tool revision invalidates earlier browser recipes; existing scopes, profile locks, interruption journals and uncertain-effect recovery remain in force.

The first browser run caught two real editing issues: inherited paragraph markup converted one inserted newline into an extra paragraph break, and a blank editor retained a placeholder break. Fixed escaped-text/line-break insertion and empty-document observation passed the updated tests. No fixture or production action executes model-supplied HTML or JavaScript.

All browser acceptance uses reviewed deterministic planners and owned local applications, not paid model planning or personal accounts. No provider key is configured in this cloud session. Linux uses the explicit exception only for fixed trusted fixtures because its browser sandbox is unavailable. Windows and production keep sandbox, proxy and TLS verification. Dependencies and saved environment setup instructions are unchanged. Hosted CI automatically repeats Windows file/browser checks on future source updates and retains only disposable reports.

Broader native application coverage, arbitrary external-site planning, external account delivery, live microphone reliability, actual app-update adaptation and universal installed/future-app mastery remain unfinished. A rendered DOM result alone does not prove an external service delivered mail or published content.

Automatic checks:

```text
python -m unittest discover -s tests -v
python -m app_agent.cli file-smoke
python -m app_agent.cli browser-smoke
```

The Windows launchers `windows\TestFiles.cmd` and `windows\TestBrowser.cmd` use disposable data and require no provider key, personal account or manual document.
