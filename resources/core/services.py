"""Systemd services collector."""

import shutil
import subprocess

from resources.base import BaseCollector, Result


def _run(cmd: list[str], timeout: int = 10) -> str:
    """Run a command and return stdout, empty string on error."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


class ServicesCollector(BaseCollector):
    """Collects failed systemd services and checks watched services."""

    @property
    def name(self) -> str:
        """Human-readable name."""
        return "Services"

    def is_available(self) -> bool:
        """Available when systemctl is present."""
        return shutil.which("systemctl") is not None

    def collect(self) -> Result:
        """Collect failed services count and optionally check specific services."""
        try:
            failed = self._get_failed_services()
            watched = self._check_watched_services()
            available_updates = self._get_available_updates()

            metrics = {
                "failed_count": len(failed),
                "failed_services": failed,
                "watched": watched,
                "available_updates": available_updates,
            }

            alerts = []
            if failed:
                alerts.append(
                    f"{len(failed)} service(s) in failed state: {', '.join(failed)}"
                )
            for svc_name, state in watched.items():
                if state != "active":
                    alerts.append(f"Service '{svc_name}' is {state}")

            status = "warning" if alerts else "ok"
            return Result(name=self.name, status=status, metrics=metrics, alerts=alerts)
        except Exception as exc:
            return Result(name=self.name, status="error", metrics={}, error=str(exc))

    def _get_failed_services(self) -> list[str]:
        out = _run(["systemctl", "--failed", "--no-legend", "--plain"])
        services = []
        for line in out.splitlines():
            parts = line.split()
            name = next(
                (p for p in parts if p != "●" and not p.startswith("●")), None
            )
            if name:
                services.append(name)
        return services[:10]

    def _check_watched_services(self) -> dict[str, str]:
        watch = self.config.get("watch", [])
        result = {}
        for svc in watch:
            out = _run(["systemctl", "is-active", svc])
            result[svc] = out or "unknown"
        return result

    def _get_available_updates(self) -> int:
        """Return the number of available updates, or -1 if detection failed."""
        pkg_manager = self.config.get("_system", {}).get("package_manager", "unknown")

        if pkg_manager == "apt":
            out = _run(["apt", "list", "--upgradable"])
            return sum(1 for l in out.splitlines() if "/" in l)

        elif pkg_manager == "dnf":
            # dnf check-update exits 100 when updates are available, 0 when none, 1 on error.
            # --cacheonly reads the local metadata cache without hitting the network.
            # Exit code 1 with --cacheonly means the cache is empty, not an error.
            result = subprocess.run(
                ["dnf", "check-update", "--quiet", "--cacheonly"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 1:
                # Cache empty: fall back to a full network check.
                result = subprocess.run(
                    ["dnf", "check-update", "--quiet"],
                    capture_output=True, text=True, timeout=30,
                )
            if result.returncode not in (0, 100):
                return -1
            count = 0
            for line in result.stdout.splitlines():
                if not line.strip():
                    continue
                if line.startswith("Obsoleting"):
                    break
                first_word = line.split()[0] if line.split() else ""
                if "." in first_word:
                    count += 1
            return count

        return -1
