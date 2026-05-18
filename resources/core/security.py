"""Security metrics collector."""

import subprocess

from resources.base import BaseCollector, Result

_AUTH_LOG = {
    "rhel": "/var/log/secure",
    "centos": "/var/log/secure",
    "fedora": "/var/log/secure",
    "rocky": "/var/log/secure",
    "almalinux": "/var/log/secure",
}
_AUTH_LOG_DEFAULT = "/var/log/auth.log"


def _run(cmd: list[str], timeout: int = 10) -> str:
    """Run a command and return stdout, empty string on error."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


class SecurityCollector(BaseCollector):
    """Collects recent logins and failed SSH attempt counts."""

    @property
    def name(self) -> str:
        """Human-readable name."""
        return "Security"

    def is_available(self) -> bool:
        """Always available on Linux."""
        return True

    def collect(self) -> Result:
        """Collect login history and failed SSH attempts."""
        try:
            n = self.config.get("recent_logins_count", 5)
            threshold = self.config.get("failed_ssh_threshold", 10)

            recent_logins = self._get_recent_logins(n)
            failed_count = self._get_failed_ssh_attempts()

            metrics = {
                "recent_logins": recent_logins,
                "failed_ssh_attempts": failed_count,
            }

            alerts = []
            if failed_count > threshold:
                alerts.append(
                    f"{failed_count} failed SSH attempts in the last 24h"
                    f" (threshold: {threshold})"
                )

            status = "warning" if alerts else "ok"
            return Result(name=self.name, status=status, metrics=metrics, alerts=alerts)
        except Exception as exc:
            return Result(name=self.name, status="error", metrics={}, error=str(exc))

    def _get_recent_logins(self, n: int) -> list[str]:
        out = _run(["last", "-n", str(n), "--time-format", "iso"])
        return [
            line for line in out.splitlines()
            if line.strip() and not line.startswith("wtmp")
        ][:n]

    def _get_failed_ssh_attempts(self) -> int:
        distro = self.config.get("_system", {}).get("distro", "")
        log_path = _AUTH_LOG.get(distro, _AUTH_LOG_DEFAULT)
        out = _run(
            ["grep", "-c", "Failed password", log_path],
            timeout=10,
        )
        try:
            return int(out)
        except ValueError:
            return 0
