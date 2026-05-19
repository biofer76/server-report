"""Tests for resources/core/security.py."""

from unittest.mock import patch

from resources.core.security import SecurityCollector
from tests.conftest import load_fixture


def _collector(config=None):
    return SecurityCollector(config or {})


def _patch_run(output: str):
    return patch("resources.core.security._run", return_value=output)


class TestSecurityCollector:
    def test_wtmp_line_filtered(self):
        fixture = load_fixture("ubuntu-24.04", "security", "last.txt")
        with _patch_run(fixture):
            logins = _collector()._get_recent_logins(10)
        assert not any(line.startswith("wtmp") for line in logins)

    def test_empty_lines_filtered(self):
        fixture = load_fixture("ubuntu-24.04", "security", "last.txt")
        with _patch_run(fixture):
            logins = _collector()._get_recent_logins(10)
        assert not any(line.strip() == "" for line in logins)

    def test_failed_ssh_count_is_integer(self):
        with _patch_run("42"):
            result = _collector().collect()
        assert isinstance(result.metrics["failed_ssh_attempts"], int)
