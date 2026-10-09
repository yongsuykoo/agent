# Reusable browser sessions — 0.16.0

A named session keeps a dedicated Edge/Chrome profile so an authorized browser task can reuse a site's sign-in instead of starting with empty cookies every time. It runs locally in the standalone agent; no Cloudflare relay is required. Existing browser goals continue to use fresh temporary profiles.

## Configure once

In the Windows interface, choose **Background & schedules → Browser sessions**. Enter a short session name, such as `work`, and the application's public HTTPS sign-in URL. Choose **Open sign-in browser**, sign in directly to the site, then close all of that browser's windows. The agent retains that owned profile. STOP closes the sign-in browser.

Closing the window does not prove authentication succeeded. The actual site decides whether the session is still authenticated when a later task opens it. Expiry, MFA and account restrictions can require direct sign-in again. The agent does not read or enter passwords, export cookies or import a user's ordinary browser profile.

An equivalent command, from the extracted installation folder, is:

```text
.venv\Scripts\python.exe -m app_agent.cli browser-login work "https://your-app.example/sign-in"
.venv\Scripts\python.exe -m app_agent.cli browser-sessions
```

These are syntax examples; replace the URL with your actual service. Sign-in uses no planning provider and never asks for a provider key. The sign-in browser allows human-driven authentication popups. Automated task execution continues to observe one managed tab.

## Submit an account task

Choose Automatic app selection and enter a goal with this form:

```text
Use browser session "work" at "https://your-app.example/form" to enter Hello in Message and click Apply and verify exactly: "Saved: Hello"
```

Choose the intended session explicitly; the agent never guesses which account to use. All automated top-level observations and action destinations must remain on that session's configured origin (scheme, hostname and port). Other public HTTPS resource requests, such as CDN assets, still pass through the ordinary destination checks. A different app origin needs a different named session. Human sign-in can use the site's external identity provider before automated tasks start.

Authorized goals can run in the durable queue, worker and schedules without separate approval of every action. The first unfamiliar workflow still needs the configured planning provider. An exact repeat can reuse a verified recipe without another provider call, but it checks the live controls and independently observes the requested output. Browser version, profile identity or manual sign-in revision changes invalidate the recipe. No session is assumed to be authenticated merely because its profile exists.

## Ownership and recovery

Each named profile lives under the local agent data directory's `browser-sessions` folder. Names map to hashed folder paths. A profile marker and strict metadata prevent accidental account substitution; one process owns a profile at a time. Tasks wait automatically when a profile is busy, provided they have no uncertain prior effects. Opening sign-in again rotates the recipe revision even if the user switched accounts.

The existing journal records browser actions before dispatch. An interrupted, unverified submission remains `needs_review` and is not repeated automatically. A verified restart rechecks retained historical evidence without reopening the site. This historical result does not certify the current external service state. A new repeat task intentionally runs again with fresh verification.

**Forget selected session** deletes only the selected agent-owned profile and its retained sign-in data. The equivalent command is `forget-browser-session work`. Busy profiles cannot be deleted. Ordinary personal browser profiles are unaffected. Session profiles are excluded from Git and release archives. Cookies remain Chromium-managed local data; this feature does not add independent cross-platform encryption to the browser's profile storage.

## Automatic acceptance and limits

`windows\TestBrowser.cmd` now runs thirteen disposable checks without an API key. Five added checks use real Chromium and a local HTTP test application to verify retained HttpOnly authentication across browser restarts, separate account profiles, authenticated guarded replay, exclusive ownership and forgetting a session. A deterministic fixture planner drives these tests; they do not demonstrate planning quality on an arbitrary site.

The adapter still supports the bounded top-level DOM tools described in [BROWSER_TASKS.md](BROWSER_TASKS.md). File uploads/downloads, password/OTP entry, canvas, iframe/shadow-root traversal and select menus remain unavailable in this route. Complex sites, actual account service delivery, native Windows acceptance, repeated real-model reliability, voice and universal installed-app mastery remain unfinished. There is no claim that stored cookies imply successful email delivery or account authorization.
