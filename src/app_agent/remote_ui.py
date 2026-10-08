"""Locally started Windows connection; no service or inbound firewall rule."""
import json
import os
from pathlib import Path
import queue
import subprocess
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


def tunnel_executable():
    found = find_tunnel_executable()
    if found:
        return found
    raise RuntimeError("Cloudflared is missing. Run windows\\Connect.cmd so WinGet can install the verified package.")


def launch_connection(data_dir, controller_key):
    if sys.platform != "win32":
        raise RuntimeError("The connection helper must be started on the Windows desktop.")
    public = json.loads(Path(controller_key).read_text(encoding="utf-8"))
    controller_fingerprint = fingerprint(public)
    executable = tunnel_executable()
    root = tk.Tk()
    root.title("App Agent connection — 0.6.2")
    root.geometry("900x650")
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
    ttk.Label(frame, text="OpenAI API key — optional; stays on this Windows computer for this session").pack(anchor="w", pady=(10, 0))
    key = tk.StringVar()
    key_entry = ttk.Entry(frame, textvariable=key, show="*")
    key_entry.pack(fill="x")
    status = tk.StringVar(value="Disconnected. Start creates a temporary outbound Cloudflare relay for up to two hours.")
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
             "disconnecting": False, "local_ok": False, "registered_once": False}
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
        for pending in pending_permissions:
            pending["event"].set()
        if state["session"]:
            state["session"].stop()
        if state["tunnel"] and state["tunnel"].poll() is None:
            state["tunnel"].terminate()
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
            if key.get().strip():
                os.environ["AGENT_API_KEY"] = validate_api_key(key.get().strip())
            if allow_cloud.get() and not (os.getenv("AGENT_API_KEY") or os.getenv("OPENAI_API_KEY")):
                raise RuntimeError("Enter the API key locally or turn off AI jobs. Never paste the key in chat.")
            if allow_tasks.get() and not allow_cloud.get():
                raise RuntimeError("App tasks need the AI jobs option enabled.")
            if not messagebox.askokcancel("Start Windows connection", "Authorize this pinned cloud controller to inspect installed apps/window text and run the enabled tests/research for up to two hours? Results are encrypted to that controller. The temporary relay uses Cloudflare. You can STOP at any time."):
                return
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
            session = BridgeSession(public, worker.submit, data_dir, allow_cloud.get(), allow_tests.get(),
                                    execute=lambda job, directory, cancel, emit: execute_job(job, directory, cancel, emit, task_permission),
                                    emit=lambda text: events.put(("log", text)), allow_tasks=allow_tasks.get())
            state["session"] = session
            server = make_server(session)
            state["server"] = server
            threading.Thread(target=server.serve_forever, daemon=True).start()
            state["local_ok"] = check_local_helper(server.server_port)
            if not state["local_ok"]:
                raise RuntimeError("The local helper did not pass its HTTP check. Copy connection diagnostics.")
            append(f"Local helper HTTP check passed: http://127.0.0.1:{server.server_port}/info")
            tunnel = subprocess.Popen([executable, "tunnel", "--url", f"http://127.0.0.1:{server.server_port}",
                                       "--no-autoupdate", "--protocol", "http2"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            state["tunnel"] = tunnel
            started = time.monotonic()
            def read_tunnel():
                for line in tunnel.stdout:
                    events.put(("relay_line", line[:2000]))
                events.put(("tunnel_closed", None))
            threading.Thread(target=read_tunnel, daemon=True).start()
            state["started"] = started
            start_button.configure(state="disabled")
            key.set("")
            key_entry.configure(state="disabled")
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
        report = diagnostics.report("0.6.2", controller_fingerprint,
                                    server.server_port if server else None,
                                    state["local_ok"] and not state["disconnecting"],
                                    tunnel is not None and tunnel.poll() is None)
        root.clipboard_clear()
        root.clipboard_append(report)
        append("Connection diagnostics copied. They contain no provider key or private controller identity.")

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
