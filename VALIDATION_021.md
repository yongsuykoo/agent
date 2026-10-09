# Release 0.21.0 validation

Validated October 9, 2026. Newly discovered installed PDFs can now be studied before an app has an operational blueprint. Partial reading survives restart; actual cited procedures establish documentation. Universal current/future-app mastery remains unfinished. No goal-completion percentage is inferred from test or documentation counts.

| Check | Completed result | Evidence |
| --- | --- | --- |
| Repository regressions | 560 passed | Existing 549 checks and eleven new bootstrap, fallback, restart, cancellation, ownership and update checks |
| Fresh installed wheel | 560 regressions and all 43 fixture checks passed | Normal site-packages installation; fourteen document, 25 browser and four file checks |
| Hosted Ubuntu Python 3.11 and 3.14 | 560 regressions and fourteen document checks passed on each | Independent hosted jobs |
| Hosted Windows Python 3.11 and 3.14 | 558 regressions passed and two existing POSIX-only skips on each | Actual Windows dependencies, parser process limits, SQLite and process-liveness APIs |
| Hosted Windows fixture checks | All 43 passed on each, no failures/skips/cancellations | Fourteen document, 25 Edge/Chrome and four file checks |
| Signed worker compatibility | Passed | Original 0.7.0 host dependency metadata/protocol, pinned signature/checksum, isolated worker and nested packaged PDF reader |

[Hosted acceptance run](https://github.com/yongsuykoo/agent/actions/runs/37934745659) verified source `aa1b596f393040b8f087b0a4227bdc10227e707d`. Only documentation and release artifacts change after that source acceptance. Existing Windows regression skips are the POSIX-only registry-symlink and process-lock termination fixtures; all named document/browser/file checks ran. The previous release's browser-startup failures and readiness fix remain recorded in [0.20.0 validation](VALIDATION_020.md). Successful acceptance runs do not prove perfect repeated reliability.

The new document acceptance creates an owned seventy-page manual and discovers it through installation inspection. Pages 1–32 contain front matter, 33–64 are textless, and 65–70 contain operating instructions. The first section commits a durable draft without claiming a documented app. The catalog closes and reopens, the next section records blank/scanned gaps without another provider call, and later instructions establish a cited, execution-unverified capability. All three source sections are retained. This exercises the actual packaged parser, filesystem and SQLite with deterministic model responses.

A separate acceptance exhausts a forty-page manual without operating instructions. Reading completion retains limitations but leaves the app undocumented and queues alternative research. The completed PDF is excluded from initial research context rather than sent to the model again. A later blueprint from another source merges the draft's source evidence and gaps. Reading an entire supported document does not prove complete semantic understanding.

The eleven new regression checks cover blank opening sections without provider charges, textual front matter retained through restart, exhaustion without false documentation, alternative-source evidence preservation, exclusion from duplicate initial research, atomic cancellation during the merge, failure backoff and retry, two manuals finishing in reverse order, preservation of another active manual owner after a failure, respect for an active initial research owner, and rejection of obsolete bootstrap results after an application update. Existing checks also verify single-owner claims across independent database connections and immediate recovery after an actual separate process exits.

Machine reports expose current reading progress and whether a blueprint exists. Learning summaries distinguish manual reading from documented applications. Drafts cannot supply practice capabilities. Zero configured daily usage limit remains uncapped; finite user limits and credential/quota backoff remain respected. Failed parsing/model calls retain exact progress and receive a fifteen-minute retry delay. An interrupted model request can be repeated and billed after recovery.

Parser bounds and dependencies are unchanged: 5 MB input, 1,024-page tree, at most 32 pages and 24,000 retained characters per section, eight-second wall, six-second CPU and 256 MiB process limits. The pinned BSD-licensed pypdf 6.20.0 wheel remains bundled with its license. The signed worker SHA-256 is `ed619e521c8cf6d66d20cf3f6b4fe41f04a73e82c73c3cf6e690f893f29fbdcd`. Signature verification, original 0.7.0 host dependency compatibility, isolated read-only worker execution and nested reader-resource loading passed.

No paid live-provider study or personal Windows desktop control ran for this release; no provider key was configured in this cloud. Model interpretation is simulated in the owned fixtures. Windows browser checks run actual Edge/Chrome with sandboxing enabled against disposable local applications. Linux uses the existing explicit sandbox exception only for these trusted fixed fixtures. Product tasks preserve browser sandboxing, proxy and TLS verification. Provider/controller credentials remain excluded from reader children. Process resource limits are not a general OS security sandbox. Existing cloud setup and installation dependencies remain compatible.

Remaining gaps include OCR, encrypted/oversized manuals, public-PDF multi-section study, broad native Office/Photoshop and other third-party app workflows, arbitrary external account planning/delivery, live microphone reliability, actual third-party installation/update adaptation, and universal software/OS mastery. This release closes the installed first-manual prerequisite; it does not turn documented procedures into tested execution or certify every app.

Automatic checks:

```text
python -m unittest discover -s tests -v
python -m app_agent.cli document-smoke
python -m app_agent.cli file-smoke
python -m app_agent.cli browser-smoke
```

Windows launchers `windows\TestDocuments.cmd`, `windows\TestFiles.cmd` and `windows\TestBrowser.cmd` run the owned fixture checks without a provider key or desktop supervision. Hosted CI repeats the checks on source updates and retains only disposable reports. See [first-manual study](MANUAL_BOOTSTRAP.md) for behavior and limitations.
