"""A short-lived Windows companion with fixed authenticated job operations."""
import copy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
import json
from pathlib import Path
import re
import socket
import sys
import threading
import time
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from .remote_protocol import RequestVerifier, encrypt_result, canonical, encode, raw_public
from .relay_diagnostics import BRIDGE_REJECTION

OPERATIONS = {"inventory", "learning_report", "windows", "inspect_window", "self_test", "study", "task"}


def validate_job(value, allow_cloud, allow_tests, allow_tasks=False):
    if not isinstance(value, dict) or set(value) - {"operation", "parameters"}:
        raise ValueError("Expected an operation and parameters.")
    operation, parameters = value.get("operation"), value.get("parameters", {})
    if operation not in OPERATIONS or not isinstance(parameters, dict):
        raise ValueError("Unsupported remote operation.")
    if operation == "inspect_window":
        if set(parameters) != {"window_handle", "process_id"} or any(type(parameters[field]) is not int or parameters[field] <= 0 for field in parameters):
            raise ValueError("Inspection requires the exact window handle and process ID.")
    elif operation == "task":
        if not allow_cloud or not allow_tasks:
            raise ValueError("Selected-window task permission was not enabled on Windows.")
        required = {"app_id", "generation", "window_handle", "process_id", "task", "expected_result"}
        if not required <= set(parameters) or set(parameters) - required - {"result_control_id"}:
            raise ValueError("A task requires the exact app version, window/process and expected result.")
        if "result_control_id" in parameters and (not isinstance(parameters["result_control_id"], str) or not parameters["result_control_id"].strip() or len(parameters["result_control_id"]) > 500):
            raise ValueError("Invalid result control identity.")
        for field in ("generation", "window_handle", "process_id"):
            if type(parameters[field]) is not int or parameters[field] <= 0:
                raise ValueError("Invalid task identity.")
        for field in ("app_id", "task", "expected_result"):
            if not isinstance(parameters[field], str) or not parameters[field].strip() or len(parameters[field]) > 2000:
                raise ValueError("Invalid task or expected result.")
    elif operation == "self_test":
        if not allow_tests:
            raise ValueError("Native test permission was not granted on Windows.")
        if set(parameters) - {"with_cloud", "with_voice"} or any(type(parameters.get(field, False)) is not bool for field in ("with_cloud", "with_voice")):
            raise ValueError("Invalid self-test parameters.")
        if parameters.get("with_voice") and not parameters.get("with_cloud"):
            raise ValueError("Speech testing requires cloud testing to be enabled.")
        if parameters.get("with_cloud") and not allow_cloud:
            raise ValueError("Cloud test permission was not granted on Windows.")
    elif operation == "study":
        if not allow_cloud:
            raise ValueError("Cloud research permission was not granted on Windows.")
        limits = {"daily_limit": (0, 10000), "max_apps": (1, 5), "max_plans": (0, 3)}
        if set(parameters) - set(limits):
            raise ValueError("Invalid study parameters.")
        for field, value in parameters.items():
            if type(value) is not int or not limits[field][0] <= value <= limits[field][1]:
                raise ValueError("Study parameter exceeds its limit.")
    elif parameters:
        raise ValueError("This operation accepts no parameters.")
    return {"operation": operation, "parameters": parameters}


def execute_job(job, data_dir, cancel, emit, task_permission=None):
    # All desktop calls are invoked by the owning AutomationWorker, never by
    # HTTP threads. There is no remote shell, arbitrary script or file path.
    from .catalog import Catalog
    from .discovery import scan_apps
    from .desktop import WindowsDesktop, window_process_id
    operation, parameters = job["operation"], job["parameters"]
    if cancel.is_set():
        raise RuntimeError("Connection session stopped.")
    if operation == "self_test":
        from .self_test import self_test
        from .research import CloudResearcher
        return self_test(data_dir, CloudResearcher() if parameters.get("with_cloud") else None, emit, cancel,
                         with_voice=parameters.get("with_voice", False))
    if operation == "windows":
        windows = []
        for handle, title in WindowsDesktop.windows():
            if title.startswith(("App Agent —", "App Agent connection")):
                continue
            try:
                windows.append({"window_handle": handle, "title": title, "process_id": window_process_id(handle)})
            except RuntimeError:
                continue
        return {"windows": windows}
    if operation == "inspect_window":
        snapshot = WindowsDesktop(parameters["window_handle"]).observe()
        if snapshot["process_id"] != parameters["process_id"]:
            raise RuntimeError("The selected window changed process; observation discarded.")
        return snapshot
    catalog = Catalog(data_dir)
    try:
        if operation == "inventory":
            changes = catalog.sync(scan_apps())
            return {"changes": changes, "apps": [{key: value for key, value in app.items() if key not in ("blueprint", "location")}
                                                 for app in catalog.apps()]}
        if operation == "learning_report":
            plans = []
            for app in catalog.apps():
                for capability in catalog.coverage(app["id"], app["generation"]):
                    saved = catalog.practice_plan(app["id"], app["generation"], capability["name"])
                    if saved and saved["status"] == "ready" and saved["body"] and len(plans) < 100:
                        plans.append({"app_id": app["id"], "generation": app["generation"], "app": app["name"],
                                      "plan": saved["body"], "status": "ready_unexecuted"})
            return {"overview": catalog.learning_overview(), "campaign": catalog.setting("campaign_state", {}),
                    "ready_experiments": plans,
                    "automatic_progress": json.loads((Path(data_dir) / 'automatic-progress.json').read_text(encoding='utf-8'))
                    if (Path(data_dir) / 'automatic-progress.json').is_file() else None}
        if operation == "study":
            from .campaign import study_campaign
            from .research import CloudResearcher
            effective = dict(parameters)
            local_limit = catalog.setting('daily_limit')
            if local_limit is not None:
                effective['daily_limit'] = local_limit
            effective['research_workers'] = catalog.setting('research_workers', 3)
            return study_campaign(catalog, CloudResearcher(), emit, cancel=cancel, **effective)
        if operation == "task":
            if task_permission is None:
                raise RuntimeError("No local app-control permission handler is available.")
            from .app_practice import grants_action
            from .learning import ensure_blueprint
            from .research import CloudResearcher
            from .runner import TaskRunner
            app = catalog.get(parameters["app_id"])
            if app["generation"] != parameters["generation"]:
                raise RuntimeError("App version changed; request a current inventory before another task.")
            desktop = WindowsDesktop(parameters["window_handle"])
            observation = desktop.observe()
            if observation["process_id"] != parameters["process_id"]:
                raise RuntimeError("Selected window changed process; no task executed.")
            result_control = parameters.get("result_control_id")
            if result_control and not any(control.get("automation_id") == result_control and control.get("visible")
                                          and not control.get("password") and control.get("type") in ("Text", "Edit", "Document")
                                          for control in observation["controls"]):
                raise RuntimeError("Selected result control is unavailable; no task executed.")
            grant = task_permission(app, observation, parameters["task"], cancel)
            if grant is None or cancel.is_set():
                raise RuntimeError("Local app-control permission was denied or cancelled.")
            cloud = CloudResearcher()
            from .task_director import task_blueprint
            blueprint = task_blueprint(catalog, app, cloud, emit, cancel, observation)
            result = TaskRunner(desktop, cloud, lambda action, snapshot: grants_action(grant, action, snapshot),
                                emit, data_dir, cancel).run(parameters["task"], blueprint, max_steps=24,
                                previous_workflows=catalog.workflows(app["id"], app["generation"]),
                                required_result_text=parameters["expected_result"], result_control_id=result_control)
            catalog.save_workflow(app["id"], app["generation"], result)
            return result
        raise ValueError("Unsupported operation.")
    finally:
        catalog.close()


class BridgeSession:
    def __init__(self, controller_public, submit, data_dir, allow_cloud=False, allow_tests=True,
                 duration=7200, execute=execute_job, emit=lambda text: None, allow_tasks=False):
        self.verifier = RequestVerifier(controller_public)
        self.signing = Ed25519PrivateKey.generate()
        self.submit, self.data_dir, self.execute, self.emit = submit, Path(data_dir), execute, emit
        self.allow_cloud, self.allow_tests = allow_cloud, allow_tests
        self.allow_tasks = allow_tasks
        self.expires = time.monotonic() + duration
        self.cancel, self.lock = threading.Event(), threading.Lock()
        self.jobs = {}

    @property
    def public_key(self):
        return encode(raw_public(self.signing.public_key()))

    def active(self):
        return not self.cancel.is_set() and time.monotonic() < self.expires

    def stop(self):
        self.cancel.set()

    def enqueue(self, value):
        if not self.active():
            raise ValueError("Connection session expired or stopped.")
        job = validate_job(value, self.allow_cloud, self.allow_tests, self.allow_tasks)
        with self.lock:
            if sum(item["status"] in ("queued", "running") for item in self.jobs.values()) >= 4:
                raise ValueError("Remote job queue is full.")
            if len(self.jobs) >= 200:
                raise ValueError("Session job limit reached; start a new session.")
            identity = uuid.uuid4().hex
            self.jobs[identity] = {"id": identity, "operation": job["operation"], "status": "queued", "logs": []}
        self.submit(lambda: self._run(identity, job))
        return self.get(identity)

    def _run(self, identity, job):
        with self.lock:
            if not self.active():
                self.jobs[identity]["status"] = "cancelled"
                return
            self.jobs[identity]["status"] = "running"
        def log(text):
            with self.lock:
                self.jobs[identity]["logs"] = (self.jobs[identity]["logs"] + [str(text)[:4000]])[-40:]
            self.emit(str(text))
        try:
            result = self.execute(job, self.data_dir, self.cancel, log)
            with self.lock:
                self.jobs[identity].update(status="cancelled" if self.cancel.is_set() else "completed", result=result)
        except Exception as error:
            # Native/model errors are reported without claiming a passed job.
            with self.lock:
                self.jobs[identity].update(status="cancelled" if self.cancel.is_set() else "failed", error=str(error)[:2000])
        self.emit(f"Remote {job['operation']}: {self.get(identity)['status']}")

    def get(self, identity):
        with self.lock:
            return copy.deepcopy(self.jobs[identity])

    def info(self):
        return {"version": version("app-agent"), "active": self.active(), "allow_cloud": self.allow_cloud,
                "allow_tests": self.allow_tests, "allow_tasks": self.allow_tasks, "operations": sorted(OPERATIONS),
                "seconds_remaining": max(0, int(self.expires - time.monotonic())),
                "time": datetime.now(timezone.utc).isoformat(),
                "worker_version": self.worker_version() if hasattr(self, 'worker_version') else version('app-agent')}


def make_server(session, port=0):
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("Invalid local helper port.")
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            # Never log signatures, request contents, or response bodies.
            pass

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def do_GET(self):
            self.dispatch()

        def do_POST(self):
            self.dispatch()

        def dispatch(self):
            nonce = None
            try:
                if self.headers.get("Transfer-Encoding"):
                    raise ValueError("Chunked requests are unsupported.")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 <= length <= 32768:
                    raise ValueError("Request exceeds the size limit.")
                body = self.rfile.read(length)
                if len(body) != length:
                    raise ValueError("Incomplete request.")
                nonce = session.verifier.verify(self.command, self.path, body, self.headers)
                if self.command == "GET" and self.path == "/info":
                    result = session.info()
                elif self.command == "GET" and re.fullmatch(r"/jobs/[a-f0-9]{32}", self.path):
                    result = session.get(self.path.rsplit("/", 1)[1])
                elif self.command == "POST" and self.path == "/jobs":
                    result = session.enqueue(json.loads(body))
                elif self.command == "POST" and self.path == "/stop" and body in (b"", b"{}"):
                    session.stop()
                    result = {"stopped": True}
                else:
                    raise ValueError("Unsupported route.")
                self.reply(200, encrypt_result(session.verifier.encryption, session.signing, result, nonce))
            except Exception as error:
                if nonce:
                    result = {"error": str(error)[:1000]}
                    self.reply(400, encrypt_result(session.verifier.encryption, session.signing, result, nonce))
                else:
                    self.reply(403, {"error": BRIDGE_REJECTION})

        def reply(self, status, value):
            body = canonical(value)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    class BoundedServer(ThreadingHTTPServer):
        # HTTPServer permits address reuse, which can admit a second listener
        # on Windows. Python versions may also enable port reuse by default.
        # This endpoint must belong to exactly one helper session.
        allow_reuse_address = False
        allow_reuse_port = False

        def __init__(self, *args):
            self.slots = threading.BoundedSemaphore(8)
            super().__init__(*args)

        def server_bind(self):
            if sys.platform == "win32":
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()

        def process_request(self, request, client_address):
            if not self.slots.acquire(blocking=False):
                self.shutdown_request(request)
                return
            try:
                super().process_request(request, client_address)
            except Exception:
                self.slots.release()
                raise

        def process_request_thread(self, request, client_address):
            try:
                super().process_request_thread(request, client_address)
            finally:
                self.slots.release()
    server = BoundedServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server
