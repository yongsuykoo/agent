# Release 0.16.0 validation

Validated on October 9, 2026 in the Linux cloud workspace. All checks below passed. A clean virtual environment installed the built wheel, confirmed imports came from `site-packages` and reported package version 0.16.0.

| Check | Result | What it establishes |
| --- | --- | --- |
| Repository regression suite | 494 passed | Existing behavior plus owned-profile identity, origin binding, cross-process locking, manual sign-in cancellation, queue waiting, generation-bound replay and headless Windows session-manager flow |
| Repository automatic browser suite | 13 passed, no failures/skips/cancellations | Real Chromium DOM actions, HTTP submissions and retained HttpOnly authentication against disposable owned fixtures |
| Fresh installed wheel regression suite | 494 passed | Packaged modules work independently of the editable source installation |
| Fresh-wheel automatic browser suite | 13 passed, no failures/skips/cancellations | Actual Chromium execution including retained authentication and account isolation |
| Fresh-wheel automatic file suite | 4 passed, no failures/skips/cancellations | Real file/folder copying, ZIP contents and incorrect-archive rejection |
| Signed release compatibility | Passed | Existing pinned controller identity, protocol 1 and unchanged dependency metadata compatible with the original 0.7.0 host |
| Isolated updated worker | Passed | The signed wheel executes a read-only learning report in its isolated child process |
| Package consistency | Passed | Wheel source matches repository bytes, ZIP CRC passes, session module and guide are included, and private profiles/build paths are excluded |

Five browser checks added in this release verify authentication surviving a browser restart, isolated account profiles, authenticated queued submission and replay, exclusive ownership, and deletion/recreation clearing stored authentication. The earlier eight checks retain Unicode form submission, unavailable controls, isolated-world state, false-completion rejection, stale target rejection, navigation, redirect restrictions, queue replay and uncertain-submit recovery. Exact repeats on unchanged live controls reuse the verified recipe with zero provider calls. Manual sign-in revision changes force fresh planning.

The local authentication application sets a real HttpOnly cookie; the agent does not extract that cookie into its records. Tests use actual Chromium processes, owned browser profiles, SQLite and process termination. A reviewed deterministic fixture planner drives tasks. Password entry, external service authentication, delivery receipts and planning quality are not inferred from these checks.

The Linux cloud lacks a usable Chromium sandbox. Only the fixed disposable fixture uses the explicit Linux-only `--trusted-fixture-no-sandbox` option. Windows checks and production tasks keep the sandbox and TLS verification enabled. No new dependency or setup service is required. No live Windows companion or paid planning credentials were available for this release.

Native Windows browser execution, actual external account workflows and MFA expiry handling, complete email delivery, real microphone reliability, unfamiliar complex applications, app-update adaptation and universal software mastery remain acceptance gaps. Stored profiles do not certify current sign-in or permission to operate an account.

After installation, credential-free acceptance is automatic:

```text
python -m unittest discover -s tests -v
python -m app_agent.cli file-smoke
python -m app_agent.cli browser-smoke
```

On Windows, `windows\TestBrowser.cmd` runs all thirteen browser checks using installed Edge or Chrome. The test fixture needs no provider key, personal account, hosted service or manual document.
