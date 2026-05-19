"""Tests for resources/core/memory.py."""

from unittest.mock import patch

from resources.core.memory import MemoryCollector
from tests.conftest import load_fixture


def _collector(config=None):
    return MemoryCollector(config or {})


def _patch_run(output: str):
    return patch("resources.core.memory._run", return_value=output)


class TestRamParsing:
    def test_ram_parsing_ubuntu(self):
        fixture = load_fixture("ubuntu-24.04", "memory", "free_m.txt")
        with _patch_run(fixture):
            ram = _collector()._get_ram()
        assert isinstance(ram["total_mb"], int)
        assert isinstance(ram["used_mb"], int)
        assert isinstance(ram["free_mb"], int)
        assert ram["total_mb"] > 0
        assert ram["used_mb"] >= 0
        assert 0 <= ram["pct"] <= 100

    def test_swap_zero_values(self):
        output = "               total        used        free\nSwap:              0           0           0\n"
        with _patch_run(output):
            swap = _collector()._get_swap()
        assert swap["total_mb"] == 0
        assert swap["used_mb"] == 0

    def test_swap_missing_values(self):
        output = "               total        used        free\nSwap:\n"
        with _patch_run(output):
            swap = _collector()._get_swap()
        assert swap["total_mb"] == 0
        assert swap["used_mb"] == 0

    def test_ram_alert_triggered(self):
        # total=1000, used=950 → pct=95%, threshold=90 → warning
        output = "               total        used        free\nMem:            1000         950          50\nSwap:              0           0           0\n"
        with _patch_run(output):
            result = _collector({"ram_threshold_pct": 90}).collect()
        assert result.status == "warning"
        assert any("RAM" in a for a in result.alerts)
