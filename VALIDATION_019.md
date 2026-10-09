# Release 0.19.0 validation

Validated on October 9, 2026. This release adds installed and public PDF manual reading, isolated bounded extraction, cached page evidence and inspected-page citations. Universal installed/future-app mastery remains unfinished; no completion percentage is inferred.

| Check | Completed result | Evidence |
| --- | --- | --- |
| Repository regressions | 533 passed | Existing 518 checks plus 15 PDF reading, retrieval, citation, cache, process and worker-package checks |
| Fresh installed wheel | 533 regressions, eight document checks, 25 browser checks and four file checks passed | Normal installation into a new environment; actual parser, filesystem and browser effects |
| Hosted Ubuntu, Python 3.11 and 3.14 | 533 regressions and eight document checks passed on each | Independent GitHub Actions runs |
| Hosted Windows, Python 3.11 and 3.14 | 531 regressions passed with two POSIX-only skips on each | Actual Windows dependencies, handle semantics, isolated parsing and worker ZIP resources |
| Hosted Windows document checks | Eight passed on each; no failures/skips/cancellations | Compressed/Unicode pages, bounded coverage, unusable documents, cache, changed bytes and update invalidation |
| Hosted Windows browser checks | 25 passed on each; no failures/skips/cancellations | Actual Edge/Chrome, sandbox enabled, owned HTTP fixtures, retained profiles and rich/semantic controls |
| Hosted Windows file checks | Four passed on each; no failures/skips/cancellations | Actual Unicode file/folder copies and ZIP member/hash verification |
| Signed worker compatibility | Passed | Pinned signature, checksum, original 0.7.0 host dependency metadata/protocol, isolated worker and nested packaged PDF reader |
| Actual public HTTPS PDF retrieval | Passed | W3C's one-page test PDF fetched with proxy/TLS verification and parsed with retained page/hash evidence |

[Hosted acceptance run](https://github.com/yongsuykoo/agent/actions/runs/37925492589) tested source commit `525fc5484379b5aeaffba61c747a75e9e89cf696`. Only documentation and packaged artifacts change after that verified source. The two Windows skips are existing POSIX-only registry-symlink and process-lock termination fixtures. All named document, browser and file checks ran.

The actual PDF reader extracted compressed multi-page text and Unicode font mappings, retained exact page hashes, and recorded a deterministic gap after reading 32 of 40 pages. Malformed, encrypted, scanned-only and excessive decoded-stream documents were rejected. The Windows child applied a 256 MiB process memory limit and six-second CPU allowance through a Job Object; Linux applied POSIX resource limits. Both enforce an eight-second parent timeout. A regression confirms timeout handling excludes provider/controller credentials from the reader environment and rejects modified parser bytes before launching.

An additional cloud check retrieved [W3C's public accessibility test PDF](https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf), extracted its single page and verified its expected text. The fetched byte SHA-256 was `3df79d34abbca99308e79cb94461c1893582604d68329a41fd4bec1885e6adb4`. This checks actual public transport and PDF reading, not application-manual applicability or paid model interpretation.

The disposable installed-manual check discovered a PDF without parsing during inventory, extracted and cached its page evidence during study, rejected changed bytes before another scan, and relearned after an app-generation change. Its blueprint remained `documented_unverified`; it did not claim successful app execution from reading alone. Required page citations reject unread, empty and unrelated pages. The regression suite also covers public PDF retrieval and bounded citation repair with unchanged evidence.

Fresh-package acceptance verified the bundled parser and license resources match source bytes, normal site-packages installation succeeds, the signed worker matches the original host dependencies, and an isolated process can read the nested parser wheel from inside the worker archive. The same nested-resource regression passed on hosted Windows. Compatible connection hosts use the existing signed-worker update mechanism; an older host still needs its one-time upgrade.

These checks use owned fixtures and deterministic provider responses. No provider key is configured in this cloud session; paid live-model PDF interpretation and actual publisher-document applicability were not tested. PDF citations establish retained provenance, not semantic correctness. No personal Windows desktop was controlled in this release. Browser acceptance uses local owned applications, not external personal accounts. Linux uses its existing explicit exception only for trusted fixed browser fixtures; Windows and production keep the browser sandbox, proxy and TLS verification.

Encrypted/scanned PDF support, OCR, manuals beyond the inspected page/text allowance, broader native application operation, arbitrary external-service planning/delivery, live microphone reliability, actual third-party installer/update adaptation and universal installed/future-app mastery remain unfinished. Resource limits do not constitute a general OS security sandbox. Existing environment setup instructions and dependency requirements remain compatible.

Automatic checks:

```text
python -m unittest discover -s tests -v
python -m app_agent.cli document-smoke
python -m app_agent.cli file-smoke
python -m app_agent.cli browser-smoke
```

Hosted CI repeats document checks on all four platforms and Windows browser/file checks on each source update. It retains only disposable fixture reports. Windows launchers `windows\TestDocuments.cmd`, `windows\TestFiles.cmd` and `windows\TestBrowser.cmd` require no provider key or desktop supervision.
