"""Real crypto/HTTP integration; fake native executor is explicitly separate."""
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from app_agent.automation_worker import AutomationWorker
from app_agent.remote_bridge import BridgeSession, execute_job, make_server, validate_job
from app_agent.remote_client import RemoteClient
from app_agent.remote_protocol import (ControllerKeys, RequestVerifier, canonical, decode, decrypt_result,
                                       encode, encrypt_result, raw_public, sign_request)
from unittest.mock import patch, Mock


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.keys = ControllerKeys()
        self.verifier = RequestVerifier(self.keys.public())

    def test_wrong_controller_and_modified_command_are_rejected(self):
        body = canonical({"operation": "inventory"})
        bad = sign_request(ControllerKeys(), "POST", "/jobs", body)
        with self.assertRaises(InvalidSignature):
            self.verifier.verify("POST", "/jobs", body, bad)
        headers = sign_request(self.keys, "POST", "/jobs", body)
        for method, path, changed in (("GET", "/jobs", body), ("POST", "/stop", body), ("POST", "/jobs", b"changed")):
            with self.assertRaises(InvalidSignature):
                self.verifier.verify(method, path, changed, headers)

    def test_replay_and_expired_requests_are_rejected(self):
        headers = sign_request(self.keys, "GET", "/info", b"")
        self.verifier.verify("GET", "/info", b"", headers)
        with self.assertRaisesRegex(ValueError, "Repeated"):
            self.verifier.verify("GET", "/info", b"", headers)
        headers = sign_request(self.keys, "GET", "/info", b"", timestamp=int(time.time()) - 91)
        with self.assertRaisesRegex(ValueError, "Expired"):
            self.verifier.verify("GET", "/info", b"", headers)

    def test_signed_encryption_is_bound_to_controller_server_and_request(self):
        server = Ed25519PrivateKey.generate()
        nonce = "f" * 32
        result = {"text": "Private visible document text"}
        envelope = encrypt_result(self.verifier.encryption, server, result, nonce)
        self.assertNotIn(result["text"], json.dumps(envelope))
        self.assertEqual(decrypt_result(self.keys, server.public_key(), envelope, nonce), result)
        with self.assertRaises(ValueError):
            decrypt_result(self.keys, server.public_key(), envelope, "a" * 32)
        with self.assertRaises(InvalidSignature):
            decrypt_result(self.keys, Ed25519PrivateKey.generate().public_key(), envelope, nonce)
        changed = {**envelope, "ciphertext": envelope["ciphertext"][:-1] + ("A" if envelope["ciphertext"][-1] != "A" else "B")}
        with self.assertRaises(InvalidSignature):
            decrypt_result(self.keys, server.public_key(), changed, nonce)

    def test_private_identity_is_preserved_and_never_in_public_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "controller.json"
            self.keys.save(path)
            self.assertEqual(ControllerKeys.load(path).public(), self.keys.public())
            with self.assertRaises(FileExistsError):
                ControllerKeys().save(path)
            self.assertNotIn("private", json.dumps(self.keys.public()))

    def test_strict_key_encoding_rejects_malformed_or_wrong_length_values(self):
        for value in ("", "a b", "++++", "AAA", None):
            with self.assertRaises(ValueError):
                decode(value, 32)


class JobPolicyTests(unittest.TestCase):
    def task(self):
        return {"operation": "task", "parameters": {"app_id": "test-app", "generation": 1, "window_handle": 41,
                                                     "process_id": 81, "task": "Type exactly: Hello", "expected_result": "Hello"}}

    def test_generic_tasks_need_cloud_and_task_permission_and_valid_identity(self):
        for cloud, tasks in ((False, True), (True, False), (False, False)):
            with self.assertRaisesRegex(ValueError, "permission"):
                validate_job(self.task(), cloud, True, allow_tasks=tasks)
        self.assertEqual(validate_job(self.task(), True, True, allow_tasks=True)["operation"], "task")
        for field, changed in (("generation", True), ("expected_result", ""), ("window_handle", 0), ("task", "a" * 2001)):
            job = self.task()
            job["parameters"][field] = changed
            with self.assertRaises(ValueError):
                validate_job(job, True, True, allow_tasks=True)

    def test_changed_process_or_app_version_is_rejected_before_permission_and_execution(self):
        from app_agent.catalog import Catalog
        from test_catalog import app, snapshot
        job = self.task()
        permission = Mock()
        with tempfile.TemporaryDirectory() as directory:
            catalog = Catalog(directory)
            catalog.sync(snapshot([app(identity="test-app")]))
            catalog.close()
            with patch("app_agent.desktop.WindowsDesktop") as desktop:
                desktop.return_value.observe.return_value = {"process_id": 82}
                with self.assertRaisesRegex(RuntimeError, "changed process"):
                    execute_job(job, directory, threading.Event(), lambda text: None, permission)
                permission.assert_not_called()
                job["parameters"]["generation"] = 2
                with self.assertRaisesRegex(RuntimeError, "version changed"):
                    execute_job(job, directory, threading.Event(), lambda text: None, permission)
                desktop.assert_called_once()

    def test_locally_granted_task_executes_with_independent_expected_text(self):
        from app_agent.app_practice import create_grant
        from app_agent.catalog import Catalog
        from test_catalog import app, snapshot
        from test_runner import FakeCloud
        class Editor:
            value = ""
            def observe(self):
                return {"window": "Editor", "window_handle": 41, "process_id": 81, "controls": [
                    {"id": 1, "name": "Editor", "automation_id": "edit", "type": "Edit", "password": False,
                     "enabled": True, "visible": True, "actions": ["type"], "value": self.value}]}
            def act(self, action):
                self.value = action["text"]
        editor = Editor()
        cloud = FakeCloud([{"kind": "type", "target": 1, "automation_id": "edit", "target_name": "Editor", "text": "Hello", "reason": "Write"},
                           {"kind": "finish", "expected_text": "Hello", "reason": "Verified"}])
        with tempfile.TemporaryDirectory() as directory:
            catalog = Catalog(directory)
            catalog.sync(snapshot([app(identity="test-app")]))
            catalog.save_blueprint("test-app", 1, {"capabilities": [{"name": "Write"}]})
            catalog.close()
            with patch("app_agent.desktop.WindowsDesktop", return_value=editor), patch("app_agent.research.CloudResearcher", return_value=cloud):
                result = execute_job(self.task(), directory, threading.Event(), lambda text: None,
                                     lambda app, observation, task, cancel: create_grant(app, observation, [1]))
            self.assertEqual(result["outcome"], "result_observed")
            self.assertEqual(result["actions_executed"], 1)
            self.assertEqual(editor.value, "Hello")
            catalog = Catalog(directory)
            try:
                self.assertEqual(len(catalog.workflows("test-app", 1)), 1)
            finally:
                catalog.close()
    def test_remote_shell_scripts_paths_and_unapproved_jobs_are_rejected(self):
        invalid = [
            {"operation": "shell", "parameters": {"command": "anything"}},
            {"operation": "inventory", "parameters": {"script": "anything"}},
            {"operation": "inventory", "path": "anywhere"},
            {"operation": "self_test", "parameters": {"with_cloud": True}},
            {"operation": "study"},
            {"operation": "inspect_window", "parameters": {"window_handle": True, "process_id": 1}}]
        for job in invalid:
            with self.subTest(job=job), self.assertRaises(ValueError):
                validate_job(job, allow_cloud=False, allow_tests=True)
        with self.assertRaises(ValueError):
            validate_job({"operation": "self_test"}, allow_cloud=True, allow_tests=False)

    def test_study_limits_and_parameter_types_are_enforced(self):
        for parameter in ({"daily_limit": 51}, {"max_apps": 6}, {"max_plans": 4}, {"daily_limit": True}, {"max_apps": 0}):
            with self.assertRaises(ValueError):
                validate_job({"operation": "study", "parameters": parameter}, True, True)
        self.assertEqual(validate_job({"operation": "study", "parameters": {"daily_limit": 50, "max_apps": 5, "max_plans": 3}}, True, True)["operation"], "study")

    def test_stop_and_expiration_prevent_queued_execution(self):
        for expired in (False, True):
            queue, calls = [], []
            session = BridgeSession(ControllerKeys().public(), queue.append, "unused", execute=lambda *args: calls.append(args))
            result = session.enqueue({"operation": "inventory"})
            if expired:
                session.expires = time.monotonic() - 1
            else:
                session.stop()
            queue.pop()()
            self.assertEqual(session.get(result["id"])["status"], "cancelled")
            self.assertEqual(calls, [])
            with self.assertRaises(ValueError):
                session.enqueue({"operation": "inventory"})

    def test_queue_has_a_bound_and_failed_execution_is_not_a_pass(self):
        pending = []
        def fail(*args):
            raise RuntimeError("Native execution failed")
        session = BridgeSession(ControllerKeys().public(), pending.append, "unused", execute=fail)
        ids = [session.enqueue({"operation": "inventory"})["id"] for _ in range(4)]
        with self.assertRaisesRegex(ValueError, "queue is full"):
            session.enqueue({"operation": "inventory"})
        pending.pop(0)()
        result = session.get(ids[0])
        self.assertEqual(result["status"], "failed")
        self.assertIn("Native execution failed", result["error"])


class ConnectionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.keys = ControllerKeys()
        self.calls = []
        self.execution_threads = []
        def execute(job, directory, cancel, emit):
            self.calls.append(job)
            self.execution_threads.append(threading.get_ident())
            return {"apps": ["A simulated app"], "native_simulation": True}
        self.worker = AutomationWorker(lambda function: function(), lambda error: None, initialize=lambda: lambda: None)
        self.session = BridgeSession(self.keys.public(), self.worker.submit, "unused", execute=execute)
        self.server = make_server(self.session)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.client = RemoteClient(self.base + "#key=" + self.session.public_key, self.keys, test_loopback=True)

    def tearDown(self):
        self.session.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.worker.close()
        self.worker.thread.join(2)

    def test_real_authenticated_http_runs_jobs_on_the_automation_worker(self):
        self.assertTrue(self.client.request("GET", "/info")["active"])
        result = self.client.submit("inventory")
        deadline = time.monotonic() + 2
        while result["status"] in ("queued", "running") and time.monotonic() < deadline:
            result = self.client.job(result["id"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["result"]["apps"], ["A simulated app"])
        self.assertEqual(self.execution_threads, [self.worker.thread.ident])
        self.assertTrue(self.client.request("POST", "/stop")["stopped"])
        with self.assertRaisesRegex(RuntimeError, "stopped"):
            self.client.submit("inventory")

    def test_local_startup_probe_reaches_bridge_without_executing_jobs(self):
        from app_agent.relay_diagnostics import check_local_helper
        self.assertTrue(check_local_helper(self.server.server_port))
        self.assertEqual(self.calls, [])

    def test_external_http_failures_do_not_claim_a_helper_authentication_failure(self):
        from io import BytesIO
        for status, payload, explanation in ((403, b'Your request was blocked.', 'without the expected helper response'),
                                             (404, b'Not found', 'Relay returned HTTP 404')):
            error = HTTPError(self.base + '/info', status, 'Rejected', {}, BytesIO(payload))
            with self.subTest(status=status), patch('app_agent.remote_client.build_opener') as opener:
                opener.return_value.open.side_effect = error
                with self.assertRaisesRegex(RuntimeError, explanation):
                    self.client.request('GET', '/info')
        self.assertEqual(self.calls, [])

    def test_unauthenticated_or_wrong_controller_requests_never_execute(self):
        request = Request(self.base + "/jobs", data=canonical({"operation": "inventory"}), headers={"Content-Type": "application/json"})
        with self.assertRaises(HTTPError) as failure:
            build_opener(ProxyHandler({})).open(request, timeout=2)
        self.assertEqual(failure.exception.code, 403)
        other = RemoteClient(self.base + "#key=" + self.session.public_key, ControllerKeys(), test_loopback=True)
        with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
            other.submit("inventory")
        self.assertEqual(self.calls, [])

    def test_wrong_server_key_rejects_an_otherwise_valid_encrypted_reply(self):
        wrong_key = encode(raw_public(Ed25519PrivateKey.generate().public_key()))
        client = RemoteClient(self.base + "#key=" + wrong_key, self.keys, test_loopback=True)
        with self.assertRaises(InvalidSignature):
            client.request("GET", "/info")

    def test_oversized_request_is_rejected_before_reading_or_executing_it(self):
        request = Request(self.base + "/jobs", data=b"", headers={"Content-Length": "32769"})
        with self.assertRaises(HTTPError) as failure:
            build_opener(ProxyHandler({})).open(request, timeout=2)
        self.assertEqual(failure.exception.code, 403)
        self.assertEqual(self.calls, [])

    def test_desktop_connection_helper_rejects_non_windows_launch(self):
        from app_agent.remote_ui import launch_connection
        with patch("app_agent.remote_ui.sys", Mock(platform="linux")):
            with self.assertRaisesRegex(RuntimeError, "Windows desktop"):
                launch_connection("unused", "unused")

    def test_pairing_link_validates_hostname_transport_and_public_key(self):
        for link in ("http://example.trycloudflare.com#key=" + self.session.public_key,
                     "https://example.com#key=" + self.session.public_key,
                     "https://example.trycloudflare.com/another#key=" + self.session.public_key,
                     "https://user:secret@example.trycloudflare.com#key=" + self.session.public_key,
                     "https://example.trycloudflare.com", "https://example.trycloudflare.com#key=AAA"):
            with self.subTest(link=link), self.assertRaises(ValueError):
                RemoteClient(link, self.keys)
