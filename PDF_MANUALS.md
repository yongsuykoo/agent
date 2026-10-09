# Independent PDF manual learning

Version 0.19.0 extends installed-manual and public documentation learning to PDF files. A PDF reader is bundled in the signed worker, so supported worker updates do not require installing another dependency on Windows.

Installation inventory discovers selected filenames containing manual, guide, help, reference, tutorial or readme. It records the file's byte hash without parsing every document during startup. When that application is studied, the agent checks the exact discovered installation path and bytes, reads the PDF in a separate process and caches the resulting page evidence. Unchanged evidence survives restarts. Changed bytes are rejected until another scan; a new application generation retires the earlier blueprint and receives fresh evidence.

Public documentation retrieval accepts HTTPS `application/pdf` responses, checks redirects using the existing public-source policy and records the final URL, original URL, byte hash and retrieval time. Installed manuals can skip online discovery when they establish operations. Unreadable installed manuals retain a gap and permit the existing additional documentation search.

The reader inspects at most 32 pages and retains at most 24,000 characters per batch. Version 0.20.0 resumes installed manuals through additional batches using durable page/character cursors; public PDF retrieval still reads one bounded batch. Page trees are capped at 1,024 pages. It accepts up to 5 MB of PDF bytes. Each reader has an eight-second wall deadline, a six-second CPU allowance and a 256 MiB process memory ceiling, enforced through POSIX resource limits or a Windows Job Object. At most two readers run concurrently. Stream decoding, page trees and form traversal are also bounded. The packaged parser wheel is checked against its pinned SHA-256 before loading. Provider and controller credentials are excluded from the reader's environment.

Pages include their number, retained character range and a hash of the extracted text that was actually retained. Blueprint extraction must cite an inspected, nonempty PDF page for every PDF source it uses. Uninspected pages, empty pages and citations to a different source are rejected. Partial reading deterministically adds a limitation even if the model omits it. A citation establishes provenance, not that the model interpreted the text correctly or that the operation succeeds. PDF-derived capabilities remain `documented_unverified` until separate execution evidence supports them.

Encrypted documents, scanned pages without extractable text, malformed documents and excessive resource use produce explicit gaps. Installed continuation records textless sections and proceeds to later pages; it cannot interpret scanned images. This release does not supply OCR, passwords, JavaScript rendering, unrestricted binary reverse engineering or proof of every app operation. PDF attachments, scripts and installation procedures are never executed by the reader. The process limits contain resource use; they are not a general operating-system security sandbox.

The original BSD-licensed pypdf 6.20.0 wheel and its license are packaged unchanged. See [third-party notices](THIRD_PARTY_NOTICES.md).

Automatic acceptance uses owned, disposable PDFs and a simulated installation folder, with the actual parser and filesystem APIs. No provider key, browser, desktop supervision or personal manual is required:

```text
python -m app_agent.cli document-smoke
```

`windows\TestDocuments.cmd` runs the same twelve checks. Hosted CI runs them on Linux and Windows, Python 3.11 and 3.14, alongside existing regressions and Windows browser/file acceptance.
