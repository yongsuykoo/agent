# General Windows agent — 0.10.0

The purpose is a personal agent that discovers the machine, learns operational procedures without demonstrations, carries out chat/voice goals, checks results and adapts as software changes. An operating model grows from evidence; it is not the complete proprietary source code of Windows or every application.

The three goals are:

1. Discover Windows components, installed software and incoming installations.
2. Learn relevant interfaces and procedures from installed manuals, registrations, accessible controls, public documentation and execution evidence.
3. Interpret a task, select appropriate apps, operate them, verify results and reuse successful procedures while retiring stale ones.

Version 0.10.0 supplies the following general mechanisms, alongside existing UI automation, optional screenshot reasoning, voice submission and the Photoshop artifact adapter.

| Mechanism | Implemented behavior | Evidence limit |
| --- | --- | --- |
| Persistent system evidence graph | Links Windows, services, app versions, binaries, dependencies, manuals, registered interfaces, file types, documented capabilities and successful workflows. | Service/binary metadata and registered interfaces do not prove that an operation works. |
| Local retrieval | Ranks relevant evidence and installed apps for each submitted task. General planning and per-app execution receive the retrieved context. | Uses lexical retrieval; incomplete documentation does not exclude other installed apps from selection. |
| Incoming installation observation | A separate read-only Windows process monitor polls every ten seconds while the new UI/helper is open. Likely installer/updater names trigger public product-resource inspection and an inventory refresh. | Heuristic names can miss short-lived or unusually named installers, protected processes and downloads that have not launched. It does not block or intercept installation. |
| Provisional study | Background study can research a product candidate before it is registered. Its source is explicitly unconfirmed; no candidate executable is run. | Research needs the enabled AI option and provider access. Generic installer names are insufficient; research may finish after installation. |
| Registration reconciliation | After an observed installer exits, one exact product-name/version match to a new or changed app generation can reuse matching preview documentation. Existing unchanged registrations are insufficient. | Product resources are untrusted metadata. A matched registration is not a successful execution test or proof that an installation completed correctly. |
| Unknown window identity | General routing can identify an app by its registered full executable path even when a document title omits the app name. File Explorer additionally requires a folder-window class. | Inaccessible processes, shared processes without a distinguishing surface, and ambiguous documents remain unresolved. |
| Windows GUI surfaces | Discovers Settings, File Explorer, Task Manager and Control Panel when their fixed executables are present. Uses fixed OS-directory launch routes and OS-build generations. | No arbitrary shell, driver installation, hidden API invocation or permission bypass. Individual GUI operations need observed controls and result evidence. |
| Adaptation and reuse | App-generation changes retire old knowledge and routines. OS-build changes invalidate cached multi-app plans. Successful unchanged routines can execute with zero model calls and fresh output checks. | One successful workflow is not a repeatability certificate. Failed and untested capabilities remain gaps. |

Local inventory, graph building, installer observation and retrieval have no provider calls or daily cap. Public research and task reasoning use the configured provider. `0` in the daily study/design setting is uncapped at the application level; the provider can still bill, rate-limit or reject requests. Existing bounded file readers, parallel document readers and up to four research workers keep onboarding responsive.

Only public product facts are used for provisional research. The process probe does not query command lines, MSI arguments, usernames or credentials. Retrieved task context omits previous user-task labels, manual text, document values and arbitrary window/control names; current live task observations remain a separate input governed by existing permissions. Password controls are excluded. Website and registration data are evidence, not instructions.

The latest standalone app starts the monitor automatically with `windows\Start.cmd`. The latest connection helper also starts it when automatic maintenance is enabled. Older helpers can download the signed task worker, but a worker update does not replace their already-running UI/monitor implementation. STOP and closing the helper retain their existing behavior; installer observation stops when its UI closes and does not alter any installer.

Inspect the local evidence with **Machine knowledge**, or with the installed CLI:

```text
app-agent knowledge-map
app-agent knowledge-query "Create a spreadsheet report and print it"
app-agent machine-report
```

The architecture supports learning and attempting tasks in unfamiliar apps; it does not certify that every Excel workflow, printer, email account or other application is supported. Print jobs and sent email are external effects; observations must distinguish preparing an output from actually delivering it. No live Windows acceptance of the new installer monitor or OS surfaces has run in this cloud Linux environment. The 305 automated cloud checks include simulated Windows adapters, real SQLite persistence and task-engine regressions. They are not 305 real app certifications, and no completion percentage is inferred from them.
