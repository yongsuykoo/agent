# Personal Windows app agent

Version **0.6.6** includes a locally launched Windows connection companion with support for your own Cloudflare hostname. For `agent.papaprint.store`, follow [NAMED_TUNNEL_SETUP.md](NAMED_TUNNEL_SETUP.md) and run `windows\ConnectNamed.cmd` after setup. Temporary Quick Tunnels remain available through `windows\Connect.cmd`. It supports automatic tests/research and tasks limited to locally granted app controls. Requests are authenticated and results encrypted; your provider key stays on Windows. See [WINDOWS_CONNECTION.md](WINDOWS_CONNECTION.md). Publishing the companion does not establish a live connection or 80% completion; [GOAL_MILESTONES.md](GOAL_MILESTONES.md) defines the remaining acceptance evidence.

Release 0.6.6 cloud validation: **181 regression tests passed**, including actual cryptography and authenticated loopback HTTP, plus simulated desktop/model execution. All 181 also passed using the packaged wheel in a fresh environment from the extracted Windows test kit. These checks do not establish live Windows app mastery.

Version 0.6.6 gives the planner the actual observed output after each action and records control identities alongside changing numeric indices. Completion failures include the actual display instead of only the proposed explanation. Generated practice tasks use a strict schema and receive up to three bounded validation/repair attempts; an inconsistent task is never executed. Cancellation is checked between planning calls. These changes address failures observed in the latest live run; their live Windows retest remains pending.

Live 0.6.5 evidence on October 8, 2026: the cloud authenticated and decrypted the named-host connection and ran all 13 automatic checks on Windows Python 3.14.0. **11 passed, 2 failed, none skipped or cancelled.** All nine native checks and both AI Notepad replacements passed. AI Calculator produced 10 instead of 45; verification rejected its completion claims. Independent Notepad study documented six capabilities, but its generated task disagreed with its expected output and was rejected before execution. An earlier native-only run passed nine checks and skipped four AI checks. The failures remain acceptance gaps.

A separate five-app research batch documented three apps and deferred two after search/retrieval failures. The persistent catalog now contains **404 discovered apps, eight documented apps and 35 documented capabilities**, with zero observed capability tests and zero ready experiments in that catalog. Documentation is unverified evidence; it does not establish operation of those apps. The isolated self-test catalog is separate. Full reports, logs and installed-app metadata remain private under ignored `remote-results`.

Version 0.6.5 also corrected the occupied-port failure found during 0.6.4 Windows setup: it disables address/port sharing, uses Windows exclusive address binding and closes the socket on failure without trying another port. The named connection has since run live Windows checks successfully. Cloud coverage of the exclusive-bind option uses simulated sockets; this does not establish every Windows installation scenario.

Version 0.5.0 adds **Learn all apps**: persistent batch documentation research, follow-up technical-manual study, and experiments for individual capabilities. The agent designs its own tasks, retains failures for retry, and measures execution evidence separately from documentation. Research runs separately from desktop automation so chat tasks can start while research is pending. See [AUTONOMOUS_LEARNING.md](AUTONOMOUS_LEARNING.md) for starting the campaign, budgets, and remaining gaps.

Automatic Windows self-testing remains available: click **Self-test**, or run `windows\SelfTest.cmd`. It operates a disposable Notepad document and Calculator and saves a report without manual task entry. The new thirteenth check researches Notepad documentation, designs its own experiment and verifies execution through the persistent queue. Cloud checks and learning use the session API key and incur provider usage charges. See [WINDOWS_TESTING.md](WINDOWS_TESTING.md) for reporting and [ADVANCED_LEARNING.md](ADVANCED_LEARNING.md) for control permissions.

Goal: independently research unfamiliar applications, build evidence-backed operational blueprints, execute tasks, and troubleshoot failures through chat and voice.

Live Windows validation: the uploaded 0.4.6 self-test report passed all 12 checks with Python 3.14.0. It discovered 404 installed apps, verified three native Calculator calculations, verified Notepad text entry/replacement, punctuation, Unicode, multiline text and saving from disk, and passed two AI Notepad tasks plus an AI Calculator task (7 executed actions, displayed result 45). This validates those operations on the tested computer; discovery of the other apps does not establish operational mastery. The general all-app learning goal remains unfinished.

Release 0.5.0 validation: 129 cloud regression tests passed, including the complete simulated 13-check Windows suite. All 129 also passed using the packaged wheel installed in a fresh environment from the extracted Windows test kit. These are simulated desktop/model tests, separate from the 0.4.6 live Windows results. The latest live results above supersede this historical baseline; the thirteenth check has now run and failed validation before execution.

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
