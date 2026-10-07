# Connect the Windows desktop to the cloud — 0.6.1

This companion makes a temporary outbound connection from your logged-in Windows desktop. The cloud controller can then inspect apps/windows, run the automatic self-test, research apps, and request tasks in locally granted controls. It is not a desktop video stream or a remote shell.

## Start the companion

1. Close the old App Agent. Download the current repository ZIP and extract into a fresh folder. Run `windows\Setup.cmd`.
2. Double-click **`windows\Connect.cmd`**. Version 0.6.1 launches through Python, so PowerShell script execution is not required and its execution policy is unchanged. It installs Cloudflare's `cloudflared` through WinGet when missing; WinGet's integrity checks remain enabled. The connection uses Cloudflare's temporary Quick Tunnel service. No inbound firewall rule or router port-forward is created. Windows may require approval to install the package. If WinGet is unavailable, install cloudflared using the official Cloudflare Windows instructions and retry.
3. In **App Agent connection — 0.6.1**, leave automatic tests enabled. For live model tests/research, enter your OpenAI API key locally and enable the AI option. It incurs provider charges. Enable cloud app tasks if you want the controller to operate other disposable app windows after local grants.
4. Click **Start connection** and accept the displayed scope. Copy the **entire pairing link** and send it to this chat. The link contains the temporary relay address and the Windows session's public verification key. It contains no API key, password, or private key.
5. Leave the helper open and the desktop unlocked. The controller can now submit jobs and read encrypted results directly. You do not enter test commands or upload reports manually. Native tests clear Calculator and operate their own disposable Notepad document; avoid touching the desktop while they run.

For another app task, the helper shows the task and selected window, then lets you select permitted controls. Open disposable data and grant only the intended controls. That grant lasts for that app/version/window/process until STOP/disconnect. It is permission, not teaching. New controls and other windows are excluded. A save/delete/send button can still affect data if you grant it. Missing permission is reported as a blocked task, never a passed workflow.

The connection expires after two hours. **STOP / disconnect**, Escape, Ctrl+Alt+F12, or closing the helper cancels further actions and terminates its relay. In-flight provider requests may take up to 90 seconds to return. Start a fresh helper process for a new session. This does not install a background service or configure Windows SSH/RDP.

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

The cloud environment must allow HTTPS to the generated `*.trycloudflare.com` host. A saved environment draft is not proof that this access is active. If a proxy returns a connection-denied error, apply/publish the saved network settings and retry the same pairing link while the helper remains open. Keep existing package-manager and API domain settings.

## Validation

Regression tests exercise real Ed25519/X25519/AES-GCM operations and a real loopback HTTP server: forgery, body/route changes, replay/expiry, wrong server identity, encrypted results, queue bounds, cancellation, local scope validation and the automation thread. Native/model app execution is simulated in these cloud tests. WinGet installation, Cloudflare relay startup and the live desktop connection remain unvalidated until this companion runs on Windows and the controller receives the link. No live connection or 80% goal completion is claimed by publishing it.
