"""Cloud controller for a publicly shareable, pinned Windows pairing link."""
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit, urlunsplit, parse_qs
from urllib.request import Request, build_opener, HTTPRedirectHandler

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from .remote_protocol import canonical, decode, decrypt_result, sign_request
from .relay_diagnostics import BRIDGE_REJECTION


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class RemoteClient:
    def __init__(self, pairing_link, keys, test_loopback=False):
        parsed = urlsplit(pairing_link)
        loopback = test_loopback and parsed.scheme == "http" and parsed.hostname == "127.0.0.1"
        if (not loopback and (parsed.scheme != "https" or not re.fullmatch(r"[a-z0-9-]+\.trycloudflare\.com", parsed.hostname or "")
                             or parsed.port not in (None, 443))) or parsed.username or parsed.password or parsed.query or parsed.path not in ("", "/"):
            raise ValueError("Pairing requires the helper's HTTPS trycloudflare.com link.")
        fragment = parse_qs(parsed.fragment, strict_parsing=True)
        if set(fragment) != {"key"} or len(fragment["key"]) != 1:
            raise ValueError("Pairing link must include its Windows session public key.")
        self.signing_public = Ed25519PublicKey.from_public_bytes(decode(fragment["key"][0], 32))
        self.base = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
        self.keys = keys

    def request(self, method, path, value=None):
        if method not in ("GET", "POST") or not re.fullmatch(r"/(?:info|jobs|stop|jobs/[a-f0-9]{32})", path):
            raise ValueError("Unsupported controller request.")
        body = b"" if value is None else canonical(value)
        if method == "GET" and body:
            raise ValueError("GET requests accept no body.")
        headers = sign_request(self.keys, method, path, body)
        request = Request(self.base + path, data=body if method == "POST" else None, method=method,
                          headers={**headers, "Content-Type": "application/json", "User-Agent": "AppAgent-Controller/0.6"})
        try:
            response = build_opener(NoRedirects()).open(request, timeout=20)
        except HTTPError as error:
            response = error
        with response:
            payload = response.read(8_000_001)
            if len(payload) > 8_000_000:
                raise RuntimeError("Remote result exceeds the size limit.")
            if response.status not in (200, 400):
                if response.status == 404:
                    raise RuntimeError("Relay returned HTTP 404 for the helper endpoint. Check that the current Windows helper is running and copy its connection diagnostics.")
                if response.status == 403:
                    try:
                        rejected = json.loads(payload) == {"error": BRIDGE_REJECTION}
                    except (ValueError, UnicodeError):
                        rejected = False
                    if rejected:
                        raise RuntimeError("HTTP 403 with a bridge-style rejection. Verify the pinned controller, current pairing link and clock; this unsigned response does not authenticate the helper.")
                    raise RuntimeError("HTTP 403 without the expected helper response. Inspect relay diagnostics and cloud network policy; no authenticated Windows connection was established.")
                raise RuntimeError(f"Windows connection request rejected (HTTP {response.status}). Check the link and cloud network access.")
            value = decrypt_result(self.keys, self.signing_public, json.loads(payload), headers["X-Agent-Nonce"])
        if "error" in value and "id" not in value:
            raise RuntimeError(value["error"])
        return value

    def submit(self, operation, parameters=None):
        return self.request("POST", "/jobs", {"operation": operation, "parameters": parameters or {}})

    def job(self, identity):
        if not re.fullmatch(r"[a-f0-9]{32}", identity):
            raise ValueError("Invalid job identity.")
        return self.request("GET", "/jobs/" + identity)

    def wait(self, identity, timeout=3600, emit=print):
        deadline, previous = time.monotonic() + timeout, None
        while time.monotonic() < deadline:
            value = self.job(identity)
            if value["status"] != previous:
                emit(f"Windows job {identity}: {value['status']}")
                previous = value["status"]
            if value["status"] not in ("queued", "running"):
                return value
            time.sleep(2)
        raise TimeoutError("The remote job has not finished. Query its job ID again; do not submit a duplicate.")


def controller_main(arguments=None):
    import argparse
    from .remote_protocol import ControllerKeys
    parser = argparse.ArgumentParser(description="Control fixed App Agent Windows test/research jobs")
    parser.add_argument("--pairing-link", required=True)
    parser.add_argument("--key-file", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("operation", choices=("info", "inventory", "learning_report", "windows", "inspect_window", "self_test", "study", "task", "job", "stop"))
    parser.add_argument("--parameters", default="{}", help="JSON operation parameters; never credentials")
    parser.add_argument("--job-id")
    args = parser.parse_args(arguments)
    try:
        client = RemoteClient(args.pairing_link, ControllerKeys.load(args.key_file))
        if args.operation == "info":
            result = client.request("GET", "/info")
        elif args.operation == "stop":
            result = client.request("POST", "/stop")
        elif args.operation == "job":
            result = client.wait(args.job_id) if args.wait else client.job(args.job_id)
        else:
            result = client.submit(args.operation, json.loads(args.parameters))
            if args.wait:
                result = client.wait(result["id"])
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if result.get("status") in ("failed", "cancelled"):
            return 1
        evidence = result.get("result", {})
        if isinstance(evidence, dict) and (evidence.get("status") in ("failed", "cancelled", "partial") or
                ("outcome" in evidence and evidence["outcome"] not in ("result_observed", "visual_result_assessed"))):
            return 1
        return 0
    except Exception as error:
        # Report a useful failure without ever dumping private key material.
        print("Windows connection failed: " + str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(controller_main())
