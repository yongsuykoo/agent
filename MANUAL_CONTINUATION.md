# Durable installed-manual study

Version 0.20.0 extends independent installed-PDF learning beyond the first bounded section. The normal background campaign studies one pending PDF section before continuing its initial app queue. Version 0.21.0 also starts this reading before an application has a blueprint; see [first-manual study](MANUAL_BOOTSTRAP.md). No demonstration or separate command for each section is required. A zero daily study limit retains the existing uncapped setting; user-configured limits and provider failures remain respected.

Progress is keyed to the application generation, exact discovered manual bytes/path and reader revision. A cursor identifies the next page and character offset. Each extraction retains at most 32 pages and 24,000 characters, so long single pages also continue without dropping text. Parsing retains the existing 5 MB input, 1,024-page tree, eight-second wall, six-second CPU and 256 MiB process limits. A section which exceeds a parser limit becomes a gap rather than an unbounded retry.

A staged parse does not advance progress. The blueprint update and acknowledged source cursor commit in one SQLite transaction after validated extraction. Earlier capabilities, execution evidence and page/range citations survive the merge. Every source records the retained text hash and cursor; only matching current-generation cached evidence can acknowledge that section. Complete reading remains `documented_unverified` until an actual operation is separately checked.

Only one worker can claim a manual section. A live owner's lease prevents duplicate concurrent study; a confirmed dead process can be replaced immediately. A stopped or failed request leaves the last committed section unchanged. STOP also rolls back cancellation during the final merge. Provider/parse failures receive a fifteen-minute retry delay. App updates/removals and changed manual bytes invalidate in-flight results. A provider call interrupted before commit may be repeated and charged after recovery; this release does not claim exactly-once paid requests.

Blank or scanned sections are recorded as textless page gaps and do not consume a model request; later extractable sections remain eligible. Extractable sections containing no applicable operations can advance with explicit limitations and no invented capabilities. Machine reports expose reviewed sections, characters, next cursor, known textless pages and reading completion. These fields measure retained reading evidence, not complete understanding.

Continuation applies to discovered installed PDFs, including new apps with no blueprint. Draft findings are retained separately until a cited operating procedure is established. Exhausted manuals without procedures queue alternative research. Installation scanning and public documentation retrieval retain their existing behavior. Public PDFs still receive a single bounded extraction. OCR, oversized/encrypted manuals, exhaustive source-code understanding and automatic execution of arbitrary software remain outside verified coverage.

Automatic checks use owned PDFs and installation folders, the actual isolated parser, filesystem, SQLite and process APIs, and deterministic provider responses:

```text
python -m unittest discover -s tests -v
python -m app_agent.cli document-smoke
```

The fourteen document checks include restart through seventy pages, contiguous offsets through a 50,010-character page, blank/scanned sections without model usage, cancelled commits, concurrent claims, actual process-exit recovery and generation changes. `windows\TestDocuments.cmd` runs them unattended. Hosted CI also runs existing Windows browser and file checks; no personal desktop or provider key is needed.
