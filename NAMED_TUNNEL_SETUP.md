# Connect through agent.papaprint.store — 0.6.8

This uses a dedicated hostname in your Cloudflare account. It gives you control over that hostname's routing and security settings. It does not guarantee that the cloud connection will succeed: the controller must receive and authenticate the helper's response before any Windows tests begin.

## 1. Create a dedicated tunnel in Cloudflare

Open your Cloudflare account for **papaprint.store**, then open **Cloudflare One / Zero Trust** and find **Tunnels**. Menu names can change; send a screenshot with credentials hidden if you cannot find it.

Create a **new Cloudflared tunnel** named **app-agent-windows**. Use a new tunnel for this helper so the existing website and other connectors keep their current routing.

Select Windows in the connector instructions. Copy the tunnel token or the displayed `cloudflared service install ...` command. Keep it on your computer. **Do not run that command or send it in chat.** The helper accepts the command as text, extracts the token, and launches its own temporary connector without installing a Windows service.

Add a published application route (also called a public hostname) with these values:

| Setting | Value |
| --- | --- |
| Subdomain | `agent` |
| Domain | `papaprint.store` |
| Path | Leave empty |
| Service type | `HTTP` |
| Service URL | `127.0.0.1:8765` |

The full hostname is **agent.papaprint.store**. The origin is **http://127.0.0.1:8765** on Windows; the public connection uses HTTPS. Save this route. Do not change the root website's DNS or attach this hostname to an unrelated tunnel. If Cloudflare reports an existing DNS record, inspect it before replacing it.

## 2. Start the updated Windows helper

1. Close the old App Agent and connection helper. Download the [Windows test kit](downloads/app-agent-windows-test-kit.zip), extract it into a **new folder**, and run `windows\Setup.cmd` inside that folder.
2. Run **`windows\ConnectNamed.cmd`**. It opens App Agent connection **0.6.8**, with named mode enabled and **agent.papaprint.store** filled in.
3. Paste the token or copied installation command into the **Cloudflare tunnel token** masked field. It is used only in the cloudflared child process environment; it is not saved to a file or placed in the process command line. The helper's diagnostic output redacts it.
4. Leave automatic Windows tests enabled. AI tests and documentation research are optional: enter your OpenAI API key in the separate local masked field and enable the AI option when wanted. They incur provider usage charges.
5. Click **Start connection** and accept its scope prompt. Leave the helper open. After registration, click **Copy connection diagnostics** and send the copied report to the testing chat. It includes the public pairing link; it contains no tunnel token or provider key.

The helper binds the fixed loopback port **8765**. If the port is busy, it reports that problem and stops; it does not choose a different port or terminate another program. The connection lasts at most two hours. STOP/disconnect or closing the helper cancels its jobs and stops its connector. No RDP, SSH or inbound firewall rule is needed.

## 3. Let the controller verify the connection

The cloud controller uses the existing private identity outside the repository and explicitly selects your hostname:

```sh
.venv/bin/python -m app_agent.remote_client \
  --allowed-host agent.papaprint.store \
  --pairing-link '<full public pairing link from this helper session>' \
  --key-file /workspace/.app-agent-controller/controller-private.json info
```

Only an authenticated, decrypted `/info` response establishes pairing. The controller can then submit the already authorized tests and retrieve their evidence. Native tests use disposable Notepad data and clear Calculator; leave the desktop untouched while they run. Other app tasks require the helper's local grants for the intended controls.

Opening `https://agent.papaprint.store/info` in a browser normally returns the helper's JSON rejection because browser requests lack a controller signature. This demonstrates that the browser reached a helper endpoint; it does not prove the cloud connection or authenticate the helper.

## If this hostname is blocked

Copy the helper diagnostics before stopping it. A missing DNS hostname, 404, Cloudflare error page, and the helper's JSON signature rejection are different outcomes. Avoid repeatedly restarting the tunnel without diagnosing the current response.

For a Cloudflare rejection, use the actual request time and Ray ID to inspect **Security events** for this owned hostname. The Ray ID alone does not explain the rule. If a rule is responsible, change only the identified rule for **agent.papaprint.store**, keeping the helper's request authentication and encryption. Do not disable protection for the entire website. Browser-header impersonation is not a connection setup step.

If source-IP filtering is needed, Cloudflare and Codex guidance recommends maintaining the applicable published egress ranges from [OpenAI's feed](https://openai.com/chatgpt-agents.json), refreshing them daily. Those ranges are shared infrastructure, so IP allowance cannot replace the helper's signature checks. Account limits and the specific matched rule determine whether this approach is available. Do not add ranges or relax settings until the actual event establishes why the owned hostname was blocked.

An interactive Cloudflare Access login page also prevents the current machine client from reaching the helper. This version does not implement Cloudflare Access service-token authentication. Configure a dedicated helper route rather than changing existing website access policies.

## What has been tested

The 0.6.7 checkout and extracted-kit installed-wheel suites each passed **184 tests**. They exercise real signatures, encryption and loopback HTTP, plus simulated Windows/native/model paths. The live 0.6.6 session completed all 13 checks: **12 passed, one failed, zero skipped/cancelled**. AI Calculator passed after seven actions with display 45. Independent documentation-to-practice still declined a suitable experiment after researching five capabilities. A subsequent bounded study left ten documented apps, 45 unverified capabilities and three unexecuted plans among 404 detected apps.

Version 0.6.7 adds observed editor control context, one bounded follow-up documentation study when no practice is supported, and retained failure diagnostics. The live 0.6.7 result below verifies the follow-up on the tested host. The existing tunnel/hostname/origin are unchanged; no new DNS or tunnel configuration is needed. Successful checks do not establish 80% completion or universal app mastery.

On October 8, 2026, the authenticated **0.6.7** Windows suite passed **all 13 checks**, with zero failed/skipped/cancelled checks. Calculator verified 45 after seven model-selected actions. Independent Notepad practice recovered from an unsupported initial plan through one additional technical documentation study: ten capabilities documented, its own text experiment generated, one typing action executed, and exact editor text verified. The isolated test catalog records one observed capability and nine untested capabilities. A read-only persistent report confirmed that ten documented apps, 45 unverified capabilities and three unexecuted plans survived the helper restart. These results establish the tested workflows; broader app families, repeated practice, real update adaptation, microphone use and live cancellation remain acceptance gaps. Full evidence remains private in ignored `remote-results/067-self-test.json` and `067-learning-report.json`.

Version 0.6.8 adds native process IDs to window listing, ready/unexecuted experiment details to learning reports, and optional exact `result_control_id` verification for generic tasks. Existing local control grants still apply. The speech self-test is explicitly optional: `{"with_cloud":true,"with_voice":true}` adds a fourteenth generated-speech-to-editor check using Windows SAPI and local provider transcription; it never records a microphone. It incurs transcription/reasoning charges. The running 0.6.7 helper cannot execute new 0.6.8 code or replace itself through the fixed job API. Upgrade locally using Setup.cmd and ConnectNamed.cmd in a fresh extracted folder, then reauthenticate the new public pairing link before these tests. No tunnel/DNS changes are required. The 0.6.8 cloud and fresh packaged-wheel suites passed 195 tests; the new native paths and live speech remain unverified. A second live 0.6.7 suite passed 12 and failed independent practice; retain that reliability failure separately from the first all-13 pass.
