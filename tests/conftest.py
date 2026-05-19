"""Shared pytest fixtures and helpers for the server-report test suite."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(distro: str, collector: str, filename: str) -> str:
    """Read a fixture file and return its content as a string."""
    return (FIXTURES / distro / collector / filename).read_text()


@pytest.fixture
def load_fixture_fn():
    """Pytest fixture exposing load_fixture as an injectable helper."""
    return load_fixture


@pytest.fixture
def ubuntu_config():
    """Minimal merged config dict with _system set for Ubuntu 24.04."""
    return {
        "_system": {
            "distro": "ubuntu",
            "distro_version": "24.04",
            "distro_pretty": "Ubuntu 24.04 LTS",
            "package_manager": "apt",
        }
    }


@pytest.fixture
def rocky_config():
    """Minimal merged config dict with _system set for Rocky Linux 9."""
    return {
        "_system": {
            "distro": "rocky",
            "distro_version": "9",
            "distro_pretty": "Rocky Linux 9.4 (Blue Onyx)",
            "package_manager": "dnf",
        }
    }
