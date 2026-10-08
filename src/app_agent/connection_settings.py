"""Explicit public host selection for an account-owned named tunnel."""
import ipaddress
import re

NAMED_TUNNEL_PORT = 8765


def public_hostname(value):
    if not isinstance(value, str):
        raise ValueError("Enter a public DNS hostname without https:// or a path.")
    value = value.strip().lower()
    if len(value) > 253 or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+", value):
        raise ValueError("Enter a public DNS hostname without https:// or a path.")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        raise ValueError("Named tunnels require a DNS hostname, not an IP address.")
    if value.endswith((".localhost", ".local", ".invalid", ".test")):
        raise ValueError("Named tunnels require a public DNS hostname.")
    return value


def tunnel_token(value):
    if not isinstance(value, str) or not 20 <= len(value.strip()) <= 8192:
        raise ValueError("Paste the Cloudflare tunnel token into its masked Windows field.")
    value = value.strip()
    parts = value.split()
    if parts and parts[0] == "sudo":
        parts = parts[1:]
    if len(parts) == 4 and parts[0].lower() in ("cloudflared", "cloudflared.exe") and parts[1:3] == ["service", "install"]:
        # Parse the dashboard's command as text; never execute it or install a service.
        value = parts[3].strip("\"'")
    if not 20 <= len(value) <= 8192 or not re.fullmatch(r"[A-Za-z0-9_.=+/-]+", value):
        raise ValueError("Paste the token or Cloudflare's cloudflared service install command into this field.")
    return value
