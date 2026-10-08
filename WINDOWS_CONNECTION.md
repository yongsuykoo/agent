# Connect the Windows desktop to the cloud — 0.8.0

This companion makes a temporary outbound connection from your logged-in Windows desktop. The cloud controller can then inspect apps/windows, run the automatic self-test, research apps, and request tasks in locally granted controls. It is not a desktop video stream or a remote shell.

## Start the companion

1. Close the old App Agent. Download the current repository ZIP and extract into a fresh folder. Run `windows\Setup.cmd`.
2. For your own hostname, follow [NAMED_TUNNEL_SETUP.md](NAMED_TUNNEL_SETUP.md) and double-click **`windows\ConnectNamed.cmd`**. For a temporary Quick Tunnel, use **`windows\Connect.cmd`**. Both launch through Python, so PowerShell script execution is not required and its execution policy is unchanged. They install Cloudflare's `cloudflared` through WinGet when missing; WinGet's integrity checks remain enabled. No inbound firewall rule or router port-forward is created. Windows may require approval to install the package. If WinGet is unavailable, install cloudflared using the official Cloudflare Windows instructions and retry.
3. In **App Agent connection — 0.8.0**, leave automatic tests enabled. Named mode also requires your hostname and the tunnel token entered in its masked local field. For live model tests/research, enter your OpenAI API key locally and enable the AI option. It incurs provider charges. Enable cloud app tasks if you want the controller to operate other disposable app windows after local grants.
4. Click **Start connection** and accept the displayed scope. The helper checks its local HTTP server and waits for Cloudflare to log a registered transport connection before displaying the link. Copy the **entire pairing link** and send it to this chat. The link contains the temporary relay address and the Windows session's public verification key. It contains no API key, password, or private key. Relay registration alone does not prove cloud reachability; the controller must authenticate the `/info` response.
5. Leave the helper open and the desktop unlocked. The controller can now submit jobs and read encrypted results directly. You do not enter test commands or upload reports manually. Native tests clear Calculator and operate their own disposable Notepad document; avoid touching the desktop while they run.

For another app task, the helper shows the task and selected window, then lets you select permitted controls. Open disposable data and grant only the intended controls. That grant lasts for that app/version/window/process until STOP/disconnect. It is permission, not teaching. New controls and other windows are excluded. A save/delete/send button can still affect data if you grant it. Missing permission is reported as a blocked task, never a passed workflow.

The connection expires after two hours. **STOP / disconnect**, Escape, Ctrl+Alt+F12, or closing the helper cancels further actions and terminates its relay. In-flight provider requests may take up to 90 seconds to return. Start a fresh helper process for a new session. This does not install a background service or configure Windows SSH/RDP.

## Diagnose a connection failure

Click **Copy connection diagnostics** and paste the report into the testing chat. The full report also appears in the white log box, so it can be read or captured there when clipboard transfer is confusing. It includes the local startup check, relay process status, public relay URL, registration count and the latest 12 redacted relay log lines. Once registration succeeds, the report also includes the full public pairing link; no separate link copy is needed. It contains no provider key, tunnel token, private controller identity or app/window contents. Copy it before closing the helper, especially when registration times out after 90 seconds.

Cloudflared parses configuration-file routing before its CLI origin ([official source](https://github.com/cloudflare/cloudflared/blob/master/ingress/ingress.go)). The helper passes its own temporary empty YAML configuration, excluding inherited tunnel settings from that child process. Quick mode selects its loopback `--url`; named mode selects its account-managed tunnel using the locally entered token. Named mode binds only `127.0.0.1:8765`, matching the route you configure in Cloudflare. It refuses a busy port instead of silently changing it. It does not change or delete existing Cloudflare configuration or disable TLS verification, and does not prove that inherited routing caused the reported 404. The temporary file is removed after the relay exits.

Opening the public URL with `/info` appended in a browser should return `{"error":"Request rejected. Check pairing, request signature, clock and size."}` with HTTP 403. That is the normal response to an unsigned browser request; it does not authenticate the server. A browser 404 instead indicates that the requested URL did not serve this helper endpoint. A DNS NXDOMAIN indicates a missing hostname. A plain-text `Your request was blocked.` response differs from the helper rejection and does not establish a credential or controller-key problem. Compare these responses with the helper diagnostics before changing network settings or restarting repeatedly.

Version 0.6.5 corrects the occupied-port failure reported during 0.6.4 Windows setup. The server disables address and port sharing and requests Windows exclusive address use before binding. If that option or binding fails, startup closes the socket and reports the error. Setup retains the occupied-port test; it is not skipped or weakened.

## Pairing and privacy

`windows\cloud-controller.json` contains only the pinned controller public keys. The corresponding private controller identity stays outside the repository in this cloud workspace. The Windows helper generates a separate signing identity for each session; its public key is in the pairing link. Requests require the pinned controller's signature, include timestamps, and reject repeated nonces. Results are encrypted to the controller and signed by the Windows session. The relay cannot decrypt the result bodies; request operations/metadata are visible to the relay under TLS termination.

Provider keys remain in the Windows process. They are not sent to this cloud controller, stored in connection files or committed to GitHub. The controller may receive installed app names, requested window contents, task logs, and test evidence according to the enabled scope. Those results are not uploaded to a public repository. No screenshot transmission is implemented by this companion. Close the normal App Agent during companion tests to prevent competing background automation.

The fixed job types are `inventory`, `windows`, `inspect_window`, `learning_report`, `self_test`, `study`, and `task`. Inspection binds the exact window handle/process. Tasks also bind the catalog app generation and require a local control grant. Study batches are bounded to five apps and three experiment designs, within the daily budget. Task execution is bounded to 24 planning steps. The queue allows four outstanding jobs and 200 jobs per session. No remote caller can supply a shell command, script, installer, arbitrary file path, or change the controller key.

## Cloud controller use

Use the existing cloud private key; do not generate a replacement silently. Pairing a new key requires an updated public-key file and a fresh Windows helper launch. No key values belong in chat or tool output.

```sh
.venv/bin/python -m app_agent.remote_client \
  --pairing-link '<full public pairing link>' \
  --key-file /workspace/.app-agent-controller/controller-private.json info

.venv/bin/python -m app_agent.remote_client \
  --pairing-link '<full public pairing link>' \
  --key-file /workspace/.app-agent-controller/controller-private.json \
  --parameters '{"with_cloud":true}' --wait \
  --output /workspace/remote-results/self-test.json self_test
```

Long-running jobs return a job ID and can be polled with `job --job-id <id>`. Do not resubmit a job merely because a request times out. `completed` means the operation returned; the nested self-test counts or task outcome determine whether it passed. Missing cloud credentials produce skipped checks and a partial report, not full acceptance.

For named mode, add `--allowed-host agent.papaprint.store` to each controller command. The hostname must match exactly; custom hosts are rejected unless explicitly selected. A Quick Tunnel link remains accepted without this option.

The cloud environment must allow HTTPS/443 to the exact selected hostname, either your named host or the generated Quick Tunnel subdomain. A saved environment draft is not proof that this access is active. Keep existing package-manager and API domain settings. After a network change, verify the actual request; repeated publication or tunnel restarts without new evidence do not diagnose an unchanged 403. A Cloudflare Ray ID alone does not identify which security rule rejected a request.

## Validation

Regression tests exercise real Ed25519/X25519/AES-GCM operations and a real loopback HTTP server: forgery, body/route changes, replay/expiry, wrong server identity, encrypted results, queue bounds, cancellation, local scope validation and the automation thread. Native/model app execution is simulated in these cloud tests.

On October 8, 2026, the controller authenticated and decrypted live Windows responses through the named hostname. The 0.6.5 AI-enabled suite passed 11 checks and failed two. The subsequent **0.6.6** run passed **12 checks and failed one**, with none skipped or cancelled: all native checks, both AI Notepad replacements and AI Calculator passed. Calculator performed seven actions and verified 45. Independent documentation-to-practice still declined a suitable experiment after researching five capabilities.

The persistent catalog now has ten documented apps, 45 unverified capabilities and three unexecuted plans among 404 detected apps. Version **0.6.7** adds observed editor control context, one bounded follow-up study on unavailable practice and retained failure diagnostics. Its checkout and extracted-kit suites passed **184 tests**, and the live 0.6.7 result below verifies the latest learning correction on the tested host. The existing hostname and origin remain unchanged. Windows cancellation/restart checks and fresh WinGet installation also remain unverified. Successful pairing and these checks do not establish 80% completion or universal app mastery.

On October 8, 2026, the authenticated **0.6.7** Windows suite passed **all 13 checks**, with zero failed/skipped/cancelled checks. Calculator verified 45 after seven model-selected actions. Independent Notepad practice recovered from an unsupported initial plan through one additional technical documentation study: ten capabilities documented, its own text experiment generated, one typing action executed, and exact editor text verified. The isolated test catalog records one observed capability and nine untested capabilities. A read-only persistent report confirmed that ten documented apps, 45 unverified capabilities and three unexecuted plans survived the helper restart. These results establish the tested workflows; broader app families, repeated practice, real update adaptation, microphone use and live cancellation remain acceptance gaps. Full evidence remains private in ignored `remote-results/067-self-test.json` and `067-learning-report.json`.

Version 0.6.8 adds native process IDs to window listing, ready/unexecuted experiment details to learning reports, and optional exact `result_control_id` verification for generic tasks. Existing local control grants still apply. The speech self-test is explicitly optional: `{"with_cloud":true,"with_voice":true}` adds a fourteenth generated-speech-to-editor check using Windows SAPI and local provider transcription; it never records a microphone. It incurs transcription/reasoning charges. The running 0.6.7 helper cannot execute new 0.6.8 code or replace itself through the fixed job API. Upgrade locally using Setup.cmd and ConnectNamed.cmd in a fresh extracted folder, then reauthenticate the new public pairing link before these tests. No tunnel/DNS changes are required. The 0.6.8 cloud and fresh packaged-wheel suites passed 196 tests; the new native paths and live speech remain unverified. A second live 0.6.7 suite passed 12 and failed independent practice; retain that reliability failure separately from the first all-13 pass.

STOP transport evidence: the live 0.6.7 empty-body POST was rejected with an unsigned 403, while a signed JSON body reached an authenticated route rejection. No live disconnect was established. Version 0.6.8 sends a signed empty JSON object for STOP and accepts only that object or the legacy empty body. Real authenticated loopback HTTP tests verify disconnect and rejection of extra commands. The live named-host STOP path remains pending an upgraded Windows helper.

Latest live acceptance: 0.6.8 passed 12 checks and failed two (invalid follow-up capability expected_result; transcribed exact-text command lacking the required colon). Native PID window listing, exact-process inspection and ready-plan reporting passed. Idle STOP returned an authenticated stopped result after jobs finished. Version 0.6.9 fixes extraction structure/validation retries and accepts spoken text-command delimiters; these corrections still need an upgraded local helper for live verification. No tunnel/DNS changes are required.

Version 0.7.0 adds an automatic mode with a stable connection host and signed worker updates. After this one local installation, routine worker fixes no longer need helper restarts or new pairing links. Automatic mode is explicitly shown at startup, uses an eight-hour session, checks idle before tests, retains failures, and studies up to five apps/day within existing budgets. See AUTOMATIC_MODE.md for limits and pending live acceptance.
