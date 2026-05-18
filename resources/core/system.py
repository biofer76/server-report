"""General system information collector."""

import socket
import subprocess

from resources.base import BaseCollector, Result


def _run(cmd: list[str], timeout: int = 10) -> str:
    """Run a command and return stdout, empty string on error."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


class SystemCollector(BaseCollector):
    """Collects static system information: distro, kernel, uptime, CPU model, RAM."""

    @property
    def name(self) -> str:
        """Human-readable name."""
        return "System"

    def is_available(self) -> bool:
        """Always available on Linux."""
        return True

    def collect(self) -> Result:
        """Collect general system information. No alerts or thresholds."""
        try:
            metrics = {
                "hostname":     socket.gethostname(),
                "distro":       self.config.get("_system", {}).get("distro_pretty", "unknown"),
                "kernel":       _run(["uname", "-r"]),
                "architecture": _run(["uname", "-m"]),
                "uptime":       self._get_uptime(),
                "cpu_model":    self._get_cpu_model(),
                "total_ram_mb": self._get_total_ram_mb(),
            }
            return Result(name=self.name, status="ok", metrics=metrics, alerts=[])
        except Exception as exc:
            return Result(name=self.name, status="error", metrics={}, error=str(exc))

    def _get_uptime(self) -> str:
        out = _run(["uptime", "-p"])
        return out if out else _run(["uptime"])

    def _get_cpu_model(self) -> str:
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        return line.partition(":")[2].strip()
        except OSError:
            pass
        return "unknown"

    def _get_total_ram_mb(self) -> int:
        out = _run(["free", "-m"])
        for line in out.splitlines():
            if line.startswith("Mem:"):
                parts = line.split()
                try:
                    return int(parts[1])
                except (IndexError, ValueError):
                    pass
        return 0
