# Native file tools — updated in 0.17.0

The agent can use fixed local filesystem operations for file copying and ZIP creation. It interprets explicit paths, inventories the requested source, creates an exclusive new destination, and independently verifies the saved bytes. It needs neither a provider call nor a File Explorer window for these tasks.

## Tasks

Choose **Automatic** in the window selector and enter one of these forms, replacing the quoted paths with your actual paths:

```text
Copy file "D:\Projects\brief.docx" to "D:\Backups\brief-copy.docx" and verify.
Copy folder "D:\Projects\Photos" to new folder "D:\Backups\Photos-copy" and verify.
Copy all files from folder "D:\Projects\Photos" to new folder "D:\Backups\Photos-copy" and verify.
Create a ZIP archive of folder "D:\Projects\Photos" at "D:\Backups\Photos.zip" and verify.
Compress folder "D:\Projects\Photos" into "D:\Backups\Photos.zip".
```

The destination parent must already exist, and the requested destination must be new. Folder copy includes all nested regular files, empty directories and hidden entries that can be read normally. ZIP entries use source-relative names, without embedding the absolute drive path or the root folder name. Copy verifies contents and folder structure; it does not preserve ACLs, alternate streams or timestamps. Neither operation executes the files it reads.

Autonomous mode permits the exact submitted operation. Supervised mode presents the source, destination and operation before reading source contents. Native file tasks do not request cloud-sharing or screenshot permission. Selecting an app window explicitly, requesting a different tool such as 7-Zip, or adding delivery/deletion/editing instructions keeps the task on the general desktop route so the native tool cannot silently omit part of the goal.

Relative paths, missing source/parent paths, device/network paths, alternate streams, reserved Windows names, links/junctions/reparse points, unsupported special files and a destination inside the source are rejected. Each task supports up to 4,096 entries and 2 GiB of source bytes, streamed in bounded chunks. These are operation bounds, not a daily budget; no daily file-task cap is added. More general file selection, move/delete, existing destination merging, encrypted archives and extraction remain additional work.

## Verification and recovery

Windows file reads now exclude overlapping writers/deleters until the handle closes. Path and opened-handle identity use compatible fields across Python versions, with separate before/after timestamp checks for each. An already open incompatible writer defers the read. These bounded handles close after success, error or cancellation.

The task records relative names, sizes and SHA-256 hashes. It hashes source data during transfer, checks that the source inventory/content still matches, then separately reads the output. Folder verification rejects missing/extra files or directories. ZIP verification reads every member and rejects changed bytes, incorrect sizes, duplicate/extra entries and encrypted entries. Output hashes become durable checkpoints only after these checks succeed.

Jobs and schedules use the same queue and STOP state as other tasks. The background worker can execute these autonomous goals with no API credential, while retaining its existing unlocked/idle desktop policy. A schedule retains the exact output path; repeating a completed copy to the same path fails because that destination now exists. This release does not invent new backup paths or overwrite old backups.

A restart after durable verification rechecks the existing output against the saved manifest and hash without rereading or copying the source again. Changed/missing output cannot be reported as completed. A crash, STOP or error after dispatch but before verification retains any partial output and marks the unfinished job `needs_review`; it does not overwrite or silently delete it. File path checks detect ordinary links and observed changes, but do not provide an operating-system sandbox or guarantee atomic isolation from hostile concurrent filesystem changes.

## Automatic checks

`windows\TestFiles.cmd` runs four credential-free checks: real file copy, recursive folder copy with Unicode/empty directories, ZIP creation, and rejection of incorrect archived bytes. It uses a fresh disposable folder in the agent data directory, retains a JSON report and test artifacts, and does not interact with the desktop or existing user documents. The CLI equivalent is:

```text
app-agent file-smoke
```

The 445 automated tests pass from both the repository and a fresh installed wheel. File tests use actual Linux filesystem/ZIP data, real SQLite, and a child process that exits after dispatch to prove uncertainty survives recovery. Headless chat tests, the background supervisor and schedules execute real file goals without provider construction. A separate fresh-wheel automatic smoke run passed all four checks. Native Windows file execution has not been tested in this cloud session; Windows path validation and reparse attributes are covered separately. No all-app completion is inferred from these checks.
