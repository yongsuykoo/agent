# Version 0.2.0: independent app discovery and learning

This release adds the discovery-to-research-to-practice loop. It is not a claim that every app is fully understood or that arbitrary app tasks are reliable. Each app has inspectable evidence of what was documented and what was exercised.

## What happens automatically

With the interface open, the agent scans on startup and every five minutes. It combines desktop uninstall registrations, Start-menu application identities, and current-user Microsoft Store packages. New apps are queued for research. Changed app versions invalidate that version's blueprint and exclude old tested workflows from current planning. Partial scans never silently declare apps removed from an unavailable source.

Background study is enabled by default when an API key is available, with a limit of three app research attempts per day using the Windows machine's local date. Failed attempts count towards the limit and back off. The interface displays the limit; turn off background study or change it from 1 to 50. Explicit research and user tasks are outside the background budget. API usage is billed by the provider. Document research may require two cloud requests per app plus web-search charges; practice and task execution make additional requests.

The agent finds public manuals independently, retrieves source pages, and maps documented features, steps, inputs, prerequisites, expected results, troubleshooting, and recovery guidance. It records uncertainty and source references. Successful research is not repeated at every launch. Running apps can be inspected read-only to retain the observed accessibility interface; no arbitrary app is launched solely for background inspection.

## Using the release

1. Close the older version. Download the current GitHub repository ZIP, extract into a new folder, and run windows/Setup.cmd then windows/Start.cmd.
2. Leave the window dropdown at **Automatic — choose app from command**. Wait for the inventory status to show detected apps.
3. Enter **Use Calculator to calculate 23 plus 19 and verify the result**. The agent selects the discovered app, opens it if needed, researches it, operates its accessible controls, and checks visible results.
4. Approve each action, or click **Authorize remaining task actions** while an action awaits approval. This is a one-task grant, ends at completion/STOP, and applies only to the selected app window. Start with disposable data.
5. Open **Apps & knowledge** to inspect discovered apps, versions, status, documentation blueprints, and exercised workflows. Select an app there to set its research name.
6. Use **Practice app** to have the agent generate a reversible experiment from that app's documentation. You provide no demonstration. Execution still uses step/task authorization.
7. Optional: enable **Auto-practice Calculator** and grant its explicit permission. The agent may open Windows Calculator, clear its calculation, and test a self-generated arithmetic task without individual approvals. Only a strict arithmetic-button allowlist is permitted. Other apps do not inherit this permission. It tries at most once per app version per day and stops repeating after a result-observed workflow is saved.

STOP also pauses background study until **Apply / resume** is clicked. Installation monitoring continues while the interface stays open. Closing the agent stops monitoring; new apps installed while closed are found on its next startup. No Windows service is installed.

## Learning evidence

`queued`: detected, not researched. `documented`: a source-backed blueprint exists, with individual procedures still marked `documented_unverified`. `research_failed`: a specific prerequisite failed and a later retry is scheduled. Practiced workflows carry `result_observed_once`, app version, executed actions, and observation evidence. A visible result does not prove every capability works. Workflows with zero executed actions are not added as practiced knowledge.

The next task can use previous workflow steps as planning hints, with controls freshly observed and approvals revalidated. It does not blindly replay old numeric control indices. Version updates invalidate current knowledge; historical evidence remains locally retained.

## Limits requiring further development and Windows validation

Arbitrary portable executables without installation or Start-menu registration are not comprehensively inventoried. Running windows remain manually selectable. App version metadata can be unavailable, so not every silent update is detectable. Automatic window matching uses app aliases and titles; ambiguous, localized, or unusual windows require manual selection. Registry-only entries without launch identities cannot be automatically opened. Background research covers a bounded set of public HTML/text sources; inaccessible manuals, PDFs, undocumented internals, and canvas interfaces need additional adapters.

Unattended mutation experiments are restricted to the Calculator sandbox. Other apps support independently proposed experiments with user authorization, not unrestricted background modification. The app cannot recover a closed-source application's complete internal design or guarantee universal understanding. More interfaces, result validators, and safe per-app experiment boundaries are still needed.

New inventory, monitoring, automatic launch, practice, and learning behavior has been tested with simulated Windows/model components in the cloud. The updated release must now run on a real Windows desktop to validate OS integration. Existing user testing established Calculator observation and a supervised calculation on prior releases.

## Data

Inventory, settings, observed interfaces, versioned blueprints, and workflow evidence are stored in `%LOCALAPPDATA%\AppAgent\catalog.sqlite3`; existing legacy blueprints and sessions remain. No API key is written to the catalog. Model routing sends app names/identities and the command; research sends app name/version and public documentation; execution sends selected-window text after consent. Background read-only interface snapshots are stored locally. Do not select sensitive windows. See WINDOWS_TESTING.md for other privacy and stop-control details.

CLI: `app-agent scan`, `app-agent apps`, and `app-agent study-next --daily-limit 3` expose inventory and the bounded research queue without the GUI.
