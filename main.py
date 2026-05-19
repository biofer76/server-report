#!/usr/bin/env python3
"""Entry point for server-report."""

import argparse
import os
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Load .env as the very first operation before any other import reads the env.
from dotenv import load_dotenv
load_dotenv(override=True)

import loader
import mailer
from formatters.text import TextFormatter
from formatters.html import HtmlFormatter
from formatters.json import JsonFormatter
from formatters.csv import CsvFormatter

_FORMATTER_MAP = {
    "text": TextFormatter,
    "html": HtmlFormatter,
    "json": JsonFormatter,
    "csv": CsvFormatter,
}

_LOG_PATH = Path("/var/log/server-report.log")
_VERSION_PATH = Path(__file__).parent / "VERSION"


def _read_version() -> str:
    """Read the VERSION file."""
    try:
        return _VERSION_PATH.read_text().strip()
    except Exception:
        return "unknown"


def _log(message: str) -> None:
    """Append a timestamped line to the execution log."""
    entry = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {message}\n"
    try:
        with open(_LOG_PATH, "a") as f:
            f.write(entry)
    except OSError:
        pass  # non-fatal if log directory is not writable


_CRON_MARKER = "server-report/main.py"
_MAIN_PY = str(Path(__file__).resolve())


def _require_root(flag: str) -> None:
    """Exit with an error if the current process is not running as root."""
    if os.geteuid() != 0:
        print(f"[ERROR] {flag} must be run as root (use sudo)", file=sys.stderr)
        sys.exit(1)


def _read_crontab() -> list[str]:
    """Return current root crontab lines, or [] if no crontab is set."""
    result = subprocess.run(
        ["crontab", "-l"], capture_output=True, text=True
    )
    if result.returncode != 0:
        return []
    return result.stdout.splitlines()


def _write_crontab(lines: list[str]) -> None:
    """Write lines as the root crontab."""
    content = "\n".join(lines) + "\n"
    subprocess.run(
        ["crontab", "-"],
        input=content, text=True, check=True,
    )


def _install_cron(general: dict) -> None:
    """Write the server-report cron entry, replacing any existing one."""
    _require_root("--install-cron")
    schedule = general.get("cron_schedule", "0 8 * * *")
    cron_line = f"{schedule} {sys.executable} {_MAIN_PY} >> /var/log/server-report.log 2>&1"
    existing = [l for l in _read_crontab() if _CRON_MARKER not in l]
    _write_crontab(existing + [cron_line])
    print(f"[OK] Cron entry written: {cron_line}")
    _log(f"install-cron OK  entry={cron_line!r}")


def _remove_cron() -> None:
    """Remove the server-report cron entry if present."""
    _require_root("--remove-cron")
    current = _read_crontab()
    filtered = [l for l in current if _CRON_MARKER not in l]
    if len(filtered) == len(current):
        print("[INFO] No cron entry found for server-report")
        return
    _write_crontab(filtered)
    print("[OK] Cron entry removed")
    _log("remove-cron OK")


def _build_recipients(args: argparse.Namespace, general_config: dict) -> list[dict]:
    """Return the recipient list, overriding with CLI arguments when given."""
    if args.to:
        fmt = args.format or "text"
        return [{"email": args.to, "format": fmt}]
    return general_config.get("recipients", [])


def main() -> None:
    """Orchestrate the full execution flow."""
    parser = argparse.ArgumentParser(description="Periodic server status report")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Render using the text formatter and print to stdout; do not send email",
    )
    parser.add_argument(
        "--to",
        default="",
        help="Override recipient email address for a one-off send",
    )
    parser.add_argument(
        "--format",
        choices=list(_FORMATTER_MAP.keys()),
        default="",
        help="Format to use with --to (default: text)",
    )
    parser.add_argument(
        "--install-cron",
        action="store_true",
        help="Write the cron entry for this server (requires root)",
    )
    parser.add_argument(
        "--remove-cron",
        action="store_true",
        help="Remove the cron entry for this server (requires root)",
    )
    args = parser.parse_args()

    # Load configuration (needed by cron operations too)
    config = loader.load_config()
    general = config.get("general", {})

    if args.install_cron:
        _install_cron(general)
        return

    if args.remove_cron:
        _remove_cron()
        return

    version = _read_version()
    hostname = os.environ.get("SERVER_ID") or socket.gethostname()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Discover and run collectors
    collectors, warnings = loader.discover_collectors(config)
    results = loader.run_collectors(collectors, config)

    # Inject load warnings as a synthetic result if any plugins failed
    if warnings:
        from resources.base import Result
        results.append(
            Result(
                name="Plugin Loader",
                status="warning",
                metrics={"warnings": warnings},
                alerts=[f"Plugin load warning: {w}" for w in warnings],
            )
        )

    if args.dry_run:
        output = TextFormatter().render(results, hostname, timestamp, version)
        print(output)
        _log(f"dry-run OK  host={hostname}  version={version}  collectors={len(collectors)}")
        return

    # Determine which formats are needed
    recipients = _build_recipients(args, general)
    needed_formats = {r.get("format", "text") for r in recipients}

    # Render each format once
    rendered: dict[str, str] = {}
    for fmt in needed_formats:
        cls = _FORMATTER_MAP.get(fmt)
        if cls is None:
            continue
        rendered[fmt] = cls().render(results, hostname, timestamp, version)

    # Send
    try:
        # Temporarily override recipients in config for dispatch
        dispatch_config = dict(general)
        dispatch_config["recipients"] = recipients
        mailer.dispatch(
            results=results,
            hostname=hostname,
            timestamp=timestamp,
            version=version,
            config=dispatch_config,
            rendered=rendered,
        )
        _log(
            f"send OK  host={hostname}  version={version}  "
            f"collectors={len(collectors)}  recipients={len(recipients)}"
        )
    except Exception as exc:
        _log(f"send ERROR  host={hostname}  error={exc}")
        print(f"[ERROR] Failed to send report: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
