"""Disk usage metrics collector."""

import subprocess

from resources.base import BaseCollector, Result


def _run(cmd: list[str], timeout: int = 10) -> str:
    """Run a command and return stdout, empty string on error."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


class DiskCollector(BaseCollector):
    """Collects disk usage for all relevant partitions."""

    @property
    def name(self) -> str:
        """Human-readable name."""
        return "Disk"

    def is_available(self) -> bool:
        """Always available on Linux."""
        return True

    def collect(self) -> Result:
        """Collect disk usage metrics and alert on high-usage partitions."""
        try:
            partitions = self._get_partitions()
            metrics = {"partitions": partitions}

            threshold = self.config.get("threshold_pct", 85)
            alerts = []
            for p in partitions:
                if p["pct_int"] >= threshold:
                    alerts.append(
                        f"{p['mount']} at {p['pct']} usage (threshold: {threshold}%)"
                    )

            status = "warning" if alerts else "ok"
            return Result(name=self.name, status=status, metrics=metrics, alerts=alerts)
        except Exception as exc:
            return Result(name=self.name, status="error", metrics={}, error=str(exc))

    def _get_partitions(self) -> list[dict]:
        out = _run(["df", "-h", "--output=target,size,used,avail,pcent"])
        exclude_mounts = self.config.get("exclude_mounts", ["/boot", "/boot/efi", "/sys", "/proc", "/dev", "/run"])

        rows = []
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 5:
                continue
            mount, size, used, avail, pct = parts[:5]
            if any(mount == ex or mount.startswith(ex + "/") for ex in exclude_mounts):
                continue
            if "loop" in mount:
                continue
            try:
                pct_int = int(pct.rstrip("%"))
            except ValueError:
                pct_int = 0
            rows.append({
                "mount": mount,
                "size": size,
                "used": used,
                "avail": avail,
                "pct": pct,
                "pct_int": pct_int,
            })
        return rows
