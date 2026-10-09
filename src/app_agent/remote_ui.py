"""Locally started Windows connection; no service or inbound firewall rule."""
import json
import os
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

from .automation_worker import AutomationWorker
from .remote_bridge import BridgeSession, execute_job, make_server
from .remote_protocol import fingerprint
from .research import validate_api_key
from .connection_launcher import find_tunnel_executable
from .relay_diagnostics import RelayDiagnostics, check_local_helper
from .relay_launcher import start_relay, stop_relay
from .connection_settings import public_hostname, tunnel_token, NAMED_TUNNEL_PORT


def tunnel_executable():
    found = find_tunnel_executable()
    if found:
        return found
    raise RuntimeError("Cloudflared is missing. Run windows\\Connect.cmd so WinGet can install the verified package.")


def launch_connection(data_dir, controller_key, named_hostname=None):
    if sys.platform != "win32":
        raise RuntimeError("The connection helper must be started on the Windows desktop.")
    public = json.loads(Path(controller_key).read_text(encoding="utf-8"))
    controller_fingerprint = fingerprint(public)
    executable = tunnel_executable()
    root = tk.Tk()
    root.title("App Agent connection — 0.14.0")
    root.geometry("920x820")
    frame = ttk.Frame(root, padding=16)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Connect this Windows session to your cloud controller", font=("Segoe UI", 14)).pack(anchor="w")
    ttk.Label(frame, text="Controller fingerprint: " + controller_fingerprint).pack(anchor="w", pady=8)
    ttk.Label(frame, text="This allows inventory/window inspection and optional tests, research and scoped app tasks.\nTests use disposable Notepad data and clear Calculator. Leave the desktop untouched during tests.\nOther app tasks need a local grant for specific controls. No remote shell is provided.", wraplength=860).pack(anchor="w")
    allow_tests = tk.BooleanVar(value=True)
    allow_cloud = tk.BooleanVar(value=False)
    allow_tasks = tk.BooleanVar(value=False)
    ttk.Checkbutton(frame, text="Allow automatic Windows self-tests", variable=allow_tests).pack(anchor="w", pady=6)
    ttk.Checkbutton(frame, text="Allow AI self-tests and documentation research (provider usage charges)", variable=allow_cloud).pack(anchor="w")
    ttk.Checkbutton(frame, text="Enable cloud app tasks — I will grant controls in disposable windows locally", variable=allow_tasks).pack(anchor="w")
    automatic = tk.BooleanVar(value=True)
    ttk.Checkbutton(frame, text="Automatic maintenance: signed worker updates, idle tests and parallel app study", variable=automatic).pack(anchor="w")
    from .catalog import Catalog
    configuration = Catalog(data_dir)
    try:
        unlimited = tk.BooleanVar(value=configuration.setting('daily_limit', 0) == 0)
    finally:
        configuration.close()
    ttk.Checkbutton(frame, text="No daily AI study/design cap — provider charges, quotas and rate limits still apply", variable=unlimited).pack(anchor="w")
    ttk.Label(frame, text="Automatic mode keeps this connection for up to 8 hours. Tests start after 60 seconds without input; avoid using the desktop during a test. AI tests/research incur provider charges.", wraplength=860).pack(anchor="w")
    ttk.Label(frame, text="OpenAI API key — optional; stays on this Windows computer for this session").pack(anchor="w", pady=(10, 0))
    key = tk.StringVar()
    key_entry = ttk.Entry(frame, textvariable=key, show="*")
    key_entry.pack(fill="x")
    named_mode = tk.BooleanVar(value=bool(named_hostname))
    hostname = tk.StringVar(value=named_hostname or "")
    relay_key = tk.StringVar()
    named_checkbox = ttk.Checkbutton(frame, text="Use my Cloudflare domain (named tunnel)", variable=named_mode)
    named_checkbox.pack(anchor="w", pady=(10, 0))
    ttk.Label(frame, text=f"Hostname only; configure its Cloudflare service as HTTP 127.0.0.1:{NAMED_TUNNEL_PORT}").pack(anchor="w")
    hostname_entry = ttk.Entry(frame, textvariable=hostname)
    hostname_entry.pack(fill="x")
    ttk.Label(frame, text="Cloudflare tunnel token or installation command — stays on this computer; never send it in chat").pack(anchor="w")
    relay_key_entry = ttk.Entry(frame, textvariable=relay_key, show="*")
    relay_key_entry.pack(fill="x")
    def toggle_named():
        mode = "normal" if named_mode.get() else "disabled"
        hostname_entry.configure(state=mode)
        relay_key_entry.configure(state=mode)
    named_checkbox.configure(command=toggle_named)
    toggle_named()
    status = tk.StringVar(value="Disconnected. Automatic mode keeps the connection for up to eight hours; manual mode for two hours.")
    ttk.Label(frame, textvariable=status, wraplength=860).pack(anchor="w", pady=10)
    link = tk.StringVar()
    entry = ttk.Entry(frame, textvariable=link, state="readonly")
    entry.pack(fill="x")
    ttk.Label(frame, text="Share the full pairing link with this chat. It contains public keys, not your API key.\nClosing this helper or clicking STOP disconnects it.").pack(anchor="w", pady=5)
    buttons = ttk.Frame(frame)
    buttons.pack(fill="x")
    output = tk.Text(frame, height=8, state="disabled")
    output.pack(fill="both", expand=True, pady=8)
    events = queue.Queue()
    state = {"session": None, "server": None, "tunnel": None, "worker": None, "closed": False,
             "disconnecting": False, "local_ok": False, "registered_once": False, "relay_directory": None,
             "named_hostname": None}
    diagnostics = RelayDiagnostics()
    original_key = os.environ.get("AGENT_API_KEY")
    grants = {}
    pending_permissions = []

    def append(text):
        output.configure(state="normal")
        output.insert("end", str(text) + "\n")
        output.see("end")
        output.configure(state="disabled")

    def stop():
        if state["disconnecting"]:
            return
        state["disconnecting"] = True
        diagnostics.connections.clear()
        grants.clear()
        if state.get('maintenance'):
            state['maintenance'].close()
        for pending in pending_permissions:
            pending["event"].set()
        if state["session"]:
            state["session"].stop()
        if state["tunnel"] or state["relay_directory"]:
            threading.Thread(target=stop_relay, args=(state["tunnel"], state["relay_directory"]), daemon=False).start()
        if state["server"]:
            def close_server():
                state["server"].shutdown()
                state["server"].server_close()
            threading.Thread(target=close_server, daemon=True).start()
        if state["worker"]:
            state["worker"].close()
        status.set("Disconnected. In-flight provider requests may take up to 90 seconds to finish; further actions are cancelled.")
        link.set("")
        start_button.configure(state="disabled")

    def close():
        stop()
        state["closed"] = True
        hotkey_stop.set()
        if original_key is None:
            os.environ.pop("AGENT_API_KEY", None)
        else:
            os.environ["AGENT_API_KEY"] = original_key
        root.destroy()

    def start():
        if state["session"]:
            return
        try:
            selected_hostname = public_hostname(hostname.get()) if named_mode.get() else None
            selected_token = tunnel_token(relay_key.get()) if selected_hostname else None
            if key.get().strip():
                os.environ["AGENT_API_KEY"] = validate_api_key(key.get().strip())
            if allow_cloud.get() and not (os.getenv("AGENT_API_KEY") or os.getenv("OPENAI_API_KEY")):
                raise RuntimeError("Enter the API key locally or turn off AI jobs. Never paste the key in chat.")
            if allow_tasks.get() and not allow_cloud.get():
                raise RuntimeError("App tasks need the AI jobs option enabled.")
            duration = 8 * 3600 if automatic.get() else 2 * 3600
            usage = 'no daily app-imposed study/design cap' if unlimited.get() else 'five study/design attempts per day'
            if not messagebox.askokcancel("Start Windows connection", f"Authorize this pinned cloud controller and the enabled local automatic cycle for up to {duration // 3600} hours? Automatic mode checks signed updates, tests when idle, and studies apps in parallel with {usage}. AI usage is billed by your provider. Existing app-control grants are required. You can STOP at any time."):
                return
            configuration = Catalog(data_dir)
            try:
                configuration.set_setting('daily_limit', 0 if unlimited.get() else 5)
            finally:
                configuration.close()
            def failed(error):
                if state["session"]:
                    state["session"].stop()
                events.put(("error", "Windows automation worker failed: " + str(error)))
            worker = AutomationWorker(lambda fn: fn(), failed)
            state["worker"] = worker
            def task_permission(app, observation, task, cancel):
                identity = (app["id"], app["generation"], observation["window_handle"], observation["process_id"])
                if identity in grants:
                    return grants[identity]
                pending = {"event": threading.Event(), "grant": None, "app": app, "observation": observation, "task": task, "identity": identity}
                events.put(("permission", pending))
                deadline = time.monotonic() + 120
                while not pending["event"].wait(0.1):
                    if cancel.is_set() or time.monotonic() > deadline:
                        pending["event"].set()
                        return None
                return pending["grant"]
            from .worker_update import WorkerUpdates
            from .maintenance import Maintenance
            updates = WorkerUpdates(data_dir, public, enabled=automatic.get())
            maintenance = Maintenance(data_dir, enabled=automatic.get(), emit=lambda text: events.put(("log", text)),monitor_installations=True)
            state['updates'], state['maintenance'] = updates, maintenance
            state['next_maintenance'] = 0
            session = BridgeSession(public, worker.submit, data_dir, allow_cloud.get(), allow_tests.get(), duration=duration,
                                    execute=lambda job, directory, cancel, emit: updates.execute(job, directory, cancel, emit, task_permission),
                                    emit=lambda text: events.put(("log", text)), allow_tasks=allow_tasks.get())
            state["session"] = session
            session.worker_version = lambda: updates.version
            state["named_hostname"] = selected_hostname
            try:
                server = make_server(session, NAMED_TUNNEL_PORT if selected_hostname else 0)
            except OSError as error:
                if selected_hostname:
                    raise RuntimeError(f"Cannot bind the named-tunnel helper to 127.0.0.1:{NAMED_TUNNEL_PORT}. Close any older helper; configure that exact port in Cloudflare. No other program was stopped.") from error
                raise
            state["server"] = server
            threading.Thread(target=server.serve_forever, daemon=True).start()
            state["local_ok"] = check_local_helper(server.server_port)
            if not state["local_ok"]:
                raise RuntimeError("The local helper did not pass its HTTP check. Copy connection diagnostics.")
            append(f"Local helper HTTP check passed: http://127.0.0.1:{server.server_port}/info")
            tunnel, relay_directory = start_relay(executable, server.server_port, named_token=selected_token)
            state["tunnel"] = tunnel
            state["relay_directory"] = relay_directory
            append("Relay uses an isolated temporary configuration; existing local tunnel configuration is not reused.")
            if selected_hostname:
                diagnostics.url = "https://" + selected_hostname
                append(f"Named tunnel selected: {selected_hostname}; Cloudflare service must be HTTP 127.0.0.1:{server.server_port}.")
            started = time.monotonic()
            def read_tunnel():
                for line in tunnel.stdout:
                    if selected_token:
                        line = line.replace(selected_token, "[redacted]")
                    events.put(("relay_line", line[:2000]))
                events.put(("tunnel_closed", None))
            threading.Thread(target=read_tunnel, daemon=True).start()
            state["started"] = started
            start_button.configure(state="disabled")
            key.set("")
            key_entry.configure(state="disabled")
            relay_key.set("")
            relay_key_entry.configure(state="disabled")
            hostname_entry.configure(state="disabled")
            named_checkbox.configure(state="disabled")
            status.set("Connecting outbound relay…")
        except Exception as error:
            append(error)
            if state["session"]:
                stop()

    def copy_link():
        if link.get():
            root.clipboard_clear()
            root.clipboard_append(link.get())

    def copy_diagnostics():
        server, tunnel = state["server"], state["tunnel"]
        report = diagnostics.report("0.14.0", controller_fingerprint,
                                    server.server_port if server else None,
                                    state["local_ok"] and not state["disconnecting"],
                                    tunnel is not None and tunnel.poll() is None)
        if link.get():
            report += "\nPublic pairing link: " + link.get()
        root.clipboard_clear()
        root.clipboard_append(report)
        append(report)
        append("The full report above is also copied to the clipboard.")

    start_button = ttk.Button(buttons, text="Start connection", command=start)
    start_button.pack(side="left")
    ttk.Button(buttons, text="Copy pairing link", command=copy_link).pack(side="left", padx=8)
    ttk.Button(buttons, text="Copy connection diagnostics", command=copy_diagnostics).pack(side="left", padx=8)
    ttk.Button(buttons, text="STOP / disconnect", command=stop).pack(side="left")
    from .hotkey import register_stop
    hotkey_stop = register_stop(lambda: (state["session"].stop() if state["session"] else None, events.put(("disconnect", None))),
                               lambda text: events.put(("log", text)))
    root.protocol("WM_DELETE_WINDOW", close)
    root.bind("<Escape>", lambda event: stop())

    def permission_dialog(pending):
        if pending["event"].is_set() or not state["session"].active():
            pending["event"].set()
            return
        from .app_practice import create_grant
        pending_permissions.append(pending)
        observation = pending["observation"]
        dialog = tk.Toplevel(root)
        dialog.title("Allow cloud tasks in disposable app controls")
        dialog.geometry("850x500")
        ttk.Label(dialog, text=f"App: {pending['app']['name']}\nWindow: {observation['window']}\nRequested task: {pending['task']}\nSelect ONLY controls permitted in this disposable window. The grant lasts until STOP/disconnect. New controls and other windows are excluded.", wraplength=810).pack(anchor="w", padx=12, pady=10)
        controls = [item for item in observation["controls"] if item["id"] and item.get("actions")
                    and item["enabled"] and item["visible"] and not item.get("password")]
        listing = tk.Listbox(dialog, selectmode="extended", exportselection=False)
        listing.pack(fill="both", expand=True, padx=12)
        for item in controls:
            listing.insert("end", f"{item['type']}: {item['name']} [{', '.join(item['actions'])}]")
        def finish(allowed):
            if not pending["event"].is_set() and allowed and state["session"].active():
                try:
                    grant = create_grant(pending["app"], observation, [controls[index]["id"] for index in listing.curselection()])
                except ValueError as error:
                    messagebox.showerror("Permission scope", str(error), parent=dialog)
                    return
                pending["grant"] = grant
                grants[pending["identity"]] = grant
            pending["event"].set()
            pending_permissions.remove(pending)
            dialog.destroy()
        ttk.Button(dialog, text="Allow selected controls", command=lambda: finish(True)).pack(anchor="w", padx=12, pady=8)
        ttk.Button(dialog, text="Reject", command=lambda: finish(False)).pack(anchor="w", padx=12)
        dialog.protocol("WM_DELETE_WINDOW", lambda: finish(False))

    def pump():
        while True:
            try:
                kind, value = events.get_nowait()
            except queue.Empty:
                break
            if kind == "relay_line":
                diagnostics.observe(value)
                if state["named_hostname"]:
                    diagnostics.url = "https://" + state["named_hostname"]
                if state["session"].active() and not state["disconnecting"]:
                    if diagnostics.ready:
                        state["registered_once"] = True
                        link.set(diagnostics.url + "#key=" + state["session"].public_key)
                        status.set("Relay connection registered. Copy the pairing link; the cloud controller must still verify it.")
                    else:
                        link.set("")
                        status.set("Waiting for relay registration. An assigned address alone does not confirm a connection.")
                    if "ERR" in value or "WRN" in value:
                        append("Relay: " + diagnostics.lines[-1])
            elif kind == "permission":
                permission_dialog(value)
            elif kind in ("disconnect", "tunnel_closed", "error"):
                if value:
                    append(value)
                stop()
            else:
                append(value)
        if state['session'] and state['session'].active() and state.get('maintenance') and not state.get('maintenance_queued') and time.monotonic() >= state.get('next_maintenance', 0):
            state['next_maintenance'] = time.monotonic() + 10
            state['maintenance_queued'] = True
            def maintain():
                try:
                    if not state['session'].active():
                        return
                    updates = state['updates']
                    with updates.lock:
                        updates.check(lambda text: events.put(('log', text)))
                    from .maintenance import idle_seconds
                    state['maintenance'].tick(state['session'], updates.version, idle_seconds())
                finally:
                    state['maintenance_queued'] = False
            state['worker'].submit(maintain)
        if state["session"] and (not state["session"].active() or
                (not state["registered_once"] and time.monotonic() - state.get("started", time.monotonic()) > 90)):
            if state["tunnel"] and state["tunnel"].poll() is None:
                if state["session"].active():
                    append("Relay did not register within 90 seconds. Copy connection diagnostics before closing this window.")
                stop()
        if not state["closed"]:
            root.after(200, pump)
    pump()
    root.mainloop()
