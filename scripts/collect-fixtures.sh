#!/bin/bash
# =============================================================================
# scripts/collect-fixtures.sh
#
# Creates a GCP VM, provisions server-report, collects command outputs
# for test fixtures, downloads them locally, and deletes the VM.
#
# Usage:
#   bash scripts/collect-fixtures.sh [distro] [project] [zone]
#
# Arguments:
#   distro   ubuntu | debian | rocky  (default: ubuntu)
#   project  GCP project ID          (default: reads from gcloud config)
#   zone     GCP zone                (default: europe-west8-a)
#
# Examples:
#   bash scripts/collect-fixtures.sh
#   bash scripts/collect-fixtures.sh ubuntu my-project europe-west8-a
#   bash scripts/collect-fixtures.sh rocky my-project europe-west8-a
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
# Paths
# -----------------------------------------------------------------------------

VM_NAME="server-report-fixture-collector"
REPO_URL="https://github.com/biofer76/server-report"
INSTALL_PATH="/opt/server-report"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOCAL_FIXTURES="$PROJECT_DIR/tests/fixtures/$GCP_FIXTURE_DISTRO"

# -----------------------------------------------------------------------------
# Cleanup on exit
# -----------------------------------------------------------------------------

cleanup() {
    echo ""
    gcp_delete_vm "$VM_NAME" "$PROJECT" "$ZONE"
}
trap cleanup EXIT

# -----------------------------------------------------------------------------
# Create VM
# -----------------------------------------------------------------------------

echo "[INFO] Creating VM: $VM_NAME ($DISTRO)"
echo "[INFO] Project: $PROJECT | Zone: $ZONE"

gcp_create_vm "$VM_NAME" "$PROJECT" "$ZONE"
gcp_wait_for_ssh "$VM_NAME" "$PROJECT" "$ZONE"

# -----------------------------------------------------------------------------
# Provision
# -----------------------------------------------------------------------------

gcp_provision_server_report "$VM_NAME" "$PROJECT" "$ZONE" "$REPO_URL" "$INSTALL_PATH"

# -----------------------------------------------------------------------------
# Remote script to collect fixture outputs
# -----------------------------------------------------------------------------

REMOTE_SCRIPT=$(cat << 'REMOTE_EOF'
#!/bin/bash
set -euo pipefail

FIXTURE_DIR="/tmp/fixtures"
mkdir -p "$FIXTURE_DIR"/{memory,disk,cpu,network,security,services,system}

echo "[COLLECT] memory..."
free -m > "$FIXTURE_DIR/memory/free_m.txt"

# Edge case: swap line with no values (simulate missing swap)
cat > "$FIXTURE_DIR/memory/free_m_no_swap.txt" << 'EOF'
               total        used        free      shared  buff/cache   available
Mem:             955         368         425           0         314         587
Swap:
EOF

echo "[COLLECT] disk..."
df -h --output=target,size,used,avail,pcent > "$FIXTURE_DIR/disk/df_h.txt"

echo "[COLLECT] cpu..."
cat /proc/loadavg > "$FIXTURE_DIR/cpu/loadavg.txt"
nproc > "$FIXTURE_DIR/cpu/nproc.txt"
ps aux --sort=-%cpu | head -6 > "$FIXTURE_DIR/cpu/ps_aux.txt"

echo "[COLLECT] network..."
ss -s > "$FIXTURE_DIR/network/ss_s.txt"

echo "[COLLECT] security..."
last -n 5 --time-format iso > "$FIXTURE_DIR/security/last.txt"
# auth.log may not exist on a fresh VM, touch it to avoid errors
touch "$FIXTURE_DIR/security/auth_log_failed.txt"
grep "Failed password" /var/log/auth.log >> "$FIXTURE_DIR/security/auth_log_failed.txt" 2>/dev/null || true
grep "Failed password" /var/log/secure >> "$FIXTURE_DIR/security/auth_log_failed.txt" 2>/dev/null || true

echo "[COLLECT] system..."
cat /etc/os-release > "$FIXTURE_DIR/system/os_release.txt"
uname -r > "$FIXTURE_DIR/system/uname_r.txt"
uname -m > "$FIXTURE_DIR/system/uname_m.txt"
uptime -p > "$FIXTURE_DIR/system/uptime.txt"
grep "model name" /proc/cpuinfo | head -1 > "$FIXTURE_DIR/system/cpuinfo.txt"

echo "[COLLECT] services..."
systemctl --failed --no-legend --plain > "$FIXTURE_DIR/services/systemctl_failed.txt" || true

# Package manager specific
if command -v apt &>/dev/null; then
    echo "[COLLECT] apt..."
    apt list --upgradable 2>/dev/null > "$FIXTURE_DIR/services/apt_upgradable.txt" || true
    # Simulate apt with updates for testing
    cat > "$FIXTURE_DIR/services/apt_upgradable_with_updates.txt" << 'EOF'
Listing... Done
curl/noble-updates 8.5.0-2ubuntu10.6 amd64 [upgradable from: 8.5.0-2ubuntu10.5]
git/noble-updates 1:2.43.0-1ubuntu7.2 amd64 [upgradable from: 1:2.43.0-1ubuntu7.1]
openssl/noble-updates 3.0.13-0ubuntu3.5 amd64 [upgradable from: 3.0.13-0ubuntu3.4]
EOF
fi

if command -v dnf &>/dev/null; then
    echo "[COLLECT] dnf..."
    sudo dnf makecache -q
    dnf check-update --cacheonly --quiet > "$FIXTURE_DIR/services/dnf_check_update.txt" 2>/dev/null || true
    # Simulate no-updates case
    echo "" > "$FIXTURE_DIR/services/dnf_check_update_no_updates.txt"
fi

echo "[COLLECT] done. Files saved to $FIXTURE_DIR"
ls -la "$FIXTURE_DIR"/**
REMOTE_EOF
)

# -----------------------------------------------------------------------------
# Execute remote script
# -----------------------------------------------------------------------------

echo "[INFO] Running collection script on VM..."
gcp_ssh "$VM_NAME" "$PROJECT" "$ZONE" "$REMOTE_SCRIPT"

# -----------------------------------------------------------------------------
# Download fixtures
# -----------------------------------------------------------------------------

echo "[INFO] Downloading fixtures to $LOCAL_FIXTURES..."
mkdir -p "$LOCAL_FIXTURES"

gcp_scp_from "$VM_NAME" "$PROJECT" "$ZONE" "/tmp/fixtures/." "$LOCAL_FIXTURES/"

echo ""
echo "[OK] Fixtures downloaded to: $LOCAL_FIXTURES"
echo ""
echo "Files collected:"
find "$LOCAL_FIXTURES" -type f | sort | sed 's|'"$PROJECT_DIR"'/||'
