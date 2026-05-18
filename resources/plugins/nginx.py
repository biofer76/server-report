"""Nginx status collector."""

import shutil
import subprocess
import urllib.error
import urllib.request

from resources.base import BaseCollector, Result


def _run(cmd: list[str], timeout: int = 10) -> tuple[int, str]:
    """Run a command and return (returncode, stdout)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip()
    except Exception:
        return -1, ""


class NginxCollector(BaseCollector):
    """Collects nginx process status and stub_status connection metrics."""

    @property
    def name(self) -> str:
        """Human-readable name."""
        return "Nginx"

    def is_available(self) -> bool:
        """Available when the nginx binary is present."""
        return shutil.which("nginx") is not None

    def collect(self) -> Result:
        """Check nginx process state and fetch stub_status if available."""
        try:
            rc, _ = _run(["nginx", "-t"])
            config_ok = rc == 0

            rc2, ps_out = _run(["pgrep", "-c", "nginx"])
            process_count = int(ps_out) if ps_out.isdigit() else 0

            metrics: dict = {
                "config_ok": config_ok,
                "process_count": process_count,
            }

            status_url = self.config.get("status_url", "http://127.0.0.1/nginx_status")
            stub = self._fetch_stub_status(status_url)
            if stub:
                metrics["stub_status"] = stub

            alerts = []
            if process_count == 0:
                alerts.append("No nginx processes found — nginx may be down")
            if not config_ok:
                alerts.append("nginx -t reports a configuration error")

            status = "warning" if alerts else "ok"
            return Result(name=self.name, status=status, metrics=metrics, alerts=alerts)
        except Exception as exc:
            return Result(name=self.name, status="error", metrics={}, error=str(exc))

    def _fetch_stub_status(self, url: str) -> dict | None:
        """Fetch and parse the nginx stub_status page."""
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                body = resp.read().decode("utf-8")
            lines = body.strip().splitlines()
            if len(lines) < 4:
                return None
            # stub_status format: Active connections: N
            active = int(lines[0].split(":")[1].strip())
            # server accepts handled requests
            counts = lines[2].split()
            accepts, handled, requests = int(counts[0]), int(counts[1]), int(counts[2])
            # Reading: N Writing: N Waiting: N
            rw = lines[3].split()
            return {
                "active_connections": active,
                "accepts": accepts,
                "handled": handled,
                "requests": requests,
                "reading": int(rw[1]),
                "writing": int(rw[3]),
                "waiting": int(rw[5]),
            }
        except Exception:
            return None
