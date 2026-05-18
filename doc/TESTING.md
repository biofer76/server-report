# server-report - Testing Guide

This document describes how to set up a test environment on GCP and run the
test suite after every change. Keep it updated as new collectors and plugins
are added.

---

## 1. Create a GCP test VM

**Important:** Always verify the active GCP project before running any
`gcloud` command. Use `--project=PROJECT-ID` explicitly in every
command, or set the project for the current session with:

```bash
gcloud config set project PROJECT-ID

# verify
gcloud config get project
```

```bash
# Authenticate if needed
gcloud auth login


# Create a minimal Debian or Ubuntu VM (e2-micro is free tier eligible)
gcloud compute instances create server-report-test \
  --zone=europe-west8-a \
  --machine-type=e2-micro \
  --image-family=ubuntu-2404-lts-amd64 \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=10GB \
  --tags=server-report-test

# SSH into the VM
gcloud compute ssh server-report-test --zone=europe-west8-a
```

To test on Debian instead, replace the image flags with:

```bash
--image-family=debian-12 \
--image-project=debian-cloud
```

---

## 2. Provision the VM

Run these commands once after the VM is created.

```bash
# Update packages
sudo apt update && sudo apt upgrade -y

# Install Python 3.10+ (already present on Ubuntu 24.04 and Debian 12)
python3 --version

# Install pip if missing
sudo apt install -y python3-pip

# Install git
sudo apt install -y git

# Clone the repository
git clone https://github.com/biofer76/server-report /opt/server-report
cd /opt/server-report

# Install dependencies
pip install -r requirements.txt --break-system-packages
```

---

## 3. Minimal configuration

```bash
# Create a minimal .env file (no real Mailgun key needed for dry-run)
cat > /opt/server-report/.env << 'EOF'
MAILGUN_API_KEY=key-test-placeholder
EOF

# Verify the example config folder is present
ls configs/example/

# Optionally copy the example config as a server override
# The hostname must match the folder name under configs/
hostname
cp -r configs/example configs/$(hostname)
```

---

## 4. Smoke test (run after every change)

The dry-run test is the baseline. It must always complete without errors.

```bash
cd /opt/server-report
python3 main.py --dry-run
```

**Expected output:**

- Report printed to stdout with no Python tracebacks
- `_system` block shows `distro: ubuntu` (or `debian`) and `package_manager: apt`
- All core collectors present: CPU, Memory, Disk, Network, Services
- Optional plugins absent if not installed: Restic, Docker, Nginx shown as skipped or absent
- No `[ERROR]` lines unless a collector genuinely fails

---

## 5. Collector checklist

Run these checks individually to verify each collector works correctly.

### System detection

```bash
python3 - << 'EOF'
from loader import load_config
cfg = load_config()
print(cfg.get("_system"))
EOF
```

Expected: `{'distro': 'ubuntu', 'distro_version': '24.04', 'distro_pretty': 'Ubuntu 24.04 LTS', 'package_manager': 'apt'}`

### CPU

```bash
python3 - << 'EOF'
from loader import load_config
from resources.core.cpu import CpuCollector
cfg = load_config()
c = CpuCollector(cfg.get("cpu", {}))
print(c.is_available())
print(c.collect())
EOF
```

### Memory

```bash
python3 - << 'EOF'
from loader import load_config
from resources.core.memory import MemoryCollector
cfg = load_config()
c = MemoryCollector(cfg.get("memory", {}))
print(c.collect())
EOF
```

### Disk

```bash
python3 - << 'EOF'
from loader import load_config
from resources.core.disk import DiskCollector
cfg = load_config()
c = DiskCollector(cfg.get("disk", {}))
r = c.collect()
print(r.status, r.metrics)
EOF
```

**Watch for:** mount points with spaces, tmpfs partitions incorrectly included,
percentage parsing errors.

### Network

```bash
# Verify ss is available
which ss

python3 - << 'EOF'
from loader import load_config
from resources.core.network import NetworkCollector
cfg = load_config()
c = NetworkCollector(cfg.get("network", {}))
print(c.collect())
EOF
```

**Watch for:** `ss` missing on minimal systems. Install with `sudo apt install iproute2`.

### Services

```bash
# Verify systemctl is available
systemctl --failed --no-legend --plain

python3 - << 'EOF'
from loader import load_config
from resources.core.services import ServicesCollector
cfg = load_config()
c = ServicesCollector(cfg.get("services", {}))
r = c.collect()
print(r.status, r.metrics)
EOF
```

**Watch for:**
- `available_updates` must be an integer, not `-1` (which means unknown package manager)
- `_system.package_manager` must be `apt` on Ubuntu/Debian

### Plugins (optional, install first)

**Restic:**

```bash
# Install restic
sudo apt install -y restic

python3 - << 'EOF'
from loader import load_config
from resources.plugins.restic import ResticCollector
cfg = load_config()
c = ResticCollector(cfg.get("restic", {}))
print(c.is_available())   # must be True
print(c.collect())
EOF
```

**Docker:**

```bash
# Install docker
sudo apt install -y docker.io

python3 - << 'EOF'
from loader import load_config
from resources.plugins.docker import DockerCollector
cfg = load_config()
c = DockerCollector(cfg.get("docker", {}))
print(c.is_available())
print(c.collect())
EOF
```

**Nginx:**

```bash
sudo apt install -y nginx
sudo systemctl start nginx

python3 - << 'EOF'
from loader import load_config
from resources.plugins.nginx import NginxCollector
cfg = load_config()
c = NginxCollector(cfg.get("nginx", {}))
print(c.is_available())
print(c.collect())
EOF
```

---

## 6. Formatter checklist

Verify each formatter produces valid output.

```bash
python3 - << 'EOF'
import socket
from datetime import datetime
from loader import load_config, discover_collectors, run_collectors
from formatters.text import TextFormatter
from formatters.html import HtmlFormatter
from formatters.json import JsonFormatter
from formatters.csv import CsvFormatter

cfg        = load_config()
collectors, warnings = discover_collectors(cfg)
results    = run_collectors(collectors, cfg)
hostname   = socket.gethostname()
timestamp  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
version    = open("VERSION").read().strip()

for fmt_cls in (TextFormatter, HtmlFormatter, JsonFormatter, CsvFormatter):
    fmt = fmt_cls()
    out = fmt.render(results, hostname, timestamp, version)
    print(f"\n--- {fmt_cls.__name__} ({len(out)} chars) ---")
    print(out[:500])
EOF
```

**Expected:**
- `TextFormatter`: readable plain text, no Python objects printed raw
- `HtmlFormatter`: valid HTML starting with `<`, no tracebacks
- `JsonFormatter`: valid JSON, parseable with `json.loads()`
- `CsvFormatter`: fixed columns `timestamp,server,version,resource,status,alerts`, no metric detail

---

## 7. End-to-end test with real email

Only run this when Mailgun is configured and you want to verify the full flow.

```bash
# Set real credentials in .env
echo "MAILGUN_API_KEY=key-your-real-key" >> /opt/server-report/.env

# Send to a single address to avoid spamming all recipients
python3 main.py --to your@email.com --format html
python3 main.py --to your@email.com --format text
python3 main.py --to your@email.com --format csv
python3 main.py --to your@email.com --format json
```

**Check in the inbox:**
- `html`: report rendered directly in the email body
- `text`: plain text body, readable without any rendering
- `csv`: attachment named `server-report-<timestamp>.csv`, opens in Excel
- `json`: attachment named `server-report-<timestamp>.json`, valid JSON

---

## 8. Red Hat / CentOS compatibility test

To verify multi-distro support, create a second VM with Rocky Linux or AlmaLinux.

```bash
gcloud compute instances create server-report-test-rhel \
  --zone=europe-west8-a \
  --machine-type=e2-micro \
  --image-family=rocky-linux-9 \
  --image-project=rocky-linux-cloud \
  --boot-disk-size=10GB
```

Run the same smoke test and collector checklist. Pay attention to:

- `_system.package_manager` must be `dnf`
- `services` collector must use `dnf check-update` for available updates
- `available_updates` must be an integer, not `-1`

---

## 9. Cleanup

Delete the test VM when done to avoid unnecessary GCP costs.

```bash
gcloud compute instances delete server-report-test --zone=europe-west8-a --quiet
```

If you created the Red Hat VM:

```bash
gcloud compute instances delete server-report-test-rhel --zone=europe-west8-a --quiet
```

---

## 10. Checklist before every release

Run through this list before tagging a new version.

- [ ] `python3 main.py --dry-run` completes without errors on Ubuntu
- [ ] `python3 main.py --dry-run` completes without errors on Debian
- [ ] `_system` block is correct on both distros
- [ ] `available_updates` is an integer on both distros (not `-1`)
- [ ] All four formatters produce valid output
- [ ] CSV has fixed columns, no metric detail
- [ ] JSON is parseable with `json.loads()`
- [ ] HTML has no raw Python objects
- [ ] End-to-end email test passed for all four formats
- [ ] No hardcoded credentials, paths, or thresholds in the code
- [ ] `VERSION` file updated
- [ ] `requirements.txt` versions are still pinned and current
- [ ] Test VM deleted after testing