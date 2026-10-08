# Personal Windows app agent

Version **0.6.7** includes a locally launched Windows connection companion with support for your own Cloudflare hostname. For `agent.papaprint.store`, follow [NAMED_TUNNEL_SETUP.md](NAMED_TUNNEL_SETUP.md) and run `windows\ConnectNamed.cmd` after setup. Temporary Quick Tunnels remain available through `windows\Connect.cmd`. It supports automatic tests/research and tasks limited to locally granted app controls. Requests are authenticated and results encrypted; your provider key stays on Windows. See [WINDOWS_CONNECTION.md](WINDOWS_CONNECTION.md). Publishing the companion does not establish a live connection or 80% completion; [GOAL_MILESTONES.md](GOAL_MILESTONES.md) defines the remaining acceptance evidence.

Release 0.6.7 cloud validation: **184 regression tests passed**, including actual cryptography and authenticated loopback HTTP, plus simulated desktop/model execution. All 184 also passed using the packaged wheel in a fresh environment from the extracted Windows test kit. These checks do not establish live Windows app mastery.

Version 0.6.6 gives the planner the actual observed output after each action and records control identities alongside changing numeric indices. Completion failures include the actual display instead of only the proposed explanation. Generated practice tasks use a strict schema and receive up to three bounded validation/repair attempts; an inconsistent task is never executed. Cancellation is checked between planning calls. The live 0.6.6 retest passed Calculator: seven model-selected actions produced and verified 45. Independent practice still failed because the planner reported no suitable disposable experiment. No failure was converted into a pass.

Live 0.6.5 evidence on October 8, 2026: the cloud authenticated and decrypted the named-host connection and ran all 13 automatic checks on Windows Python 3.14.0. **11 passed, 2 failed, none skipped or cancelled.** All nine native checks and both AI Notepad replacements passed. AI Calculator produced 10 instead of 45; verification rejected its completion claims. Independent Notepad study documented six capabilities, but its generated task disagreed with its expected output and was rejected before execution. An earlier native-only run passed nine checks and skipped four AI checks. The failures remain acceptance gaps.

Latest live 0.6.6 suite on October 8, 2026: **12 passed, one failed, none skipped or cancelled**. Native operations, both AI Notepad replacements and AI Calculator passed. Independent Notepad research documented five capabilities, but the planner declined to generate a disposable experiment. This remains a failure, separate from the earlier inconsistent-plan failure.

Version 0.6.7 supplies observed editor control types/actions to the experiment planner. If the first blueprint provides no suitable experiment, the automatic learning check performs one additional documentation study focused on those observed controls and the existing permission scope, then tries planning again. It never converts an unsupported plan to a supported one, executes an invalid task, or expands permissions. Failures retain the proposed unsupported plan and documentation source/capability evidence in the private report. Cloud tests cover successful follow-up, a bounded second refusal and cancellation without editing. The live 0.6.7 result below verifies this follow-up on the tested Windows host.

Latest live **0.6.7** validation on October 8, 2026: **all 13 checks passed**, with zero failures/skips/cancellations. AI Calculator executed seven actions and verified display 45. Independent Notepad study initially produced no supported experiment, then used the bounded follow-up technical documentation search to build a ten-capability blueprint. The agent generated its own exact-text experiment, typed it in one action and verified the complete editor value. The isolated learning catalog records one capability with an observed test and nine untested capabilities. This confirms one live documentation-to-practice workflow, not complete app mastery or repeatability across all applications. Private evidence is in `remote-results/067-self-test.json`.

A read-only learning report after the helper restart confirmed that the persistent catalog retained ten documented apps, 45 unverified capabilities and three unexecuted experiment plans. The isolated self-test's verified capability is not silently counted in the persistent catalog.

The two bounded five-app research batches now leave the persistent catalog at **404 discovered apps, ten documented apps, 45 documented capabilities and three ready experiment plans**, with zero observed capability tests in that catalog. The latest batch documented two apps and deferred three. Planned experiments have not been executed or verified; the isolated self-test catalog is separate. Full reports, logs and installed-app metadata remain private under ignored `remote-results`.

Version 0.6.5 also corrected the occupied-port failure found during 0.6.4 Windows setup: it disables address/port sharing, uses Windows exclusive address binding and closes the socket on failure without trying another port. The named connection has since run live Windows checks successfully. Cloud coverage of the exclusive-bind option uses simulated sockets; this does not establish every Windows installation scenario.

Version 0.5.0 adds **Learn all apps**: persistent batch documentation research, follow-up technical-manual study, and experiments for individual capabilities. The agent designs its own tasks, retains failures for retry, and measures execution evidence separately from documentation. Research runs separately from desktop automation so chat tasks can start while research is pending. See [AUTONOMOUS_LEARNING.md](AUTONOMOUS_LEARNING.md) for starting the campaign, budgets, and remaining gaps.

Automatic Windows self-testing remains available: click **Self-test**, or run `windows\SelfTest.cmd`. It operates a disposable Notepad document and Calculator and saves a report without manual task entry. The new thirteenth check researches Notepad documentation, designs its own experiment and verifies execution through the persistent queue. Cloud checks and learning use the session API key and incur provider usage charges. See [WINDOWS_TESTING.md](WINDOWS_TESTING.md) for reporting and [ADVANCED_LEARNING.md](ADVANCED_LEARNING.md) for control permissions.

Goal: independently research unfamiliar applications, build evidence-backed operational blueprints, execute tasks, and troubleshoot failures through chat and voice.

Live Windows validation: the uploaded 0.4.6 self-test report passed all 12 checks with Python 3.14.0. It discovered 404 installed apps, verified three native Calculator calculations, verified Notepad text entry/replacement, punctuation, Unicode, multiline text and saving from disk, and passed two AI Notepad tasks plus an AI Calculator task (7 executed actions, displayed result 45). This validates those operations on the tested computer; discovery of the other apps does not establish operational mastery. The general all-app learning goal remains unfinished.

Release 0.5.0 validation: 129 cloud regression tests passed, including the complete simulated 13-check Windows suite. All 129 also passed using the packaged wheel installed in a fresh environment from the extracted Windows test kit. These are simulated desktop/model tests, separate from the 0.4.6 live Windows results. The latest live results above supersede this historical baseline; the thirteenth check has now passed live in 0.6.7 after earlier failed attempts.

This prototype provides desktop registry, Start-menu, and Microsoft Store discovery, persistent app blueprints, and cloud AI documentation research. Its Windows interface supports typed tasks, push-to-talk transcription, supervised accessibility control, local session evidence, and troubleshooting advice. Apps without registration or Start-menu entries are not comprehensively discovered. See WINDOWS_TESTING.md and LEARNING_RELEASE.md for the test release.

## Development

Python 3.11 or later:

```sh
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\python.exe -m pip install -e ".[bridge]"
.venv\Scripts\app-agent.exe discover
.venv\Scripts\app-agent.exe blueprint Calculator --create
.venv\Scripts\app-agent.exe blueprint Calculator
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

On Linux use `.venv/bin/python` and `.venv/bin/app-agent`. App discovery requires Windows. Knowledge records default to the user's local application data directory; `--data-dir` overrides it. Duplicate creation preserves the original record and reports an error.

## Build sequence

1. Foundation: inventory, persistent knowledge, evidence model.
2. Research: version-specific official documentation retrieval, source citations, structured capability extraction. Treat retrieved content as untrusted data, never as authority to execute instructions.
3. Windows control: accessibility-first observation and execution, visual fallback, task cancellation, scoped permissions, result verification.
4. Learning loop: controlled experiments, documented successes and failures, recovery procedures, revalidation after app updates.
5. Interface: chat, push-to-talk, progress display, and persistent stop controls.
6. Troubleshooting: relevant logs, reproducible diagnosis, reversible fixes, and regression checks.

Windows acceptance milestone: independently study one Windows app, complete three useful workflows without demonstrations, and recover from a reproducible failure. No capability is marked verified merely because documentation describes it.

Keep the local controller lightweight. Use cloud reasoning for difficult research and planning, cache verified workflows, and prefer APIs or accessibility controls over repeated screenshot analysis. OpenAI is the initial model provider; live reasoning requires an API key and a Windows execution host.

Windows validation must run on a Windows host with an interactive desktop. The cloud controller can request Windows checks after an authenticated companion connection is established. Consequential operations require explicit authorization; research and experimentation begin with read-only or disposable test data.

## Documentation research

Configure `AGENT_API_KEY` securely as an OpenAI API credential. `OPENAI_API_KEY` is also accepted on a local Windows installation. `AGENT_MODEL` defaults to `gpt-4.1`; the selected model must support the Responses API, web search, and JSON output. API and search usage incur provider charges.

```sh
app-agent research "Windows Calculator"
app-agent research "Windows Calculator" --source https://github.com/microsoft/calculator
app-agent blueprint "Windows Calculator"
```

Without `--source`, the agent searches online for documentation and retrieves up to three cited pages. Explicit URLs skip search. Research accepts up to five public HTTPS HTML/text pages, checks redirects, limits document size, removes script/style text, and records URLs, retrieval timestamps, and content hashes. PDFs and JavaScript-only pages are not supported yet. Direct connections check resolved IP addresses. With an HTTPS proxy, the proxy resolves destination hostnames; its egress policy must block private destinations. Use network egress restrictions to enforce isolation against DNS rebinding.

The model receives the app name, version, and retrieved public documentation text. It receives no desktop screenshots, credentials, or local files. Source indices are validated before saving; every resulting capability is marked `documented_unverified`, regardless of the model's claims. Citations establish provenance, not factual correctness. Execution tests will be required to verify capabilities. Research never executes instructions it reads. Existing verified capabilities are protected against replacement.

Development tests exercise the pipeline with simulated model responses. The user has demonstrated live documentation research and the Windows task checks described above. The cloud development machine has no provider credential or interactive Windows desktop. The authenticated companion has now executed the live checks and bounded research batch described above using the key held on Windows; broader campaign acceptance remains incomplete. Live retrieval of Microsoft Calculator documentation was checked through the managed HTTPS proxy.
