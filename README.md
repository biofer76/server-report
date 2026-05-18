# server-report

A lightweight, extensible server monitoring system that collects system metrics and delivers periodic status reports via email. Designed for Linux servers, it adapts to different environments through a plugin system.

## Features

- **System info**: distro, kernel, architecture, uptime, CPU model
- **CPU**: usage, load average, top processes
- **Memory**: RAM and swap usage with configurable thresholds
- **Disk**: usage per partition, configurable exclude list
- **Network**: TCP connection summary
- **Security**: recent SSH logins, failed login attempts
- **Services**: failed systemd services, available package updates
- **Plugin system**: extend with custom collectors (Restic, Docker, Nginx, and more)
- **Multiple output formats**: plain text, HTML, JSON, CSV
- **Per-recipient format**: each recipient receives the report in their preferred format
- **Multi-distro**: tested on Ubuntu 24.04, Debian 12, Rocky Linux 9
- `--dry-run` mode for previewing the report without sending

## Project structure

```
server-report/
├── main.py                  # entry point, CLI arguments
├── loader.py                # config merge, plugin discovery, collector init
├── mailer.py                # email sending via Mailgun
├── formatters/
│   ├── text.py              # plain text (email body)
│   ├── html.py              # HTML (email body)
│   ├── json.py              # full structured report (attachment)
│   └── csv.py               # anomaly log with fixed columns (attachment)
├── resources/
│   ├── core/                # standard collectors, always active
│   │   ├── system.py
│   │   ├── cpu.py
│   │   ├── memory.py
│   │   ├── disk.py
│   │   ├── network.py
│   │   ├── security.py
│   │   └── services.py
│   └── plugins/             # optional collectors, loaded if file is present
│       ├── restic.py
│       ├── docker.py
│       └── nginx.py
└── configs/
    ├── base/                # default values, versioned in Git
    ├── shared/              # values common to all servers, not versioned
    └── <hostname>/          # per-server overrides, not versioned
```

## Requirements

- Python 3.10+ (Python 3.11+ on Rocky Linux / RHEL)
- Linux (Ubuntu 24.04, Debian 12, Rocky Linux 9 tested)
- A [Mailgun](https://www.mailgun.com) account with a verified sending domain

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/biofer76/server-report.git /opt/server-report
cd /opt/server-report
```

### 2. Create the virtualenv and install dependencies

```bash
# Ubuntu 24.04
sudo apt install -y python3.12-venv
python3 -m venv .venv

# Debian 12
sudo apt install -y python3.11-venv
python3 -m venv .venv

# Rocky Linux 9
sudo dnf install -y python3.11
python3.11 -m venv .venv

# All distros
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure secrets

Create a `.env` file with your Mailgun credentials:

```bash
cat > /opt/server-report/.env << 'ENVEOF'
MAILGUN_API_KEY=key-your-api-key-here
ENVEOF
```

### 4. Configure shared settings

Create `configs/shared/general.yaml` with the values common to all your servers:

```yaml
mailgun_domain:  "mg.yourdomain.com"
mailgun_api_url: "https://api.eu.mailgun.net/v3"  # or api.mailgun.net for US

recipients:
  - email: "admin@yourdomain.com"
    format: "html"
```

### 5. Configure per-server overrides (optional)

Create `configs/<hostname>/general.yaml` to override any value for a specific server:

```yaml
# Override the schedule or recipients for this server only
cron_schedule: "0 7 * * *"
```

### 6. Test

```bash
source .venv/bin/activate
python3 main.py --dry-run
```

### 7. Schedule with cron

```bash
crontab -e
```

Add the following line (the schedule is also configurable in `configs/base/general.yaml`):

```
0 8 * * * /opt/server-report/.venv/bin/python /opt/server-report/main.py >> /var/log/server-report.log 2>&1
```

## Usage

```bash
# Preview report in terminal (no email sent)
python3 main.py --dry-run

# Send report to all configured recipients
python3 main.py

# Send to a specific address with a specific format
python3 main.py --to other@email.com --format html
```

## Output formats

| Format | Delivery   | Description                                       |
| ------ | ---------- | ------------------------------------------------- |
| `text` | Email body | Plain text, readable on any client                |
| `html` | Email body | Formatted report with color-coded status badges   |
| `json` | Attachment | Full structured data for external processing      |
| `csv`  | Attachment | Fixed-column anomaly log, opens directly in Excel |

## Configuration

The configuration system uses three layers, merged in order:

1. `configs/base/` — generic defaults, versioned in Git
2. `configs/shared/` — values common to all your servers, not versioned
3. `configs/<hostname>/` — per-server overrides, not versioned

Each layer contains one YAML file per resource (e.g. `general.yaml`, `disk.yaml`, `memory.yaml`). Only the keys that differ from the layer below need to be specified.

## Adding a plugin

1. Create `resources/plugins/myplugin.py` implementing `BaseCollector`
2. Add `configs/base/myplugin.yaml` with default configuration values
3. The loader discovers the new file automatically — no other changes needed

See `resources/base.py` for the `BaseCollector` interface and `resources/plugins/restic.py` for a complete example.

## Deployment

`server-report` is a self-contained Python application with no mandatory deployment tooling. Any tool that can clone a Git repository, write files, and set up a cron job works.

An official Ansible integration is available as a separate repository: [server-report-ansible](https://github.com/biofer76/server-report-ansible).

## License

[MIT](LICENSE)