# server-report - Architecture Document

## Overview

`server-report` is a lightweight, extensible server monitoring system that collects system metrics and delivers periodic status reports via email. It is designed to be deployed on Linux VPS servers using Git and Ansible, and to adapt to different server configurations through a plugin system.

The system is intentionally simple in scope: it runs on a schedule, collects data, formats it, and sends it. There is no real-time alerting, no persistent storage, and no dashboard. This simplicity is a deliberate design choice that makes the system easy to install, maintain, and reason about.

---

## Goals

- Provide a unified monitoring solution adoptable as a standard across multiple client servers
- Allow easy extension through plugins without modifying the core system
- Support multiple recipients with individual format preferences
- Be deployable in minutes on a new server via Ansible
- Remain stateless: each execution is independent, no history is stored on the server

---

## Non-goals

The following are explicitly out of scope:

- Real-time alerting (use dedicated tools like PagerDuty or Grafana for this)
- Metric history and time-series storage on the server (delegated to the recipient)
- Web dashboard or UI
- Multi-server aggregation (one instance per server)
- Custom report templates per recipient
- Docker containerization (unnecessary complexity given minimal dependencies)

---

## Stack

- **Python 3.10+** running directly on the host
- **PyYAML** for config file parsing
- **python-dotenv** for `.env` file loading
- **Git** for distribution and updates
- **Ansible** for provisioning, deploy, and updates
- **Cron** on the server for scheduling, written by Ansible reading from config
- **Ansible Vault** for secrets management

---

## Dependencies

All external dependencies are declared in `requirements.txt` with pinned versions. Ansible installs them during the deploy using the pinned versions to ensure consistency across servers.

```
PyYAML==6.0.2
python-dotenv==1.0.1
```

---

## Versioning

The repository contains a `VERSION` file with the current version string, for example `1.0.0`. Every report includes the version in its header so the recipient always knows which version generated it. Ansible logs the deployed version during install and update operations.

---

## Deployment Model

Each monitored server runs the system directly on the host. The repository is cloned into a fixed path, for example `/opt/server-report`. Ansible manages the full lifecycle.

### Installing on a new server

1. Verify Python 3.10+ is present, install if missing
2. Install `python3.12-venv` if missing: `sudo apt install python3.12-venv`
3. Clone the repository to `/opt/server-report`
4. Create the virtualenv: `python3 -m venv /opt/server-report/.venv`
5. Install dependencies: `/opt/server-report/.venv/bin/pip install -r requirements.txt`
6. Set the server hostname via Ansible to match the folder name under `configs/`
7. Write the `.env` file with server-specific secrets, generated from Ansible Vault
8. Read `cron_schedule` from the server's `general.yaml` and write the cron entry
9. Run `/opt/server-report/.venv/bin/python main.py --dry-run` as a smoke test

### Updating an existing server

1. `git pull` on the server
2. `/opt/server-report/.venv/bin/pip install -r requirements.txt` to pick up any new or updated dependencies
3. Restart cron if the schedule has changed

Both operations are Ansible playbooks: `ansible/install.yml` and `ansible/update.yml`.

---

## Project Structure

```
server-report/
├── VERSION                  # current version string, e.g. "1.0.0"
├── requirements.txt         # pinned external dependencies
├── main.py                  # entry point, CLI arguments
├── loader.py                # config merge, plugin discovery and initialization
├── mailer.py                # email sending via Mailgun
├── formatters/
│   ├── base.py              # abstract base formatter
│   ├── text.py              # plain text (email body)
│   ├── html.py              # HTML (email body)
│   ├── json.py              # full structured report (email attachment)
│   └── csv.py               # anomaly log with fixed columns (email attachment)
├── resources/
│   ├── base.py              # abstract base collector
│   ├── core/                # standard resources, available on any Linux server
│   │   ├── cpu.py
│   │   ├── memory.py
│   │   ├── disk.py
│   │   ├── network.py
│   │   └── services.py
│   └── plugins/             # optional resources, loaded if the file is present
│       ├── restic.py
│       ├── docker.py
│       └── nginx.py
├── configs/
│   ├── base/                # default values for all resources and plugins
│   │   ├── general.yaml     # schedule, mailgun, recipients
│   │   ├── cpu.yaml
│   │   ├── memory.yaml
│   │   ├── disk.yaml
│   │   ├── network.yaml
│   │   ├── services.yaml
│   │   ├── restic.yaml
│   │   ├── docker.yaml
│   │   └── nginx.yaml
│   ├── vps-prod/            # overrides for vps-prod (must match server hostname)
│   │   ├── general.yaml     # only keys that differ from base
│   │   └── restic.yaml
│   └── vps-staging/
│       └── general.yaml
└── ansible/
    ├── install.yml
    └── update.yml
```

### Responsibilities

| Component             | Responsibility                                                                            |
| --------------------- | ----------------------------------------------------------------------------------------- |
| `main.py`             | Parse CLI arguments, load `.env`, orchestrate the full execution flow                     |
| `loader.py`           | Identify server, merge config, discover collectors, pass config to each, enforce timeouts |
| `mailer.py`           | Receive formatted output per recipient and send via Mailgun API                           |
| `formatters/`         | Transform the list of Result objects into a specific output format                        |
| `resources/base.py`   | Define the collector interface all resources must implement                               |
| `resources/core/`     | Standard metrics always present on any Linux server                                       |
| `resources/plugins/`  | Optional metrics depending on what is installed on the server                             |
| `configs/base/`       | Default values shared across all servers, one YAML file per resource                      |
| `configs/<hostname>/` | Per-server overrides, only files and keys that differ from base                           |

---

## Configuration System

### Server identification

The system identifies the current server using the following logic:

```python
import os, socket
server_id = os.environ.get("SERVER_ID") or socket.gethostname()
```

By default it reads the system hostname, which Ansible sets at provisioning time to match the folder name under `configs/`. The `SERVER_ID` environment variable can override this in edge cases, for example when the hostname cannot be changed or when running the system manually on a different machine.

The hostname set by Ansible in the inventory must match exactly the folder name under `configs/`. If the names diverge, the system falls back to `configs/base/` without warning. This is a known operational risk, mitigated by the `--dry-run` smoke test after every deploy.

### Config merge

`loader.py` performs the merge in two steps:

1. Load all YAML files from `configs/base/` into a single dict, keyed by resource name
2. Load all YAML files from `configs/<server_id>/` and merge key by key into the base dict

**Merge rule: lists are always replaced in full, never appended.** This is a general rule of the system with no exceptions. A server override file only needs to contain the keys that differ from base. All other keys retain their base defaults.

```python
import yaml

def load_config(server_id: str) -> dict:
    config = {}
    for path in sorted(BASE_DIR.glob("*.yaml")):
        config[path.stem] = yaml.safe_load(path.read_text())

    override_dir = CONFIGS_DIR / server_id
    if override_dir.exists():
        for path in sorted(override_dir.glob("*.yaml")):
            base = config.get(path.stem, {})
            override = yaml.safe_load(path.read_text())
            config[path.stem] = {**base, **override}

    return config
```

### System detection

After the config merge, `loader.py` detects the host operating system and package manager by reading `/etc/os-release`. The result is injected into the config dict under the reserved key `_system`, which is then passed to every collector along with the rest of the config.

```python
import platform

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
```

The `_system` key is reserved and must never appear in any YAML config file. It is populated exclusively by `loader.py` at runtime.

The merged config dict passed to every collector has the following structure:

```python
{
    "cpu":      { ... },   # from configs/base/cpu.yaml + override
    "memory":   { ... },
    "disk":     { ... },
    # ... one key per resource
    "_system":  {          # injected by loader.py, never from YAML
        "distro":          "ubuntu",
        "distro_version":  "24.04",
        "distro_pretty":   "Ubuntu 24.04 LTS",
        "package_manager": "apt",
    }
}
```

### Scheduling

The `cron_schedule` field in `configs/<server_id>/general.yaml` (or `configs/base/general.yaml` if not overridden) is the single source of truth for the execution schedule. Ansible reads this value directly from the YAML file during install and update, and writes the cron entry accordingly. There is no manual duplication of the schedule value.

```yaml
# Ansible reads this value and writes the cron entry
cron_schedule: "0 8 * * *"
```

The cron entry written by Ansible uses the virtualenv Python directly:

```bash
0 8 * * * /opt/server-report/.venv/bin/python /opt/server-report/main.py
```

### Secrets management

Secrets are never stored in the Git repository. They are managed via **Ansible Vault** and written to `/opt/server-report/.env` on each server during the deploy. `python-dotenv` loads this file at startup and exposes its contents as environment variables. Plugins read secrets exclusively from the environment, never from the config dict.

| What                     | Where                                    |
| ------------------------ | ---------------------------------------- |
| Structural configuration | Git repository, `configs/` folder (YAML) |
| Encrypted secrets        | Ansible repository, Ansible Vault        |
| Plaintext secrets        | Server only, `/opt/server-report/.env`   |

Example `.env` file written by Ansible on the server:

```bash
MAILGUN_API_KEY=key-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
RESTIC_PASSWORD=supersecretpassword
```

Plugins read secrets from the environment:

```python
import os
password = os.environ.get("RESTIC_PASSWORD")
```

### Config file examples

`configs/base/general.yaml`:

```yaml
mailgun_domain:  "mg.yourdomain.com"
mailgun_api_url: "https://api.mailgun.net/v3"  # use api.eu.mailgun.net for EU accounts

recipients:
  - email: "admin@yourdomain.com"
    format: "html"

cron_schedule: "0 8 * * *"  # every day at 08:00
```

`configs/vps-prod/general.yaml`:

```yaml
# Only keys that differ from base

recipients:
  - email: "admin@yourdomain.com"
    format: "html"
  - email: "backup@yourdomain.com"
    format: "json"
  - email: "ops@yourdomain.com"
    format: "csv"

cron_schedule: "0 6 * * *"
```

`configs/base/restic.yaml`:

```yaml
repository:             "/mnt/backups/restic"
max_snapshot_age_hours: 26
```

`configs/vps-prod/restic.yaml`:

```yaml
# Only the repository path differs on this server
repository: "/mnt/client-backups/restic"
```

---

## Collector Interface

Every resource, both core and plugin, must implement the interface defined in `resources/base.py`. The loader instantiates each collector passing its merged config dict, then calls `is_available()` before `collect()`.

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

@dataclass
class Result:
    name:    str
    status:  str                                       # "ok" | "warning" | "error" | "unavailable"
    metrics: dict                                      # free-form, structure defined by each collector
    alerts:  list[str] = field(default_factory=list)  # empty if no issues
    error:   str | None = None                        # set if collect() raised an exception


class BaseCollector(ABC):

    def __init__(self, config: dict) -> None:
        """
        Receives the merged config dict for this resource.
        Keys come from configs/base/<resource>.yaml overridden by configs/<server_id>/<resource>.yaml.
        Secrets must be read from environment variables, not from config.
        """
        self.config = config

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the resource (e.g. 'CPU', 'Restic Snapshots')."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """
        Return True if this collector can run on the current host.
        Called before collect(). If False, the collector is silently skipped.
        """
        ...

    @abstractmethod
    def collect(self) -> Result:
        """
        Collect metrics and return a Result object.
        Must never raise exceptions: catch internally and return
        a Result with status='error' and the error message set.
        """
        ...
```

### Collector timeout

Every `collect()` call is subject to a maximum execution timeout defined in `configs/base/general.yaml`:

```yaml
collector_timeout_seconds: 30
```

If a collector exceeds this timeout, `loader.py` interrupts it and returns a Result with `status='error'` and a descriptive error message. This prevents a single slow or hanging collector from blocking the entire report.

### Plugin loading safety

The loader imports plugin files dynamically. If a plugin file has a syntax error or a missing import, the loader catches the exception, records a warning, and continues loading the remaining plugins. A broken plugin never blocks the execution of the others. Load warnings are included in the report so the operator is always informed.

### Example plugin skeleton

```python
# resources/plugins/restic.py

import os
import shutil
from resources.base import BaseCollector, Result

class ResticCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "Restic Snapshots"

    def is_available(self) -> bool:
        return shutil.which("restic") is not None

    def collect(self) -> Result:
        try:
            repository = self.config.get("repository", "/mnt/backups/restic")
            password   = os.environ.get("RESTIC_PASSWORD")
            max_age    = self.config.get("max_snapshot_age_hours", 26)

            # collect metrics here
            metrics = { ... }
            alerts  = []
            status  = "ok"

            return Result(name=self.name, status=status, metrics=metrics, alerts=alerts)
        except Exception as e:
            return Result(name=self.name, status="error", metrics={}, error=str(e))
```

> **Convention**: every plugin must have a corresponding `configs/base/<plugin>.yaml` file with default values. A plugin without this file receives an empty config dict and must handle missing keys gracefully using internal defaults.

### Multi-distro support in collectors

Collectors access system information via `self.config.get("_system", {})`. Differences between Linux distributions are always isolated in private helper methods, never scattered inside `collect()`. The `collect()` method remains clean and calls helpers passing the system info.

```python
class ServicesCollector(BaseCollector):

    def collect(self) -> Result:
        system      = self.config.get("_system", {})
        pkg_manager = system.get("package_manager", "unknown")

        try:
            updates = self._get_available_updates(pkg_manager)
            ...
        except Exception as e:
            return Result(name=self.name, status="error", metrics={}, error=str(e))

    def _get_available_updates(self, pkg_manager: str) -> int:
        """Return number of available updates for the current package manager."""
        if pkg_manager == "apt":
            out = run("apt list --upgradable 2>/dev/null")
            return sum(1 for l in out.splitlines() if "/" in l)
        elif pkg_manager == "dnf":
            out = run("dnf check-update --quiet 2>/dev/null")
            return len(out.splitlines())
        elif pkg_manager == "zypper":
            out = run("zypper list-updates 2>/dev/null")
            return len([l for l in out.splitlines() if "|" in l]) - 2
        else:
            return -1  # unknown package manager
```

**Rules for multi-distro collectors:**

- Always access `_system` with a fallback: `self.config.get("_system", {})`
- Isolate distro-specific logic in private methods named `_get_<thing>()`
- If a feature is not supported on the current distro, return a sentinel value (`-1` or `None`) in the metrics dict, never raise an exception or return `status='error'`
- Document which distros are supported in the method docstring
- Core collectors must always return a Result, even when distro support is missing; use `status='unavailable'` only for plugins via `is_available()`

---

## Formatter Interface

Every formatter must implement the interface defined in `formatters/base.py`.

```python
from abc import ABC, abstractmethod
from resources.base import Result

class BaseFormatter(ABC):

    delivery:  str = "body"   # "body" | "attachment"
    extension: str = ""       # file extension when delivery == "attachment"

    @abstractmethod
    def render(self, results: list[Result], hostname: str, timestamp: str, version: str) -> str:
        """
        Receive the full list of Result objects and return the formatted output
        as a string. Called once per unique format needed across all recipients.
        """
        ...
```

### Format delivery matrix

| Format | Delivery          | File extension | Purpose                                                    |
| ------ | ----------------- | -------------- | ---------------------------------------------------------- |
| `text` | body (plain text) | -              | Human-readable report for any email client                 |
| `html` | body (HTML)       | -              | Human-readable report with richer formatting               |
| `json` | attachment        | `.json`        | Full structured report for external systems or scripts     |
| `csv`  | attachment        | `.csv`         | Anomaly log with fixed columns, openable directly in Excel |

Recipients who receive an attachment always get a minimal plain text body as the email message, so the email is never empty.

### CSV format specification

The CSV formatter produces a fixed-column format regardless of which collectors are active. Its purpose is to provide a lightweight anomaly log that can be opened directly in Excel or imported into a spreadsheet without any parsing.

```
timestamp,server,version,resource,status,alerts
2026-05-17 08:00:01,vps-prod,1.0.0,CPU,ok,
2026-05-17 08:00:01,vps-prod,1.0.0,Memory,warning,RAM usage at 91%
2026-05-17 08:00:01,vps-prod,1.0.0,Disk,ok,
2026-05-17 08:00:01,vps-prod,1.0.0,Restic Snapshots,error,Latest snapshot is 30h old
```

The `alerts` column contains all alert strings for that resource joined by a pipe `|` separator. Detailed metrics are not included in the CSV. For full metric data, use the JSON format.

---

## Recipients

Each recipient has an individual format preference. The mailer determines the unique formats needed, renders each once, then sends the corresponding output to each recipient.

```yaml
# configs/base/general.yaml

recipients:
  - email: "admin@yourdomain.com"
    format: "html"
  - email: "backup@yourdomain.com"
    format: "json"
  - email: "ops@yourdomain.com"
    format: "csv"
```

---

## Execution Flow

```
cron
  │
  ▼
main.py
  │
  ├── load /opt/server-report/.env via python-dotenv
  ├── read VERSION file
  │
  ├── loader.py
  │     ├── resolve server_id: os.environ.get("SERVER_ID") or socket.gethostname()
  │     ├── merge configs/base/ with configs/<server_id>/  (YAML, lists replaced in full)
  │     ├── detect_system(): read /etc/os-release, inject as _system into config
  │     ├── scan resources/core/    (all files, safe import)
  │     ├── scan resources/plugins/ (all files present, safe import)
  │     ├── instantiate each collector passing its merged config dict
  │     ├── call is_available() on each, discard unavailable ones
  │     └── return active collectors and any load warnings
  │
  ├── collect
  │     └── call collect() on each active collector
  │           ├── enforce collector_timeout_seconds per collector
  │           └── return Result (status='error' on timeout or exception)
  │
  ├── formatters/
  │     ├── determine unique formats needed across all recipients
  │     ├── instantiate the correct formatter for each format
  │     └── render output once per unique format
  │
  └── mailer.py
        └── for each recipient send the corresponding formatted output
              ├── text/html: as email body
              └── json/csv: as attachment with minimal plain text body
```

---

## CLI Usage

```bash
# Activate the virtualenv (or use the full path below)
source /opt/server-report/.venv/bin/activate

# Send report to all configured recipients
python3 main.py

# Preview report in terminal without sending (uses text format)
python3 main.py --dry-run

# Override recipient for a one-off send
python3 main.py --to other@email.com --format html
```

When calling from cron or scripts, use the full path without activating:

```bash
/opt/server-report/.venv/bin/python /opt/server-report/main.py
```

---

## Adding a New Plugin

1. Create `resources/plugins/myplugin.py` and implement `BaseCollector`
2. Add `configs/base/myplugin.yaml` with default configuration values
3. Add any required secrets to the Ansible Vault and update the `.env` template
4. Deploy the updated repository with the Ansible update playbook

No changes to the core system are required. The loader discovers the new file automatically. All existing servers inherit the base config defaults without any changes to their own config folders.

---

## Known Operational Risks

| Risk                                                  | Mitigation                                                                                                                                           |
| ----------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Server hostname does not match `configs/` folder name | System silently falls back to base config. Ansible must set the hostname correctly at provisioning time. Verify with `--dry-run` after every deploy. |
| Plugin file has a syntax error or bad import          | Loader catches the exception and continues. A warning is included in the report.                                                                     |
| Collector hangs or runs too long                      | `collector_timeout_seconds` enforced by `loader.py`. Timed-out collectors return `status='error'`.                                                   |
| Unsupported distro for a core collector               | Collector returns sentinel value in metrics (`-1` or `None`), never crashes. Documented in method docstring.                                         |
| Cron fails silently                                   | Log every execution to `/var/log/server-report.log`. Consider `systemd timer` for built-in failure logging via `journalctl`.                         |
| Missing `configs/base/<plugin>.yaml` for a new plugin | Plugin receives empty config and must use internal defaults. Enforce this convention in the deploy checklist.                                        |
| Schedule change not deployed                          | Ansible reads `cron_schedule` from YAML and rewrites the cron. Run the update playbook after any config change.                                      |

---

## Design Decisions Log

| Decision                                               | Rationale                                                                                        |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------------------ |
| YAML for config files                                  | Native merge semantics, consistent with Ansible, clear separation between data and code          |
| PyYAML and python-dotenv as declared dependencies      | Minimal and stable, declared in `requirements.txt` with pinned versions, installed by Ansible    |
| `requirements.txt` with pinned versions                | Ensures consistent behavior across all servers regardless of environment                         |
| `socket.gethostname()` with `SERVER_ID` override       | Automatic identification in the normal case, flexibility for edge cases                          |
| Ansible reads `cron_schedule` from YAML                | Single source of truth for the schedule, no manual duplication                                   |
| Lists replaced in full on merge                        | Simple and predictable rule, no ambiguity in merge behavior                                      |
| Git + Ansible instead of Docker                        | Plugins need direct access to host resources. Minimal dependencies make Docker unnecessary.      |
| Plugin discovery from folder, no explicit registration | Adding a plugin requires no changes to the core system                                           |
| Safe import for plugins                                | A broken plugin never blocks the execution of the others                                         |
| `is_available()` before `collect()`                    | Plugins fail silently on incompatible hosts, no crashes                                          |
| `collector_timeout_seconds` enforced per collector     | A slow or hanging collector never blocks the entire report                                       |
| Config passed to collector at init, not read globally  | Plugin is self-contained and testable in isolation                                               |
| `configs/base/` + per-server override folders          | Mirrors Ansible group_vars/host_vars pattern, scales cleanly as plugins grow                     |
| One YAML file per resource in base                     | Adding a plugin adds one file, no changes to existing config files                               |
| Secrets via python-dotenv from `.env` file             | Secrets never touch the Git repository, each server has its own values                           |
| Virtualenv at `/opt/server-report/.venv`               | Isolates dependencies from system Python, avoids conflicts with distro-managed packages          |
| `VERSION` file included in every report                | Operator always knows which version is running on each server                                    |
| JSON format for full structured data                   | Preserves complete metric structure for external processing                                      |
| CSV format as fixed-column anomaly log                 | Openable directly in Excel without any parser, suited for lightweight historical tracking        |
| JSON and CSV as attachments, text and html as body     | Matches natural usage of each format in an email context                                         |
| Minimal plain text body for attachment emails          | Email is never empty, recipient always has context                                               |
| Mailgun as mail provider                               | Simple REST API, no SMTP configuration, generous free tier                                       |
| One instance per server                                | Simpler mental model, no central coordinator needed                                              |
| No real-time alerting                                  | Out of scope, dedicated tools handle this better                                                 |
| No metric history on server                            | Delegated to the recipient, keeps the system stateless                                           |
| `_system` injected by loader, not from YAML            | Single detection point, collectors receive ready-to-use info without duplicating detection logic |
| Distro differences isolated in private helper methods  | `collect()` remains clean and readable, distro-specific code is contained and easy to extend     |
| Sentinel values for unsupported features               | Core collectors always return a Result; missing support is surfaced as data, not as an error     |