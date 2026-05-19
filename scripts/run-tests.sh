#!/bin/bash
# =============================================================================
# scripts/run-tests.sh
#
# Creates a GCP VM, provisions server-report, runs all integration checks
# and reports pass/fail for each one. Deletes the VM on exit.
#
# Usage:
#   bash scripts/run-tests.sh [distro] [project] [zone]
#
# Arguments:
#   distro   ubuntu | debian | rocky  (default: ubuntu)
#   project  GCP project ID          (default: reads from gcloud config)
#   zone     GCP zone                (default: europe-west8-a)
#
# Examples:
#   bash scripts/run-tests.sh
#   bash scripts/run-tests.sh ubuntu my-project europe-west8-a
#   bash scripts/run-tests.sh rocky my-project europe-west8-a
#
# Exit code:
#   0 - all checks passed
#   1 - one or more checks failed
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Arguments
# -----------------------------------------------------------------------------

DISTRO="${1:-ubuntu}"
PROJECT="${2:-$(gcloud config get project 2>/dev/null)}"
ZONE="${3:-europe-west8-a}"

if [[ -z "$PROJECT" ]]; then
    echo "[ERROR] No GCP project specified and no default project set."
    echo "        Run: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

# -----------------------------------------------------------------------------
# Distro configuration
# -----------------------------------------------------------------------------

case "$DISTRO" in
    ubuntu)
        IMAGE_FAMILY="ubuntu-2404-lts-amd64"
        IMAGE_PROJECT="ubuntu-os-cloud"
        MACHINE_TYPE="e2-micro"
        DISK_SIZE="10GB"
        FIXTURE_DISTRO="ubuntu-24.04"
        EXPECTED_DISTRO="ubuntu"
        EXPECTED_PKG_MANAGER="apt"
        PROVISION_CMD="sudo apt-get update -qq && sudo apt-get install -y -qq git python3-pip python3.12-venv"
        VENV_PYTHON="python3"
        ;;
    debian)
        IMAGE_FAMILY="debian-12"
        IMAGE_PROJECT="debian-cloud"
        MACHINE_TYPE="e2-micro"
        DISK_SIZE="10GB"
        FIXTURE_DISTRO="debian-12"
        EXPECTED_DISTRO="debian"
        EXPECTED_PKG_MANAGER="apt"
        PROVISION_CMD="sudo apt-get update -qq && sudo apt-get install -y -qq git python3-pip python3.11-venv"
        VENV_PYTHON="python3"
        ;;
    rocky)
        IMAGE_FAMILY="rocky-linux-9"
        IMAGE_PROJECT="rocky-linux-cloud"
        MACHINE_TYPE="e2-medium"
        DISK_SIZE="20GB"
        FIXTURE_DISTRO="rocky-9"
        EXPECTED_DISTRO="rocky"
        EXPECTED_PKG_MANAGER="dnf"
        PROVISION_CMD="sudo dnf install -y -q git python3.11"
        VENV_PYTHON="python3.11"
        ;;
    *)
        echo "[ERROR] Unknown distro: $DISTRO. Use: ubuntu | debian | rocky"
        exit 1
        ;;
esac

VM_NAME="server-report-test-runner"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
REPO_URL="https://github.com/biofer76/server-report"
INSTALL_PATH="/opt/server-report"
PASS=0
FAIL=0

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

pass() {
    echo "[PASS] $1"
    PASS=$((PASS + 1))
}

fail() {
    echo "[FAIL] $1"
    FAIL=$((FAIL + 1))
}

ssh_run() {
    gcloud compute ssh "$VM_NAME" \
        --zone="$ZONE" \
        --project="$PROJECT" \
        --command="$1" \
        --strict-host-key-checking=no \
        --quiet 2>/dev/null
}

ssh_run_sudo() {
    ssh_run "sudo bash -c '$1'"
}

# -----------------------------------------------------------------------------
# Cleanup on exit
# -----------------------------------------------------------------------------

cleanup() {
    echo ""
    echo "[INFO] Cleaning up VM..."
    gcloud compute instances delete "$VM_NAME" \
        --zone="$ZONE" \
        --project="$PROJECT" \
        --quiet 2>/dev/null || true
    echo "[OK] VM deleted"

    echo ""
    echo "============================================================"
    echo "  RESULTS: $DISTRO"
    echo "============================================================"
    echo "  PASSED: $PASS"
    echo "  FAILED: $FAIL"
    echo "============================================================"

    if [[ $FAIL -gt 0 ]]; then
        exit 1
    fi
}
trap cleanup EXIT

# -----------------------------------------------------------------------------
# Create VM
# -----------------------------------------------------------------------------

echo "============================================================"
echo "  server-report integration tests"
echo "  Distro:  $DISTRO"
echo "  Project: $PROJECT"
echo "  Zone:    $ZONE"
echo "============================================================"
echo ""
echo "[INFO] Creating VM: $VM_NAME"

gcloud compute instances create "$VM_NAME" \
    --zone="$ZONE" \
    --project="$PROJECT" \
    --machine-type="$MACHINE_TYPE" \
    --image-family="$IMAGE_FAMILY" \
    --image-project="$IMAGE_PROJECT" \
    --boot-disk-size="$DISK_SIZE" \
    --quiet

# Wait for SSH
echo "[INFO] Waiting for SSH..."
MAX_WAIT=120
WAITED=0
until ssh_run "echo ready" &>/dev/null; do
    if [[ $WAITED -ge $MAX_WAIT ]]; then
        echo "[ERROR] VM not reachable after ${MAX_WAIT}s"
        exit 1
    fi
    sleep 10
    WAITED=$((WAITED + 10))
done
echo "[OK] VM is ready"

# -----------------------------------------------------------------------------
# Provisioning
# -----------------------------------------------------------------------------

echo ""
echo "[INFO] Provisioning..."

ssh_run "$PROVISION_CMD"
ssh_run "sudo git clone $REPO_URL $INSTALL_PATH"
ssh_run "sudo chown -R \$USER:\$USER $INSTALL_PATH"
ssh_run "cd $INSTALL_PATH && $VENV_PYTHON -m venv .venv && .venv/bin/pip install -q -r requirements.txt"

# Minimal config
ssh_run "cat > $INSTALL_PATH/.env << 'EOF'
MAILGUN_API_KEY=key-test-placeholder
EOF"

ssh_run "mkdir -p $INSTALL_PATH/configs/shared && cat > $INSTALL_PATH/configs/shared/general.yaml << 'EOF'
mailgun_domain: \"mg.example.com\"
mailgun_api_url: \"https://api.eu.mailgun.net/v3\"
recipients:
  - email: \"test@example.com\"
    format: \"html\"
EOF"

ssh_run "cp -r $INSTALL_PATH/configs/example $INSTALL_PATH/configs/\$(hostname)"

echo "[OK] Provisioning complete"

# -----------------------------------------------------------------------------
# 1. System detection
# -----------------------------------------------------------------------------

echo ""
echo "[INFO] Checking system detection..."

DETECTED_DISTRO=$(ssh_run "cd $INSTALL_PATH && .venv/bin/python - << 'PYEOF'
from loader import load_config
cfg = load_config()
print(cfg.get('_system', {}).get('distro', 'unknown'))
PYEOF")

DETECTED_PKG=$(ssh_run "cd $INSTALL_PATH && .venv/bin/python - << 'PYEOF'
from loader import load_config
cfg = load_config()
print(cfg.get('_system', {}).get('package_manager', 'unknown'))
PYEOF")

[[ "$DETECTED_DISTRO" == "$EXPECTED_DISTRO" ]] \
    && pass "_system.distro = $DETECTED_DISTRO" \
    || fail "_system.distro expected=$EXPECTED_DISTRO got=$DETECTED_DISTRO"

[[ "$DETECTED_PKG" == "$EXPECTED_PKG_MANAGER" ]] \
    && pass "_system.package_manager = $DETECTED_PKG" \
    || fail "_system.package_manager expected=$EXPECTED_PKG_MANAGER got=$DETECTED_PKG"

# -----------------------------------------------------------------------------
# 2. Dry-run
# -----------------------------------------------------------------------------

echo ""
echo "[INFO] Running dry-run..."

DRY_RUN_OUTPUT=$(ssh_run "cd $INSTALL_PATH && .venv/bin/python main.py --dry-run 2>&1")

echo "$DRY_RUN_OUTPUT" | grep -q "SERVER REPORT" \
    && pass "dry-run produces report" \
    || fail "dry-run did not produce report"

echo "$DRY_RUN_OUTPUT" | grep -qv "Traceback" \
    && pass "dry-run no Python tracebacks" \
    || fail "dry-run has Python tracebacks"

# -----------------------------------------------------------------------------
# 3. Core collectors
# -----------------------------------------------------------------------------

echo ""
echo "[INFO] Checking core collectors..."

for COLLECTOR in System CPU Disk Memory Network Security Services; do
    echo "$DRY_RUN_OUTPUT" | grep -q "$COLLECTOR  \[" \
        && pass "collector present: $COLLECTOR" \
        || fail "collector missing: $COLLECTOR"

    echo "$DRY_RUN_OUTPUT" | grep "$COLLECTOR  \[" | grep -qv "ERROR" \
        && pass "collector no error: $COLLECTOR" \
        || fail "collector in ERROR state: $COLLECTOR"
done

# -----------------------------------------------------------------------------
# 4. available_updates
# -----------------------------------------------------------------------------

echo ""
echo "[INFO] Checking available_updates..."

UPDATES=$(ssh_run "cd $INSTALL_PATH && .venv/bin/python - << 'PYEOF'
from loader import load_config
from resources.core.services import ServicesCollector
cfg = load_config()
c = ServicesCollector(cfg.get('services', {}))
r = c.collect()
print(r.metrics.get('available_updates', 'missing'))
PYEOF")

[[ "$UPDATES" =~ ^[0-9]+$ ]] \
    && pass "available_updates is integer: $UPDATES" \
    || fail "available_updates is not integer: $UPDATES"

# -----------------------------------------------------------------------------
# 5. recent_logins
# -----------------------------------------------------------------------------

echo ""
echo "[INFO] Checking recent_logins..."

LOGINS_OK=$(ssh_run "cd $INSTALL_PATH && .venv/bin/python - << 'PYEOF'
from loader import load_config
from resources.core.security import SecurityCollector
cfg = load_config()
c = SecurityCollector(cfg.get('security', {}))
r = c.collect()
logins = r.metrics.get('recent_logins', [])
has_empty = any(l.strip() == '' for l in logins)
has_wtmp = any('wtmp begins' in l for l in logins)
print('ok' if not has_empty and not has_wtmp else 'fail')
PYEOF")

[[ "$LOGINS_OK" == "ok" ]] \
    && pass "recent_logins no empty lines or wtmp" \
    || fail "recent_logins contains empty lines or wtmp begins"

# -----------------------------------------------------------------------------
# 6. Formatters
# -----------------------------------------------------------------------------

echo ""
echo "[INFO] Checking formatters..."

FORMATTER_RESULTS=$(ssh_run "cd $INSTALL_PATH && .venv/bin/python - << 'PYEOF'
import json, socket
from datetime import datetime
from loader import load_config, discover_collectors, run_collectors
from formatters.text import TextFormatter
from formatters.html import HtmlFormatter
from formatters.json import JsonFormatter
from formatters.csv import CsvFormatter

cfg = load_config()
collectors, _ = discover_collectors(cfg)
results = run_collectors(collectors, cfg)
hostname = socket.gethostname()
timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
version = open('VERSION').read().strip()

checks = {}

text = TextFormatter().render(results, hostname, timestamp, version)
checks['text_no_traceback'] = 'Traceback' not in text

html = HtmlFormatter().render(results, hostname, timestamp, version)
checks['html_starts_with_tag'] = html.strip().startswith('<')

j = JsonFormatter().render(results, hostname, timestamp, version)
try:
    json.loads(j)
    checks['json_parseable'] = True
except Exception:
    checks['json_parseable'] = False

csv = CsvFormatter().render(results, hostname, timestamp, version)
checks['csv_header'] = csv.splitlines()[0] == 'timestamp,server,version,resource,status,alerts'

for k, v in checks.items():
    print(f'{k}={'ok' if v else 'fail'}')
PYEOF")

while IFS='=' read -r key value || [[ -n "$key" ]]; do
    [[ "$value" == "ok" ]] \
        && pass "formatter: $key" \
        || fail "formatter: $key"
done <<< "$FORMATTER_RESULTS"

# -----------------------------------------------------------------------------
# 7. Cron scripts
# -----------------------------------------------------------------------------

echo ""
echo "[INFO] Checking cron scripts..."

ssh_run "cd $INSTALL_PATH && bash scripts/install-cron.sh" &>/dev/null

CRONTAB=$(ssh_run_sudo "crontab -l 2>/dev/null || true")
echo "$CRONTAB" | grep -q "main.py" \
    && pass "install-cron.sh writes cron entry" \
    || fail "install-cron.sh did not write cron entry"

ssh_run "cd $INSTALL_PATH && bash scripts/remove-cron.sh" &>/dev/null

CRONTAB_AFTER=$(ssh_run_sudo "crontab -l 2>/dev/null || true")
echo "$CRONTAB_AFTER" | grep -qv "main.py" \
    && pass "remove-cron.sh removes cron entry" \
    || fail "remove-cron.sh did not remove cron entry"

# Run install-cron.sh twice to verify no duplicate entries
ssh_run "cd $INSTALL_PATH && bash scripts/install-cron.sh" &>/dev/null
ssh_run "cd $INSTALL_PATH && bash scripts/install-cron.sh" &>/dev/null

CRONTAB_DUPES=$(ssh_run_sudo "crontab -l 2>/dev/null | grep -c 'main.py' || true")
[[ "$CRONTAB_DUPES" == "1" ]] \
    && pass "install-cron.sh does not create duplicate entries" \
    || fail "install-cron.sh created $CRONTAB_DUPES duplicate entries"

echo ""
echo "[INFO] All checks complete."