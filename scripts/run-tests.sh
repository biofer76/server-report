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

source "$(dirname "$0")/gcp-vm.sh"

# -----------------------------------------------------------------------------
# Arguments
# -----------------------------------------------------------------------------

DISTRO="${1:-ubuntu}"
PROJECT="${2:-$(gcloud config get project 2>/dev/null)}"
ZONE="${3:-europe-west8-a}"

gcp_require_project "$PROJECT"
gcp_load_distro_config "$DISTRO"

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

VM_NAME="server-report-test-runner"
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

# -----------------------------------------------------------------------------
# Cleanup on exit
# -----------------------------------------------------------------------------

cleanup() {
    echo ""
    gcp_delete_vm "$VM_NAME" "$PROJECT" "$ZONE"

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

gcp_create_vm "$VM_NAME" "$PROJECT" "$ZONE"
gcp_wait_for_ssh "$VM_NAME" "$PROJECT" "$ZONE"

# -----------------------------------------------------------------------------
# Provisioning
# -----------------------------------------------------------------------------

gcp_provision_server_report "$VM_NAME" "$PROJECT" "$ZONE" "$REPO_URL" "$INSTALL_PATH"

# -----------------------------------------------------------------------------
# 1. System detection
# -----------------------------------------------------------------------------

echo ""
echo "[INFO] Checking system detection..."

DETECTED_DISTRO=$(gcp_ssh "$VM_NAME" "$PROJECT" "$ZONE" "cd $INSTALL_PATH && .venv/bin/python - << 'PYEOF'
from loader import load_config
cfg = load_config()
print(cfg.get('_system', {}).get('distro', 'unknown'))
PYEOF")

DETECTED_PKG=$(gcp_ssh "$VM_NAME" "$PROJECT" "$ZONE" "cd $INSTALL_PATH && .venv/bin/python - << 'PYEOF'
from loader import load_config
cfg = load_config()
print(cfg.get('_system', {}).get('package_manager', 'unknown'))
PYEOF")

[[ "$DETECTED_DISTRO" == "$GCP_EXPECTED_DISTRO" ]] \
    && pass "_system.distro = $DETECTED_DISTRO" \
    || fail "_system.distro expected=$GCP_EXPECTED_DISTRO got=$DETECTED_DISTRO"

[[ "$DETECTED_PKG" == "$GCP_EXPECTED_PKG" ]] \
    && pass "_system.package_manager = $DETECTED_PKG" \
    || fail "_system.package_manager expected=$GCP_EXPECTED_PKG got=$DETECTED_PKG"

# -----------------------------------------------------------------------------
# 2. Dry-run
# -----------------------------------------------------------------------------

echo ""
echo "[INFO] Running dry-run..."

DRY_RUN_OUTPUT=$(gcp_ssh "$VM_NAME" "$PROJECT" "$ZONE" "cd $INSTALL_PATH && .venv/bin/python main.py --dry-run 2>&1")

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

UPDATES=$(gcp_ssh "$VM_NAME" "$PROJECT" "$ZONE" "cd $INSTALL_PATH && .venv/bin/python - << 'PYEOF'
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

LOGINS_OK=$(gcp_ssh "$VM_NAME" "$PROJECT" "$ZONE" "cd $INSTALL_PATH && .venv/bin/python - << 'PYEOF'
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

# Write the checker script to a local temp file and scp it to the VM to avoid
# heredoc escaping issues and Python 3.11 f-string nested-quote restrictions.
FORMATTER_SCRIPT=$(mktemp)
cat > "$FORMATTER_SCRIPT" << 'PYEOF'
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

csv_out = CsvFormatter().render(results, hostname, timestamp, version)
checks['csv_header'] = csv_out.splitlines()[0] == 'timestamp,server,version,resource,status,alerts'

for k, v in checks.items():
    status = 'ok' if v else 'fail'
    print(f'{k}={status}')
PYEOF

gcp_scp_to "$VM_NAME" "$PROJECT" "$ZONE" "$FORMATTER_SCRIPT" "/tmp/check_formatters.py"
rm -f "$FORMATTER_SCRIPT"

FORMATTER_RESULTS=$(gcp_ssh "$VM_NAME" "$PROJECT" "$ZONE" \
    "cd $INSTALL_PATH && PYTHONPATH=. .venv/bin/python /tmp/check_formatters.py")

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

gcp_ssh "$VM_NAME" "$PROJECT" "$ZONE" "cd $INSTALL_PATH && bash scripts/install-cron.sh" &>/dev/null

CRONTAB=$(gcp_ssh_sudo "$VM_NAME" "$PROJECT" "$ZONE" "crontab -l 2>/dev/null || true")
echo "$CRONTAB" | grep -q "main.py" \
    && pass "install-cron.sh writes cron entry" \
    || fail "install-cron.sh did not write cron entry"

gcp_ssh "$VM_NAME" "$PROJECT" "$ZONE" "cd $INSTALL_PATH && bash scripts/remove-cron.sh" &>/dev/null

CRONTAB_AFTER=$(gcp_ssh_sudo "$VM_NAME" "$PROJECT" "$ZONE" "crontab -l 2>/dev/null || true")
echo "$CRONTAB_AFTER" | grep -qv "main.py" \
    && pass "remove-cron.sh removes cron entry" \
    || fail "remove-cron.sh did not remove cron entry"

# Run install-cron.sh twice to verify no duplicate entries
gcp_ssh "$VM_NAME" "$PROJECT" "$ZONE" "cd $INSTALL_PATH && bash scripts/install-cron.sh" &>/dev/null
gcp_ssh "$VM_NAME" "$PROJECT" "$ZONE" "cd $INSTALL_PATH && bash scripts/install-cron.sh" &>/dev/null

CRONTAB_DUPES=$(gcp_ssh_sudo "$VM_NAME" "$PROJECT" "$ZONE" "crontab -l 2>/dev/null | grep -c 'main.py' || true")
[[ "$CRONTAB_DUPES" == "1" ]] \
    && pass "install-cron.sh does not create duplicate entries" \
    || fail "install-cron.sh created $CRONTAB_DUPES duplicate entries"

echo ""
echo "[INFO] All checks complete."
