"""Tests for resources/core/disk.py."""

from unittest.mock import patch

from resources.core.disk import DiskCollector
from tests.conftest import load_fixture

_BASE_CONFIG = {
    "threshold_pct": 85,
    "exclude_mounts": ["/boot", "/boot/efi", "/sys", "/proc", "/dev", "/run"],
}


def _collector(config=None):
    return DiskCollector(config or _BASE_CONFIG)


def _patch_run(output: str):
    return patch("resources.core.disk._run", return_value=output)


class TestDiskPartitions:
    def test_only_root_partition_returned(self):
        fixture = load_fixture("ubuntu-24.04", "disk", "df_h.txt")
        with _patch_run(fixture):
            partitions = _collector()._get_partitions()
        mounts = [p["mount"] for p in partitions]
        assert mounts == ["/"]

    def test_excluded_mounts(self):
        fixture = load_fixture("ubuntu-24.04", "disk", "df_h.txt")
        with _patch_run(fixture):
            partitions = _collector()._get_partitions()
        mounts = [p["mount"] for p in partitions]
        for excluded in ["/boot", "/sys/firmware/efi/efivars", "/run", "/dev/shm"]:
            assert excluded not in mounts, f"{excluded!r} should be excluded"

    def test_alert_triggered(self):
        output = (
            "Mounted on  Size  Used Avail Use%\n"
            "/           20G   18G    2G  90%\n"
        )
        with _patch_run(output):
            result = _collector({"threshold_pct": 85, "exclude_mounts": []}).collect()
        assert result.status == "warning"
        assert any("/" in a for a in result.alerts)
