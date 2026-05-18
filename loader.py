"""Config loading, plugin discovery, and collector initialisation."""

import importlib.util
import os
import platform
import socket
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path

import yaml

from resources.base import BaseCollector, Result

BASE_DIR = Path(__file__).parent
CONFIGS_DIR = BASE_DIR / "configs"
CORE_DIR = BASE_DIR / "resources" / "core"
PLUGINS_DIR = BASE_DIR / "resources" / "plugins"


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base; lists are always replaced, never appended."""
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def detect_system() -> dict:
    """Read /etc/os-release and return distro and package manager info."""
    info = {}
    try:
        with open("/etc/os-release") as f:
            for line in f:
                k, _, v = line.strip().partition("=")
                info[k] = v.strip('"')
    except FileNotFoundError:
        pass

    distro = info.get("ID", platform.system().lower())

    package_managers = {
        "ubuntu": "apt", "debian": "apt", "linuxmint": "apt",
        "rhel": "dnf", "centos": "dnf", "fedora": "dnf", "rocky": "dnf", "almalinux": "dnf",
        "opensuse": "zypper", "sles": "zypper",
        "arch": "pacman",
    }

    return {
        "distro":          distro,
        "distro_version":  info.get("VERSION_ID", "unknown"),
        "distro_pretty":   info.get("PRETTY_NAME", distro),
        "package_manager": package_managers.get(distro, "unknown"),
    }


def load_config() -> dict:
    """
    Resolve server_id, load base YAML files, deep-merge per-server overrides.

    Injects system detection result under the reserved key ``_system``.
    Returns a single dict keyed by resource name.
    """
    server_id = os.environ.get("SERVER_ID") or socket.gethostname()

    config: dict = {}
    for path in sorted((CONFIGS_DIR / "base").glob("*.yaml")):
        data = yaml.safe_load(path.read_text()) or {}
        config[path.stem] = data

    override_dir = CONFIGS_DIR / server_id
    if override_dir.exists():
        for path in sorted(override_dir.glob("*.yaml")):
            base = config.get(path.stem, {})
            override = yaml.safe_load(path.read_text()) or {}
            config[path.stem] = _deep_merge(base, override)

    config["_system"] = detect_system()
    config.setdefault("system", {})["_system"] = config["_system"]
    return config


def _import_file(path: Path):
    """Dynamically import a Python file by path and return the module."""
    module_name = f"_sr_plugin_{path.stem}_{id(path)}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _find_collector_class(module) -> type[BaseCollector] | None:
    """Return the first BaseCollector subclass found in the module, or None."""
    for attr in vars(module).values():
        try:
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseCollector)
                and attr is not BaseCollector
            ):
                return attr
        except TypeError:
            pass
    return None


def discover_collectors(config: dict) -> tuple[list[BaseCollector], list[str]]:
    """
    Scan core/ and plugins/, import each file safely, instantiate collectors.

    Returns (active_collectors, load_warnings).
    Active collectors have passed is_available(). Unavailable ones are silently
    discarded. Broken files produce a warning but never block the others.
    """
    timeout = config.get("general", {}).get("collector_timeout_seconds", 30)
    collectors: list[BaseCollector] = []
    warnings: list[str] = []

    for search_dir in (CORE_DIR, PLUGINS_DIR):
        for path in sorted(search_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                module = _import_file(path)
                cls = _find_collector_class(module)
                if cls is None:
                    continue
                resource_name = path.stem
                cfg = config.get(resource_name, {})
                instance = cls(cfg)
                if instance.is_available():
                    collectors.append(instance)
            except Exception as exc:
                warnings.append(f"Failed to load plugin {path.name}: {exc}")

    return collectors, warnings


def run_collectors(
    collectors: list[BaseCollector], config: dict
) -> list[Result]:
    """
    Call collect() on each active collector, enforcing collector_timeout_seconds.

    Timed-out or crashed collectors return a Result with status='error'.
    """
    timeout = config.get("general", {}).get("collector_timeout_seconds", 30)
    results: list[Result] = []

    with ThreadPoolExecutor(max_workers=len(collectors) or 1) as executor:
        futures = {executor.submit(c.collect): c for c in collectors}
        for future, collector in futures.items():
            try:
                result = future.result(timeout=timeout)
                results.append(result)
            except FuturesTimeout:
                results.append(
                    Result(
                        name=collector.name,
                        status="error",
                        metrics={},
                        error=f"Collector timed out after {timeout}s",
                    )
                )
            except Exception as exc:
                results.append(
                    Result(
                        name=collector.name,
                        status="error",
                        metrics={},
                        error=str(exc),
                    )
                )

    return results
