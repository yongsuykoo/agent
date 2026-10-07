# Personal Windows app agent

Version 0.4.5 includes automatic Windows self-testing. Click **Self-test** in the agent, or run `windows\SelfTest.cmd`: it runs native and AI checks, uses a disposable Notepad document, clears Calculator, and saves a report. No manual task entry is required. Cloud checks use the existing session API key and incur provider usage charges. See [WINDOWS_TESTING.md](WINDOWS_TESTING.md) for scope and reporting, [ADVANCED_LEARNING.md](ADVANCED_LEARNING.md) for controls and practice, and [LEARNING_RELEASE.md](LEARNING_RELEASE.md) for discovery and research behavior.

Goal: independently research unfamiliar applications, build evidence-backed operational blueprints, execute tasks, and troubleshoot failures through chat and voice.

This prototype provides desktop registry, Start-menu, and Microsoft Store discovery, persistent app blueprints, and cloud AI documentation research. Its Windows interface supports typed tasks, push-to-talk transcription, supervised accessibility control, local session evidence, and troubleshooting advice. Apps without registration or Start-menu entries are not comprehensively discovered. See WINDOWS_TESTING.md and LEARNING_RELEASE.md for the test release.

## Development

Python 3.11 or later:

```sh
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\python.exe -m pip install -e .
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

The cloud development machine cannot control a user's Windows desktop. Windows validation must run on a Windows host with an interactive desktop. Consequential operations require explicit authorization; research and experimentation begin with read-only or disposable test data.

## Documentation research

Configure `AGENT_API_KEY` securely as an OpenAI API credential. `OPENAI_API_KEY` is also accepted on a local Windows installation. `AGENT_MODEL` defaults to `gpt-4.1`; the selected model must support the Responses API, web search, and JSON output. API and search usage incur provider charges.

```sh
app-agent research "Windows Calculator"
app-agent research "Windows Calculator" --source https://github.com/microsoft/calculator
app-agent blueprint "Windows Calculator"
```

Without `--source`, the agent searches online for documentation and retrieves up to three cited pages. Explicit URLs skip search. Research accepts up to five public HTTPS HTML/text pages, checks redirects, limits document size, removes script/style text, and records URLs, retrieval timestamps, and content hashes. PDFs and JavaScript-only pages are not supported yet. Direct connections check resolved IP addresses. With an HTTPS proxy, the proxy resolves destination hostnames; its egress policy must block private destinations. Use network egress restrictions to enforce isolation against DNS rebinding.

The model receives the app name, version, and retrieved public documentation text. It receives no desktop screenshots, credentials, or local files. Source indices are validated before saving; every resulting capability is marked `documented_unverified`, regardless of the model's claims. Citations establish provenance, not factual correctness. Execution tests will be required to verify capabilities. Research never executes instructions it reads. Existing verified capabilities are protected against replacement.

Tests exercise the pipeline with simulated model responses. Live cloud research requires credentials and access to `api.openai.com` and the documentation hosts; it has not yet been validated with a real model. Live retrieval of the Microsoft Calculator GitHub documentation passed through the managed HTTPS proxy. Live model extraction remains blocked by the missing API credential.
