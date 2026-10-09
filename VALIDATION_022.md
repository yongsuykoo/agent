# Release 0.22.0 validation

Validated October 9, 2026. Catalog-backed research now retains checked public PDF snapshots, resumes section reading after restart, and refreshes sources while other manual reading continues. A download alone establishes no app capability. Universal current/future-app and OS mastery remains unfinished; no completion percentage is inferred from documentation or test counts.

| Check | Completed result | Evidence |
| --- | --- | --- |
| Local regressions | 576 passed | Existing 560 plus sixteen public-snapshot, source-refresh, concurrency and failure checks |
| Fresh installed wheel | 576 regressions and all 45 fixture checks passed | Normal site-packages installation; sixteen document, 25 browser and four file checks |
| Hosted Ubuntu Python 3.11 and 3.14 | 576 regressions and sixteen document checks passed on each | Independent hosted jobs |
| Hosted Windows Python 3.11 and 3.14 | 574 regressions passed and two existing POSIX-only skips on each | Actual Windows dependencies, parser process limits, SQLite and process APIs |
| Hosted Windows fixtures | All 45 passed on each, zero failures/skips/cancellations | Sixteen document, 25 actual Edge/Chrome and four file checks |
| Public HTTPS acquisition | Passed with default TLS verification | Actual W3C PDF download and isolated pinned parser; zero provider requests |
| Signed worker compatibility | Passed | Original 0.7.0 host dependency metadata/protocol, pinned signature/checksum, isolated worker and nested packaged PDF resources |

[Hosted acceptance run](https://github.com/yongsuykoo/agent/actions/runs/37941672475) verified source `8a4b2e81408e0f61a8099a19b97e9f6d10ae122a`. Only documentation and release artifacts change after this accepted source. The two Windows regression skips are existing POSIX-only registry-symlink and process-lock termination fixtures; every named document/browser/file fixture ran. Previous browser-startup failures and the readiness correction remain recorded in [0.20.0 validation](VALIDATION_020.md). These passing runs do not establish perfect repeated reliability.

Online acceptance uses actual owned HTTP streams, SQLite and the isolated packaged PDF parser. A fixture adapter substitutes public HTTPS transport, and deterministic provider responses stand in for model interpretation. Initial research downloads a seventy-page PDF without parsing or extracting capabilities during discovery. Pages 1–32 are front matter, 33–64 contain no text, and 65–70 contain an operation. Reading commits a durable draft, closes/reopens the catalog, records blank gaps without another provider request, and then establishes an execution-unverified procedure cited to page 65. All three sections retain precise source/cursor provenance. The whole reading uses one HTTP stream instead of re-downloading every section.

The second online fixture refreshes a forty-page snapshot: unchanged bytes retain the page-33 cursor, changed bytes start a new identity and are read again, and STOP preserves existing evidence. Three HTTP streams cover acquisition and the two refreshes. The fixtures assert that requests contain no provider Authorization header. This owned HTTP transport does not certify external TLS or provider reasoning.

A separate real network check fetched `https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf` over HTTPS with inherited proxy and default TLS verification. The 13264-byte PDF (SHA-256 `3df79d34abbca99308e79cb94461c1893582604d68329a41fd4bec1885e6adb4`) was registered in an owned catalog and read by the pinned isolated parser, yielding one page. No provider key was configured and no provider request ran. This proves that public acquisition and parsing worked for that document; it does not prove model interpretation, application operation or arbitrary publisher access.

The sixteen new regression checks cover deferred PDF-only discovery, mixed HTML/PDF study, restart through three sections, unchanged/changed refresh, stale bytes during model calls, cancellation before atomic commit, an actual app-generation update through a separate catalog connection during acquisition, parsed-cache tampering, failure backoff, stale refresh ownership and capture ordering, duplicate refresh owners and cancelled in-flight download, rejection of private/credential/non-HTTPS/oversized sources, raw-snapshot pruning on update/removal, alternative research after an exhausted unproductive manual, fair refresh alongside section study, preservation of downloaded PDFs when another source's provider call fails, and distinct manual identities when URLs redirect to the same final document. Existing checks retain installation discovery, parser correctness, exact page/character citations, cross-process recovery and concurrent single-owner claims.

Raw snapshots and metadata persist only for the current app generation. The catalog owner writes acquired bytes; network workers never use its SQLite connection. Refresh and reading use separate owner leases and exact generation/hash/revision fences. Cancellation or an obsolete owner cannot commit new evidence. An unchanged source keeps its reading cursor; a changed hash or final URL starts a new identity while older reading evidence remains historical. Public reading reports explicitly describe a retained snapshot. Model findings and exact reading progress commit atomically. Front matter alone cannot establish documentation or practice capability.

One public source becomes due twenty-four hours after successful acquisition/refresh and may be refreshed alongside normal reading in each learning cycle. A large manual queue cannot starve refresh. Refresh makes no model request, but interpreting later sections may incur charges. Failed refresh retains cached reading and retries after fifteen minutes; current publisher freshness is not guaranteed. Full bounded PDFs are re-downloaded, without conditional HTTP caching. A zero configured study limit remains uncapped; configured limits and credential/quota backoff are respected. Ad hoc research without a catalog still reads one bounded batch. Current-generation raw snapshots are pruned on update/removal; a total storage quota and history compaction are not implemented.

Parser bounds and dependencies are unchanged: 5 MB input, 1,024-page tree, at most 32 pages/24,000 retained characters per section, eight-second wall, six-second CPU and 256 MiB parser memory limits. The bundled BSD-licensed pypdf 6.20.0 wheel and its license remain pinned. Worker SHA-256 is `aabffe240b3dd0b206914415ac5103a3970c9c693111a772b2ed2090b18ac636`. Original 0.7.0 host compatibility, signed checksum verification, isolated read-only worker execution and nested reader-resource loading passed. No provider/controller credentials enter reader children; resource limits are not a general OS security sandbox.

No paid live-provider study, personal Windows remote control or live microphone check ran for this release. Actual hosted Windows browsers retain sandboxing and operate disposable local applications. Linux uses the explicit sandbox exception only for fixed trusted fixtures; product tasks preserve browser sandboxing, proxy and TLS verification. Installation dependencies and the existing cloud setup remain compatible.

Remaining gaps include OCR, encrypted/oversized manuals, broad native Office/Photoshop and other third-party workflows, external-account planning and delivery, live voice/model reliability, actual third-party installation/update adaptation, and universal software/OS mastery. These results extend autonomous documentation learning; they do not certify operation of every installed or future app.

Automatic verification:

```text
python -m unittest discover -s tests -v
python -m app_agent.cli document-smoke
python -m app_agent.cli file-smoke
python -m app_agent.cli browser-smoke
```

Windows launchers `windows\TestDocuments.cmd`, `windows\TestFiles.cmd` and `windows\TestBrowser.cmd` run owned fixtures without a provider key or desktop supervision. CI repeats the checks on source updates and retains only disposable reports. See [online manual study](ONLINE_MANUALS.md) for behavior and limitations.
