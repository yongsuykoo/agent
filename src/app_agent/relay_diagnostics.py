"""Relay readiness from transport events, separate from an advertised URL."""
from collections import deque
from dataclasses import dataclass, field
import json
import re
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


BRIDGE_REJECTION = "Request rejected. Check pairing, request signature, clock and size."


def redact_relay_line(line):
    line = re.sub(r"\bsk-[A-Za-z0-9_-]+", "[redacted]", str(line))
    line = re.sub(r"(?i)\bBearer\s+\S+", "Bearer [redacted]", line)
    return re.sub(r"(?i)\b(token|secret|authorization|password|api[_-]?key)\s*[=:]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,]+)",
                  r"\1=[redacted]", line)[:1000]


@dataclass
class RelayDiagnostics:
    url: str = ""
    connections: set = field(default_factory=set)
    lines: deque = field(default_factory=lambda: deque(maxlen=12))

    @property
    def ready(self):
        return bool(self.url and self.connections)

    def observe(self, line):
        line = redact_relay_line(line.strip())
        self.lines.append(line)
        match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com\b", line)
        if match:
            self.url = match.group(0)
        index = re.search(r"\bconnIndex=(\d+)\b", line)
        identity = index.group(1) if index else "default"
        if "Registered tunnel connection" in line:
            self.connections.add(identity)
        elif "Unregistered tunnel connection" in line or "failed to serve tunnel connection" in line:
            self.connections.discard(identity)

    def report(self, version, controller_fingerprint, port, local_ok, process_running):
        return "\n".join([
            f"App Agent connection {version}",
            f"Controller fingerprint: {controller_fingerprint}",
            f"Local helper: http://127.0.0.1:{port}/info" if port else "Local helper: not started",
            f"Local helper startup check: {'passed' if local_ok else 'not passed'}",
            f"Cloudflared process: {'running' if process_running else 'not running'}",
            f"Relay URL: {self.url or 'not assigned'}",
            f"Registered relay connections: {len(self.connections)}",
            "Cloud controller verification: not established by relay registration",
            "Recent relay log:", *self.lines,
        ])


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def check_local_helper(port):
    """Read only the fixed loopback endpoint; no credentials or app actions."""
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("Invalid local helper port.")
    opener = build_opener(ProxyHandler({}), NoRedirects())
    try:
        response = opener.open(Request(f"http://127.0.0.1:{port}/info", method="GET"), timeout=2)
    except HTTPError as error:
        response = error
    with response:
        payload = response.read(2049)
        if response.status != 403 or len(payload) > 2048:
            return False
        try:
            return json.loads(payload) == {"error": BRIDGE_REJECTION}
        except (ValueError, UnicodeError):
            return False
