# Release 0.15.0 validation

Validated on October 9, 2026 in the Linux cloud workspace. All checks below passed. A fresh virtual environment installed the built wheel, confirmed imports came from `site-packages` and reported package version 0.15.0.

| Check | Result | What it establishes |
| --- | --- | --- |
| Repository regression suite | 475 passed | Existing behavior plus browser routing, transport limits, independent output checks, cached replay and durable recovery |
| Fresh installed wheel regression suite | 475 passed | The packaged modules work independently of the editable source installation |
| Fresh-wheel automatic browser checks | 8 passed, no failures/skips/cancellations | Real Chromium DOM actions and HTTP submissions against the owned disposable fixture |
| Fresh-wheel automatic file checks | 4 passed, no failures/skips/cancellations | Real copied/archived bytes and rejection of an incorrect ZIP |
| Controller-signed release verification | Passed | Existing pinned controller key, protocol 1 and unchanged dependency metadata compatible with host 0.7.0 |
| Isolated updated worker | Passed | The signed wheel executes the read-only learning-report operation in its isolated child process |
| Package consistency | Passed | Wheel source bytes match the repository, ZIP CRC passes, new modules and Windows launcher are included, and private/build paths are excluded |

The browser checks use actual Chromium processes, new private profiles, a local HTTP application and a reviewed deterministic planner. The tests observe real Unicode text entry, checkbox state, one HTTP submission per requested form task, rendered result text, link navigation, blocked out-of-scope redirects, and unavailable/password controls. The queue's second successful form goal uses local replay with zero provider calls. An injected interruption after a real submission produces `needs_review` and does not submit again. A premature completion claim is rejected without a submission.

The Linux cloud's Chromium sandbox is unavailable. Its fixed local fixture checks use the explicit test-only sandbox exception; production browser tasks and Windows smoke checks keep the browser sandbox enabled. These checks do not establish external-site TLS behavior through the cloud proxy, paid model planning quality, sign-in or mail delivery, native Windows browser execution, real microphone reliability, arbitrary installed-app coverage, or universal software mastery. No live Windows companion was connected for this release.

Reproduce the credential-free checks after installation:

```text
python -m unittest discover -s tests -v
python -m app_agent.cli file-smoke
python -m app_agent.cli browser-smoke
```

On Windows, `windows\TestBrowser.cmd` runs the complete disposable browser suite automatically using installed Edge or Chrome. On Linux, a normal usable Chromium sandbox is required; only constrained testing of the built-in fixture may use `browser-smoke --trusted-fixture-no-sandbox`. That flag is rejected on Windows and cannot disable the sandbox for a real browser goal.
