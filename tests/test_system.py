"""Tests for detect_system() in loader.py."""

import platform
from unittest.mock import mock_open, patch

from loader import detect_system
from tests.conftest import load_fixture


class TestDetectSystem:
    def test_os_release_ubuntu(self):
        content = load_fixture("ubuntu-24.04", "system", "os_release.txt")
        with patch("builtins.open", mock_open(read_data=content)):
            result = detect_system()
        assert result["distro"] == "ubuntu"
        assert result["distro_version"].startswith("24.")
        assert result["package_manager"] == "apt"

    def test_os_release_rocky(self):
        content = load_fixture("rocky-9", "system", "os_release.txt")
        with patch("builtins.open", mock_open(read_data=content)):
            result = detect_system()
        assert result["distro"] == "rocky"
        assert result["distro_version"].startswith("9")
        assert result["package_manager"] == "dnf"

    def test_os_release_missing(self):
        with patch("builtins.open", side_effect=FileNotFoundError):
            result = detect_system()
        assert result["distro"] == platform.system().lower()
        assert "distro_version" in result
        assert "package_manager" in result
