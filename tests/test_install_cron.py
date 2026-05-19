"""Tests for --install-cron and --remove-cron CLI flags in main.py."""

import subprocess
import sys
from pathlib import Path

_MAIN = str(Path(__file__).parent.parent / "main.py")


class TestCronFlags:
    def test_install_cron_requires_root(self):
        result = subprocess.run(
            [sys.executable, _MAIN, "--install-cron"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "--install-cron must be run as root" in result.stderr

    def test_remove_cron_requires_root(self):
        result = subprocess.run(
            [sys.executable, _MAIN, "--remove-cron"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "--remove-cron must be run as root" in result.stderr
