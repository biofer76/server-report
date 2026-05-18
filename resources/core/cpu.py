"""CPU metrics collector."""

import subprocess

from resources.base import BaseCollector, Result


def _run(cmd: list[str], timeout: int = 10) -> str:
    """Run a command and return stdout, empty string on error."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


class CpuCollector(BaseCollector):
    """Collects CPU usage, load average, core count, and top processes."""

    @property
    def name(self) -> str:
        """Human-readable name."""
        return "CPU"

    def is_available(self) -> bool:
        """Always available on Linux."""
        return True

    def collect(self) -> Result:
        """Collect CPU metrics and apply load threshold alert."""
        try:
            cores = self._get_cores()
            load_1m, load_5m, load_15m = self._get_load_avg()
            top_cpu = self._get_top_processes("-%cpu")
            top_mem = self._get_top_processes("-%mem")

            metrics = {
                "cores": cores,
                "load_1m": load_1m,
                "load_5m": load_5m,
                "load_15m": load_15m,
                "top_cpu": top_cpu,
                "top_mem": top_mem,
            }

            alerts = []
            multiplier = self.config.get("load_multiplier", 1.5)
            threshold = cores * multiplier
            if load_1m > threshold:
                alerts.append(
                    f"High load average: {load_1m:.2f} (threshold: {threshold:.2f})"
                )

            status = "warning" if alerts else "ok"
            return Result(name=self.name, status=status, metrics=metrics, alerts=alerts)
        except Exception as exc:
            return Result(name=self.name, status="error", metrics={}, error=str(exc))

    def _get_cores(self) -> int:
        out = _run(["nproc"])
        try:
            return int(out)
        except ValueError:
            return 1

    def _get_load_avg(self) -> tuple[float, float, float]:
        out = _run(["cat", "/proc/loadavg"])
        parts = out.split()
        if len(parts) >= 3:
            return float(parts[0]), float(parts[1]), float(parts[2])
        return 0.0, 0.0, 0.0

    def _get_top_processes(self, sort_flag: str) -> list[dict]:
        n = self.config.get("top_processes_n", 5)
        out = _run(["ps", "aux", f"--sort={sort_flag}"])
        lines = out.splitlines()
        if len(lines) < 2:
            return []
        rows = []
        for line in lines[1 : n + 1]:
            parts = line.split(None, 10)
            if len(parts) < 11:
                continue
            rows.append({
                "user": parts[0],
                "pid": parts[1],
                "cpu": parts[2],
                "mem": parts[3],
                "cmd": parts[10],
            })
        return rows
