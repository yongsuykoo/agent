"""Launch only this helper's origin without reusing account tunnel settings."""
import os
from pathlib import Path
import subprocess
import tempfile


def start_relay(executable, port):
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("Invalid local helper port.")
    directory = tempfile.TemporaryDirectory(prefix="app-agent-relay-")
    try:
        config = Path(directory.name) / "config.yaml"
        config.write_text("{}\n", encoding="utf-8")
        # Cloudflared parses config ingress before --url. Explicit empty YAML
        # selects our CLI origin without touching the user's account config.
        environment = {name: value for name, value in os.environ.items()
                       if not name.upper().startswith("TUNNEL_") and name.upper() not in
                       {"NO_TLS_VERIFY", "AGENT_API_KEY", "OPENAI_API_KEY"}}
        tunnel = subprocess.Popen([str(executable), "tunnel", "--config", str(config),
                                   "--url", f"http://127.0.0.1:{port}",
                                   "--no-autoupdate", "--protocol", "http2"],
                                  env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, encoding="utf-8", errors="replace",
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return tunnel, directory
    except Exception:
        directory.cleanup()
        raise


def stop_relay(tunnel, directory):
    """Used off the UI thread; keep config until the child has exited."""
    if tunnel is not None and tunnel.poll() is None:
        try:
            tunnel.terminate()
        except OSError:
            pass
        try:
            tunnel.wait(timeout=5)
        except subprocess.TimeoutExpired:
            tunnel.kill()
            tunnel.wait(timeout=2)
    if directory is not None and (tunnel is None or tunnel.poll() is not None):
        directory.cleanup()
