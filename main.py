#!/usr/bin/env python3
"""Entry point for server-report."""

import argparse
import os
import socket
import sys
from datetime import datetime
from pathlib import Path

# Load .env as the very first operation before any other import reads the env.
from dotenv import load_dotenv
load_dotenv()

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
    args = parser.parse_args()

    version = _read_version()
    hostname = os.environ.get("SERVER_ID") or socket.gethostname()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Load configuration
    config = loader.load_config()
    general = config.get("general", {})

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
        print(f"[OK] Report sent to {len(recipients)} recipient(s)")
    except Exception as exc:
        _log(f"send ERROR  host={hostname}  error={exc}")
        print(f"[ERROR] Failed to send report: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
