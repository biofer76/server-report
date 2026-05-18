"""Memory (RAM + swap) metrics collector."""

import subprocess

from resources.base import BaseCollector, Result


def _run(cmd: list[str], timeout: int = 10) -> str:
    """Run a command and return stdout, empty string on error."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


class MemoryCollector(BaseCollector):
    """Collects RAM and swap usage, raises alerts on high usage."""

    @property
    def name(self) -> str:
        """Human-readable name."""
        return "Memory"

    def is_available(self) -> bool:
        """Always available on Linux."""
        return True

    def collect(self) -> Result:
        """Collect memory metrics and apply threshold alerts."""
        try:
            ram = self._get_ram()
            swap = self._get_swap()

            metrics = {"ram": ram, "swap": swap}

            alerts = []
            ram_threshold = self.config.get("ram_threshold_pct", 90)
            swap_threshold = self.config.get("swap_threshold_pct", 80)

            if ram["pct"] >= ram_threshold:
                alerts.append(
                    f"RAM usage at {ram['pct']:.1f}% (threshold: {ram_threshold}%)"
                )

            if swap["total"] > 0:
                swap_pct = swap["used"] / swap["total"] * 100
                if swap_pct >= swap_threshold:
                    alerts.append(
                        f"Swap usage at {swap_pct:.1f}% (threshold: {swap_threshold}%)"
                    )

            status = "warning" if alerts else "ok"
            return Result(name=self.name, status=status, metrics=metrics, alerts=alerts)
        except Exception as exc:
            return Result(name=self.name, status="error", metrics={}, error=str(exc))

    def _get_ram(self) -> dict:
        out = _run(["free", "-m"])
        for line in out.splitlines():
            if line.startswith("Mem:"):
                parts = line.split()
                total = int(parts[1])
                used = int(parts[2])
                free = int(parts[3])
                pct = used / total * 100 if total else 0.0
                return {"total_mb": total, "used_mb": used, "free_mb": free, "pct": pct}
        return {"total_mb": 0, "used_mb": 0, "free_mb": 0, "pct": 0.0}

    def _get_swap(self) -> dict:
        out = _run(["free", "-m"])
        for line in out.splitlines():
            if line.startswith("Swap:"):
                parts = line.split()
                return {"total_mb": int(parts[1]), "used_mb": int(parts[2])}
        return {"total_mb": 0, "used_mb": 0}
