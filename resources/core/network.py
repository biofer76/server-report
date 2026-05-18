"""Network metrics collector."""

import subprocess

from resources.base import BaseCollector, Result


def _run(cmd: list[str], timeout: int = 10) -> str:
    """Run a command and return stdout, empty string on error."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


class NetworkCollector(BaseCollector):
    """Collects TCP/UDP connection stats."""

    @property
    def name(self) -> str:
        """Human-readable name."""
        return "Network"

    def is_available(self) -> bool:
        """Always available on Linux."""
        return True

    def collect(self) -> Result:
        """Collect TCP connection summary."""
        try:
            metrics: dict = {}

            if self.config.get("include_summary", True):
                metrics["tcp_summary"] = self._get_tcp_summary()

            return Result(name=self.name, status="ok", metrics=metrics, alerts=[])
        except Exception as exc:
            return Result(name=self.name, status="error", metrics={}, error=str(exc))

    def _get_tcp_summary(self) -> list[str]:
        out = _run(["ss", "-s"])
        return [
            line for line in out.splitlines()
            if "estab" in line
        ][:5]
