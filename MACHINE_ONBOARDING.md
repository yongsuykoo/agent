# Automatic machine onboarding — 0.8.0

The main app scans on startup and after observed installation registration changes, with five-minute reconciliation while it remains open. The automatic connection helper runs the same backend in its inventory jobs. A Windows installation with no third-party software still produces a Windows platform entry, which is queued for system documentation. Installing an app adds local evidence and gives the new entry study priority. Existing inventories are enriched on their next scan. No demonstrations are required for these stages.

Local onboarding needs neither an AI key nor a daily study allowance. It reads machine/software metadata and selected installation files; it does not read browsing history or personal document folders. Internet research and model-based operation still require the configured provider. `0` removes the application daily study/design cap; provider charges, quotas and rate limits remain. The CLI `study-next` and `study-campaign` now accept `--daily-limit 0` and default to uncapped usage.

## What the agent observes

| Source | Evidence retained | Meaning |
| --- | --- | --- |
| Windows registry | Edition, version, build and architecture | Identifies the installed platform; an OS update queues new-version study |
| Windows services | Names, display names, states and start types | Records current system facts; no service command lines or account credentials |
| Existing inventory, App Paths, Start shortcuts and registered executable icons | App identity, versions, installation roots, launch identities | Finds more registered software and links shortcuts to installation files |
| Class registrations | ProgIDs, CLSIDs, associated executable identities | Identifies automation candidates without instantiating them |
| File-type registrations | Extensions associated with the observed ProgID family | Shows candidate app relationships; does not establish working file support |
| Installation folders | Selected files, sizes, timestamps and bounded hashes | Detects changes in inspected files, including primary executable patches without a version-number change |
| PE executables/libraries | Architecture and imported DLL names | Static dependency/interface clues; binaries are never loaded or executed during inspection |
| Manifests | Names, hashes, public package name/version/dependency names | Provides installation structure; configuration values and secrets are omitted |
| Installed text/HTML manuals | Up to three matching manual/help/readme/guide/reference/tutorial sources | Uses installation-specific documentation before online search; source text is explicitly untrusted |
| Already open app windows | Accessible controls; research receives only control types/actions | Gives operation-relevant structure without opening, focusing or typing into an app during onboarding |

Class registration probing records executable-backed automation candidates. It does not introspect all COM type libraries or execute COM procedures. App Paths can launch a catalog-selected registered executable as a literal path with no registry arguments or model-generated command. Platform knowledge entries cannot be selected as task windows.

## Continuous adaptation

Four local readers inspect installations. Static analysis is cached for unchanged inspected files. New/changed identities receive study priority ahead of the old backlog. Version changes, observed primary-file changes, or changed complete file inventories advance the app generation, retire its old blueprint/experiments/replay routines from current use, and keep historical evidence available. Current-generation interfaces and facts inform research and task planning. Installed manuals can bypass web discovery when they establish documented capabilities; unusable manuals fall back to online references. Provider authentication/rate failures back off instead of triggering more discovery calls.

The Windows platform is queued for documentation, but disposable app experiment planning excludes that non-window platform record. The existing task director chooses installed applications, observes accessible controls, checks task results and saves executed workflows. Merely finding a DLL, manual or automation registration never counts as a verified operation. No arbitrary discovered command or installation script is executed by this stage.

App Paths, class and uninstall registration watches trigger discovery when available. Existing 0.7 hosts can load the signed 0.8 worker backend without changing the relay, pairing key or protocol. Additional native watches and the **Machine knowledge** button require the updated host/main interface. No Cloudflare reconfiguration is needed. A stopped or expired helper must be started locally; a worker release cannot reopen a closed Windows process.

## Inspect progress

Click **Machine knowledge** in the main app. The backend report is saved at `%LOCALAPPDATA%\AppAgent\machine-report.json`; current evidence is also available through `app-agent machine-report` and the existing encrypted `learning_report` operation. Detailed versioned local evidence is stored in `catalog.sqlite3`. Counts distinguish registered entries, locally inspected installations, documentation, observed capability tests and verified workflows. The report explicitly records that universal mastery has not been verified.

## Resource bounds and remaining gaps

The local scanner inspects up to three accessible installation roots per entry, three subdirectory levels, 2,048 directory entries and 256 relevant files, with approximately one second for enumeration/static analysis per app. Selected content reads have additional byte allowances. Symbolic links, junctions, network roots, drive roots and common profile/cache directories are excluded. Large or inaccessible installations are reported as partial; a partial scan cannot be presented as complete. Small watches of previously selected files and primary executables still detect changes when full enumeration is partial. Inspection is limited to observed files and bounded samples; changes outside that set can be missed. There is no daily cap on this local stage.

Windows metadata probing has a 45-second timeout, a 2 MB response allowance and bounded class/service enumeration. Native UI observation can depend on an application's accessibility responsiveness. An unregistered portable app without a discovered shortcut or executable registration can remain undiscovered. Binary structure and manual coverage do not provide complete semantic understanding. Operating protected/elevated apps, visual canvases, arbitrary software/OS versions and complex workflows still needs additional adapters and actual operation evidence.

## Validation

All 256 cloud checks pass. The new tests use actual temporary installation files, real PE parsing, SQLite persistence and the real task runner, with simulated Windows registrations, desktop and model responses. They cover clean-Windows onboarding, subsequent app installation, COM/file-type evidence, installed-manual study without web discovery, independent task execution/output verification, restart caching, removal/reinstallation, same-version updates including same-size/timestamp-preserved patches, partial scans, symlink exclusion, provider backoff, cancellation and stale-evidence rejection. Existing tests retain signed update verification and real child-process execution. Both fixed PowerShell scripts also passed the official PowerShell 7.6.6 language parser on Linux; that checks syntax, not Windows registry/service behavior.

No native Windows/Office install or new Windows metadata probe has run in this cloud Linux environment. A previous authenticated Windows session was stopped. These checks demonstrate the onboarding/adaptation pipeline in controlled fixtures; they do not establish native Office operation, exhaustive machine coverage or all-app completion.
