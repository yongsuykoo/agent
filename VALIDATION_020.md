# Release 0.20.0 validation

Validated on October 9, 2026. Installed-PDF study now continues beyond the first section, resumes after restart, preserves page/range citations and commits findings with progress atomically. Universal all-app mastery remains unfinished; no completion percentage is inferred.

| Check | Completed result | Evidence |
| --- | --- | --- |
| Repository regressions | 549 passed | Existing 533 checks plus 16 startup readiness, continuation, cancellation, concurrency, byte/generation fencing and process-recovery checks |
| Fresh installed wheel | 549 regressions, twelve document checks, 25 browser checks and four file checks passed | Normal installation into new site-packages; actual parser, filesystem, SQLite, process and Chromium effects |
| Hosted Ubuntu, Python 3.11 and 3.14 | 549 regressions and twelve document checks passed on each | Independent hosted jobs |
| Hosted Windows, Python 3.11 and 3.14 | 547 regressions passed with two existing POSIX-only skips on each | Actual Windows dependencies, parser resource limits, leases and exited-process recovery |
| Hosted Windows document checks | Twelve passed on each; no failures/skips/cancellations | Seventy-page restart, 50,010-character continuation, textless gaps and fenced checkpoints, plus existing PDF checks |
| Hosted Windows browser checks | 25 passed on each; no failures/skips/cancellations | Actual Edge/Chrome with sandbox enabled and owned HTTP fixtures |
| Hosted Windows file checks | Four passed on each; no failures/skips/cancellations | Actual Unicode file/folder copies and ZIP member/hash verification |
| Signed worker compatibility | Passed | Pinned signature, byte checksum, original 0.7.0 host dependency metadata/protocol, isolated worker and nested packaged parser |

[Hosted acceptance run](https://github.com/yongsuykoo/agent/actions/runs/37931850493) tested source commit `fc0a024ecd4de6abad26f7663af123a97ab7da23`. Only documentation and packaged artifacts change after that verified source. Windows skips remain the existing POSIX-only registry-symlink and process-lock termination fixtures; all named document, browser and file checks ran.

[The initial acceptance run](https://github.com/yongsuykoo/agent/actions/runs/37929498172) passed all regressions and document checks, but Windows 3.11 passed 24 of 25 browser checks: one nested-form startup/observation command timed out before task actions were logged. Windows 3.14 passed all 25. [A second run](https://github.com/yongsuykoo/agent/actions/runs/37930562311) of source `e9fcfc242eb91eeabe7441078e57f415b85d1b90` passed all Windows 3.11 checks but timed out before the first Windows 3.14 form task. The added RPC diagnostics narrowed the remaining bare timeout to initial WebSocket negotiation, before any task command. The original five-second handshake wait is now a bounded fifteen-second startup allowance, with STOP checks and the existing header-size ceiling. A regression verifies both a six-second handshake and rejection beyond the absolute fifteen-second deadline. Task command deadlines remain unchanged, and uncertain actions are not automatically repeated. The later source acceptance above passed all four jobs; a successful run does not erase this earlier reliability gap.

The continuation checks close and reopen the catalog after reviewing pages 1–32, then review 33–64 and 65–70, retaining all three source sections and their citations. A completed manual produces no further provider request. A 50,010-character single page is reconstructed across contiguous character ranges without loss or overlap. A middle section with 32 textless pages records those gaps without a provider call and proceeds to later readable text. These are actual PDF reading and persistence effects with deterministic model responses, not proof of model interpretation or application operation.

Eight concurrent claims through independent SQLite connections yield one owner. Another check launches a separate Python process, claims study and exits without cleanup; ownership is recovered immediately through native process-liveness APIs on both operating systems. STOP after a provider response leaves the old checkpoint unchanged. A separate regression cancels during the final merge and confirms both blueprint and cursor roll back. App version changes reject in-flight findings; changed manual bytes, forged cached-source metadata and invalid cursors cannot advance progress. Finite user budgets leave the next section pending, while zero remains uncapped. Failed provider calls back off without moving the checkpoint.

The blueprint keeps earlier canonical capability names, page/range citations and source sections. Existing execution records remain attached through the application's current generation. Reading completion and textless page gaps are exposed in machine reports. Reading alone remains `documented_unverified`. Initial inventory/learning and public PDF transport remain compatible with 0.19.0; public PDFs still receive one bounded batch, and initial installed study must establish a blueprint before continuation is eligible.

The actual parser retains its eight-second wall, six-second CPU and 256 MiB process limits on Linux and Windows. Parsing accepts at most 5 MB and a 1,024-page tree, with at most 32 pages and 24,000 retained characters per batch. The unmodified, pinned BSD-licensed pypdf 6.20.0 wheel and license remain bundled. The signed worker byte SHA-256 is `a02aec4bd99c6064e6b249ef0982daca10ef29deac3af8699da03acd90b0fe39`; its dependency metadata remains compatible with the original 0.7.0 connection host. Signature, isolated worker and nested packaged-reader checks passed from the current wheel.

No paid live-model study or personal Windows desktop control ran for this release. Provider responses are simulated in owned fixtures. Browser checks use a disposable local application; actual external account workflows remain unverified. Linux uses the existing explicit sandbox exception only for trusted fixed fixtures; Windows and product tasks retain browser sandboxing, proxy and TLS verification. Provider/controller credentials remain excluded from parser children. A provider request interrupted before durable commit may be repeated and billed after recovery.

Remaining gaps include OCR, oversized/encrypted manuals, first sections which establish no usable blueprint, broad native app workflows, arbitrary external-service planning/delivery, live microphone reliability, real third-party installation/update adaptation and universal installed/future-app mastery. Complete reading does not prove exhaustive semantic understanding or successful app execution. Process limits are not a general OS security sandbox. Existing cloud setup and dependency requirements remain compatible.

Automatic checks:

```text
python -m unittest discover -s tests -v
python -m app_agent.cli document-smoke
python -m app_agent.cli file-smoke
python -m app_agent.cli browser-smoke
```

Windows launchers `windows\TestDocuments.cmd`, `windows\TestFiles.cmd` and `windows\TestBrowser.cmd` run the owned fixture checks without a provider key or desktop supervision. Hosted CI repeats them on every source update and retains only disposable reports. See [manual continuation](MANUAL_CONTINUATION.md) for operation and limits.
