# server-report - Testing Guide

This document describes how to run the test suite for `server-report`.
There are two levels of testing:

- **Unit tests** (`pytest`): fast, run locally, no VM required
- **Integration tests** (`scripts/run-tests.sh`): run on a real GCP VM, test the full system end-to-end

Run unit tests first. Run integration tests before every release.

---

## 1. Prerequisites

**Local machine:**
- Python 3.10+
- `gcloud` CLI authenticated and configured
- A GCP project with billing enabled

**Always verify the active GCP project before running any `gcloud` command:**

```bash
gcloud config set project PROJECT-ID
gcloud config get project
```

**Install local dependencies:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 2. Unit tests

Unit tests run locally with no VM and no GCP costs. They use fixture
files in `tests/fixtures/` collected from real systems.

```bash
source .venv/bin/activate
pytest tests/ -v
```

**What is tested:**
- `test_memory.py`: RAM parsing, swap absent or zero, alert threshold
- `test_disk.py`: mount point exclusions, partition parsing, alert threshold
- `test_security.py`: wtmp line filtering, empty line filtering, SSH attempt count
- `test_services.py`: apt update count, dnf update count (exit code 100), unknown package manager
- `test_system.py`: os-release parsing for Ubuntu/Debian/Rocky, missing file fallback
- `test_loader.py`: three-level config merge, list replacement, `_system` injection
- `test_install_cron.py`: `--install-cron` requires root

**Expected output:**

```
27 passed in 0.8s
```

---

## 3. Collecting fixtures

Fixtures are real command outputs collected from GCP VMs. They are
versioned in `tests/fixtures/` and should be refreshed when a new
distro version is added or when a collector changes its command.

```bash
chmod +x scripts/collect-fixtures.sh

bash scripts/collect-fixtures.sh ubuntu PROJECT-ID europe-west8-a
bash scripts/collect-fixtures.sh debian PROJECT-ID europe-west8-a
bash scripts/collect-fixtures.sh rocky PROJECT-ID europe-west8-a
```

The script creates and deletes the VM automatically. Collected files
are saved to `tests/fixtures/<distro>/`.

After collecting, commit the updated fixtures:

```bash
git add tests/fixtures/
git commit -m "test(fixtures): refresh fixtures for <distro>"
```

---

## 4. Integration tests

Integration tests create a real GCP VM, provision `server-report`,
run all checks and report pass/fail for each one. The VM is deleted
automatically on exit.

```bash
chmod +x scripts/run-tests.sh

bash scripts/run-tests.sh ubuntu PROJECT-ID europe-west8-a
bash scripts/run-tests.sh debian PROJECT-ID europe-west8-a
bash scripts/run-tests.sh rocky PROJECT-ID europe-west8-a
```

**What is checked:**

| Check                                                               | Description                             |
| ------------------------------------------------------------------- | --------------------------------------- |
| `_system.distro`                                                    | Correct distro detected                 |
| `_system.package_manager`                                           | `apt` on Ubuntu/Debian, `dnf` on Rocky  |
| dry-run produces report                                             | No crash, output contains SERVER REPORT |
| dry-run no tracebacks                                               | No Python exceptions in output          |
| collector present: System/CPU/Disk/Memory/Network/Security/Services | All 7 core collectors appear            |
| collector no error: (each)                                          | No collector in ERROR state             |
| available_updates is integer                                        | Not `-1` (unknown package manager)      |
| recent_logins no empty lines or wtmp                                | Security collector filters correctly    |
| formatter: text_no_traceback                                        | Text formatter produces clean output    |
| formatter: html_starts_with_tag                                     | HTML formatter produces valid HTML      |
| formatter: json_parseable                                           | JSON formatter produces valid JSON      |
| formatter: csv_header                                               | CSV has correct fixed columns           |
| install-cron.sh writes cron entry                                   | Cron entry added to root crontab        |
| remove-cron.sh removes cron entry                                   | Cron entry removed from root crontab    |
| install-cron.sh no duplicate entries                                | Running twice does not add duplicates   |

**Expected output:**

```
============================================================
  RESULTS: ubuntu
============================================================
  PASSED: 27
  FAILED: 0
============================================================
```

Exit code is `0` if all checks pass, `1` if any check fails.

---

## 5. Manual VM setup (debug only)

Use this section only when debugging a specific issue that the
automated scripts do not surface. For routine testing use
`run-tests.sh` instead.

### Create VM

```bash
# Ubuntu 24.04
gcloud compute instances create server-report-test \
  --zone=europe-west8-a \
  --project=PROJECT-ID \
  --machine-type=e2-micro \
  --image-family=ubuntu-2404-lts-amd64 \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=10GB

# Debian 12
gcloud compute instances create server-report-test \
  --zone=europe-west8-a \
  --project=PROJECT-ID \
  --machine-type=e2-micro \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --boot-disk-size=10GB

# Rocky Linux 9 (use e2-medium and 20GB)
gcloud compute instances create server-report-test \
  --zone=europe-west8-a \
  --project=PROJECT-ID \
  --machine-type=e2-medium \
  --image-family=rocky-linux-9 \
  --image-project=rocky-linux-cloud \
  --boot-disk-size=20GB

gcloud compute ssh server-report-test --zone=europe-west8-a --project=PROJECT-ID
```

### Provision (Ubuntu / Debian)

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip git

# Ubuntu 24.04
sudo apt install -y python3.12-venv

# Debian 12
sudo apt install -y python3.11-venv

sudo git clone https://github.com/biofer76/server-report /opt/server-report
sudo chown -R $USER:$USER /opt/server-report
cd /opt/server-report
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Provision (Rocky Linux 9)

```bash
# Rocky Linux 9 ships with Python 3.9 - install 3.11 explicitly
sudo dnf install -y python3.11 git

sudo git clone https://github.com/biofer76/server-report /opt/server-report
sudo chown -R $USER:$USER /opt/server-report
cd /opt/server-report
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Minimal configuration

```bash
cat > /opt/server-report/.env << 'EOF'
MAILGUN_API_KEY=key-test-placeholder
EOF

mkdir -p configs/shared
cat > configs/shared/general.yaml << 'EOF'
mailgun_domain:  "yourdomain.com"
mailgun_api_url: "https://api.eu.mailgun.net/v3"

recipients:
  - email: "you@yourdomain.com"
    format: "html"
EOF

cp -r configs/example configs/$(hostname)
```

### Smoke test

```bash
cd /opt/server-report
source .venv/bin/activate
python3 main.py --dry-run
```

**Expected output:**
- No Python tracebacks
- All 7 core collectors present: System, CPU, Disk, Memory, Network, Security, Services
- No `[ERROR]` lines
- `_system` shows correct distro and package manager

### System detection check

```bash
python3 - << 'EOF'
from loader import load_config
cfg = load_config()
print(cfg.get("_system"))
EOF
```

Expected on Ubuntu: `{'distro': 'ubuntu', 'distro_version': '24.04', 'distro_pretty': 'Ubuntu 24.04 LTS', 'package_manager': 'apt'}`

Expected on Debian: `{'distro': 'debian', 'distro_version': '12', 'distro_pretty': 'Debian GNU/Linux 12 (bookworm)', 'package_manager': 'apt'}`

Expected on Rocky Linux: `{'distro': 'rocky', 'distro_version': '9.x', 'distro_pretty': 'Rocky Linux 9.x (Blue Onyx)', 'package_manager': 'dnf'}`

### Cron setup test

```bash
# Install
bash scripts/install-cron.sh
sudo crontab -l
# Expected: line containing main.py with the correct schedule

# Remove
bash scripts/remove-cron.sh
sudo crontab -l
# Expected: no line referencing main.py

# Verify no duplicates
bash scripts/install-cron.sh
bash scripts/install-cron.sh
sudo crontab -l | grep -c "main.py"
# Expected: 1
```

### End-to-end email test

```bash
echo "MAILGUN_API_KEY=key-your-real-key" >> /opt/server-report/.env
source /opt/server-report/.venv/bin/activate

python3 main.py --to your@email.com --format html
python3 main.py --to your@email.com --format text
python3 main.py --to your@email.com --format csv
python3 main.py --to your@email.com --format json
```

**Check in the inbox:**
- `html`: report rendered directly in the email body
- `text`: plain text body
- `csv`: attachment `.csv`, opens in Excel
- `json`: attachment `.json`, valid JSON

### Cleanup

```bash
gcloud compute instances delete server-report-test \
  --zone=europe-west8-a \
  --project=PROJECT-ID \
  --quiet
```

---

## 6. Release checklist

Run through this list before tagging a new version.

**Unit tests**
- [ ] `pytest tests/ -v` passes with 0 failures

**Integration tests**
- [ ] `run-tests.sh ubuntu` passes with 0 failures
- [ ] `run-tests.sh debian` passes with 0 failures
- [ ] `run-tests.sh rocky` passes with 0 failures

**Manual verification**
- [ ] End-to-end email test passed for all four formats
- [ ] Log at `/var/log/server-report.log` shows structured `send OK` lines only

**Code quality**
- [ ] No hardcoded credentials, paths, or thresholds in the code
- [ ] `VERSION` file updated
- [ ] `requirements.txt` versions are still pinned and current
- [ ] All GCP test VMs deleted