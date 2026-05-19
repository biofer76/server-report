"""Tests for resources/core/services.py."""

from unittest.mock import MagicMock, patch

from resources.core.services import ServicesCollector
from tests.conftest import load_fixture


def _make_proc(returncode: int, stdout: str = "") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    return m


def _collector(config: dict):
    return ServicesCollector(config)


class TestAvailableUpdates:
    def test_apt_updates_count(self):
        fixture = load_fixture("ubuntu-24.04", "services", "apt_upgradable.txt")
        config = {"_system": {"package_manager": "apt"}}
        with patch("resources.core.services._run", return_value=fixture):
            count = _collector(config)._get_available_updates()
        assert isinstance(count, int)
        assert count >= 0

    def test_dnf_updates_count(self):
        fixture = load_fixture("rocky-9", "services", "dnf_check_update.txt")
        config = {"_system": {"package_manager": "dnf"}}
        with patch("resources.core.services.subprocess.run", return_value=_make_proc(100, fixture)):
            count = _collector(config)._get_available_updates()
        assert isinstance(count, int)
        assert count >= 0

    def test_dnf_no_updates(self):
        fixture = load_fixture("rocky-9", "services", "dnf_no_updates.txt")
        config = {"_system": {"package_manager": "dnf"}}
        with patch("resources.core.services.subprocess.run", return_value=_make_proc(0, fixture)):
            count = _collector(config)._get_available_updates()
        assert count == 0

    def test_unknown_package_manager(self):
        config = {"_system": {"package_manager": "unknown"}}
        count = _collector(config)._get_available_updates()
        assert count == -1
