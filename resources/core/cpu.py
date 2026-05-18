"""CPU metrics collector."""

import os
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
            own_pid = str(os.getpid())
            cores = self._get_cores()
            load_1m, load_5m, load_15m = self._get_load_avg()
            top_cpu = self._get_top_processes("-%cpu", own_pid)
            top_mem = self._get_top_processes("-%mem", own_pid)

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

    def _get_top_processes(self, sort_flag: str, own_pid: str) -> list[dict]:
        n = self.config.get("top_processes_n", 5)
        out = _run(["ps", "-eo", "user,pid,ppid,%cpu,%mem,cmd", f"--sort={sort_flag}"])
        lines = out.splitlines()
        if len(lines) < 2:
            return []
        rows = []
        for line in lines[1:]:
            parts = line.split(None, 5)
            if len(parts) < 6:
                continue
            pid, ppid = parts[1], parts[2]
            if pid == own_pid or ppid == own_pid:
                continue
            rows.append({
                "user": parts[0],
                "pid": pid,
                "cpu": parts[3],
                "mem": parts[4],
                "cmd": parts[5],
            })
            if len(rows) == n:
                break
        return rows
