"""Docker container status collector."""

import json
import shutil
import subprocess

from resources.base import BaseCollector, Result


def _run(cmd: list[str], timeout: int = 15) -> tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as exc:
        return -1, "", str(exc)


class DockerCollector(BaseCollector):
    """Collects running (and optionally stopped) container stats via the Docker CLI."""

    @property
    def name(self) -> str:
        """Human-readable name."""
        return "Docker"

    def is_available(self) -> bool:
        """Available when the docker binary is present."""
        return shutil.which("docker") is not None

    def collect(self) -> Result:
        """List containers and collect basic status metrics."""
        try:
            include_stopped = self.config.get("include_stopped", False)
            cmd = ["docker", "ps", "--format", "{{json .}}"]
            if include_stopped:
                cmd.append("-a")

            rc, stdout, stderr = _run(cmd)
            if rc != 0:
                return Result(
                    name=self.name,
                    status="error",
                    metrics={},
                    error=f"docker ps failed: {stderr}",
                )

            containers = []
            for line in stdout.splitlines():
                line = line.strip()
                if line:
                    try:
                        containers.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

            unhealthy = [
                c["Names"] for c in containers
                if c.get("Status", "").startswith("Exited")
                or "unhealthy" in c.get("Status", "").lower()
            ]

            metrics = {
                "container_count": len(containers),
                "containers": [
                    {"name": c.get("Names"), "status": c.get("Status"), "image": c.get("Image")}
                    for c in containers
                ],
            }

            alerts = []
            if unhealthy:
                alerts.append(f"Containers not running: {', '.join(unhealthy)}")

            status = "warning" if alerts else "ok"
            return Result(name=self.name, status=status, metrics=metrics, alerts=alerts)
        except Exception as exc:
            return Result(name=self.name, status="error", metrics={}, error=str(exc))
