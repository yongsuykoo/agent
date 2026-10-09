# Browser tasks — 0.17.0

The agent can operate unfamiliar web interfaces through observed DOM controls using an installed Chromium-based Edge or Chrome. It opens a fresh temporary profile and one tab, reads rendered text and advertised controls, plans bounded actions, executes approved actions, and independently checks the exact requested output. Version 0.16.0 also supports an explicitly named, previously configured [owned account session](BROWSER_SESSIONS.md). Version 0.17.0 adds [dropdowns, open web components and same-origin embedded forms](NESTED_BROWSER_TASKS.md). The model cannot supply JavaScript or shell commands to this adapter. The fixed DOM tools run in an isolated JavaScript world.

## Submit a goal

In the standalone agent, choose **Automatic — choose app from command**. Browser goals use this form:

```text
Open "https://example.com" in a browser and inspect the page heading and verify exactly: "Example Domain"
```

For a form, use its actual public HTTPS URL and a result the page will render:

```text
Use the browser at "https://your-public-site.example/form" to enter Hello in Message, set Confirmed on, and click Apply and verify exactly: "Saved: Hello"
```

The second URL is a syntax example, not a provided service. Use the displayed field/button labels and expected status for your actual site. The submitted URL and expected text are preserved. With autonomous task permission enabled, the authorized goal runs without individual action prompts. STOP still interrupts further actions. Browser tasks run through the existing saved queue, background worker and schedules; they do not require a Cloudflare connection.

New tasks need the configured provider for planning. A successful workflow can be reused locally on an exact repeat if the browser revision and observed page URL, control identities, content and state still match. A failed live check returns the actual state to planning; no cached success bypasses independent result verification. There is no additional daily browser-task cap. Sixteen planning steps bound a single run rather than allowing an endless loop.

## Verification and recovery

Success requires the exact case-sensitive text in a rendered output element; a text-input value, button label, whole-body substring, hidden text or truncated result cannot prove success. The adapter observes eligible text/output/status elements up to its bounded DOM limits. TaskRunner re-observes on completion; the task director independently re-observes again before committing the checkpoint. A private JSON observation and SHA-256 proof are saved under the agent's `browser-evidence` directory.

Browser actions use the existing write-ahead action journal. If execution stops after dispatch and before output verification, the job retains `needs_review` instead of blindly repeating a submit button. Once an output is durably verified, recovery checks the retained evidence and does not reopen the page. This retained observation is historical evidence, not a new check of the external service. A newly submitted repeat task performs fresh live checks and may intentionally submit a new transaction.

## Automatic testing

`windows\TestBrowser.cmd` runs nineteen checks in installed Edge/Chrome with a disposable local web application and owned fixture profiles. It needs no API key, existing account, manual document or hosted site. The tests check real Unicode entry and HTTP form submission, unavailable controls, isolated-world state, premature completion, stale control/URL rejection, navigation, blocked out-of-scope redirects, persisted queue/local replay and interruption after a real submission. Five additional checks verify retained authentication, account isolation, authenticated replay, exclusive ownership and account-data removal. Six nested-interface checks cover dropdown safety, supported shadow/frame form execution, unavailable contexts, stale targets, guarded replay and inspection limits. The fixture uses a reviewed deterministic planner; these checks establish execution/recovery behavior, not model intelligence or arbitrary website reliability.

The cloud also runs these real-Chromium checks from the fresh installed wheel. Its Linux container lacks a usable Chromium sandbox, so only the fixed owned local test fixture uses `browser-smoke --trusted-fixture-no-sandbox`. This flag is forbidden for Windows and real browser tasks. Production browsing keeps Chromium's sandbox and TLS verification enabled. External traffic retains the configured HTTPS proxy; only the adapter's own DevTools socket and owned local fixture use loopback transport.

## Current scope

The adapter supports standard text fields, explicit checkbox state, native single-choice dropdowns, links and buttons in the main DOM, open shadow roots and same-origin embedded documents. It inspects up to 8,000 elements across 64 roots and 16 nested root levels, observes up to 200 interactive controls and 200 eligible output elements, and bounds text and transport sizes. Read-only/disabled controls, passwords and one-time codes, file uploads and downloads are unavailable. There is no arbitrary script action, imported personal browser history/profile, cookie export, canvas automation, cross-origin-frame/closed-shadow-root traversal, multi-select/custom-menu tools, desktop coordinates or screenshot verification in this route.

Named account sessions are implemented and tested against local authentication fixtures. Actual external account services, complex sites, complete mail delivery verification, browser-specific Windows acceptance and repeated real-model reliability remain pending. Browser control is one part of the overall agent; this release does not demonstrate understanding every program or the full Windows blueprint.
