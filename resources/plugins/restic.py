"""Restic backup snapshot collector."""

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone

from resources.base import BaseCollector, Result


def _run(cmd: list[str], env: dict | None = None, timeout: int = 20) -> tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as exc:
        return -1, "", str(exc)


class ResticCollector(BaseCollector):
    """Checks that recent restic snapshots exist within the configured age limit."""

    @property
    def name(self) -> str:
        """Human-readable name."""
        return "Restic Snapshots"

    def is_available(self) -> bool:
        """Available when the restic binary is present."""
        return shutil.which("restic") is not None

    def collect(self) -> Result:
        """Check latest snapshot age and report status."""
        try:
            repository = self.config.get("repository", "/mnt/backups/restic")
            max_age_hours = self.config.get("max_snapshot_age_hours", 26)
            password = os.environ.get("RESTIC_PASSWORD")

            env = dict(os.environ)
            env["RESTIC_REPOSITORY"] = repository
            if password:
                env["RESTIC_PASSWORD"] = password

            rc, stdout, stderr = _run(
                ["restic", "snapshots", "--json", "--last"],
                env=env,
            )
            if rc != 0:
                return Result(
                    name=self.name,
                    status="error",
                    metrics={},
                    error=f"restic snapshots failed: {stderr}",
                )

            snapshots = json.loads(stdout) if stdout else []
            if not snapshots:
                return Result(
                    name=self.name,
                    status="warning",
                    metrics={"snapshot_count": 0},
                    alerts=["No snapshots found in repository"],
                )

            latest = snapshots[-1]
            latest_time_str = latest.get("time", "")
            latest_time = datetime.fromisoformat(
                latest_time_str.replace("Z", "+00:00")
            )
            now = datetime.now(tz=timezone.utc)
            age_hours = (now - latest_time).total_seconds() / 3600

            metrics = {
                "snapshot_count": len(snapshots),
                "latest_snapshot_time": latest_time_str,
                "latest_snapshot_age_hours": round(age_hours, 1),
                "repository": repository,
            }

            alerts = []
            if age_hours > max_age_hours:
                alerts.append(
                    f"Latest snapshot is {age_hours:.1f}h old (threshold: {max_age_hours}h)"
                )

            status = "warning" if alerts else "ok"
            return Result(name=self.name, status=status, metrics=metrics, alerts=alerts)
        except Exception as exc:
            return Result(name=self.name, status="error", metrics={}, error=str(exc))
