#!/bin/bash
# =============================================================================
# scripts/gcp-vm.sh
#
# Shared GCP VM management library. Source this file from other scripts:
#
#   source "$(dirname "$0")/gcp-vm.sh"
#
# After sourcing, call gcp_load_distro_config "$DISTRO" to populate
# all distro-specific variables, then use the provided functions.
#
# Variables populated by gcp_load_distro_config:
#   GCP_IMAGE_FAMILY       GCP image family name
#   GCP_IMAGE_PROJECT      GCP image project
#   GCP_MACHINE_TYPE       GCP machine type (e.g. e2-micro)
#   GCP_DISK_SIZE          Boot disk size (e.g. 10GB)
#   GCP_FIXTURE_DISTRO     Fixture directory name (e.g. ubuntu-24.04)
#   GCP_EXPECTED_DISTRO    Expected _system.distro value
#   GCP_EXPECTED_PKG       Expected _system.package_manager value
#   GCP_PROVISION_CMD      Command to install Python and git
#   GCP_VENV_PYTHON        Python binary to use for venv creation
# =============================================================================

# -----------------------------------------------------------------------------
# Distro configuration registry
# -----------------------------------------------------------------------------

gcp_load_distro_config() {
    local distro="${1:-ubuntu}"

    case "$distro" in
        ubuntu)
            GCP_IMAGE_FAMILY="ubuntu-2404-lts-amd64"
            GCP_IMAGE_PROJECT="ubuntu-os-cloud"
            GCP_MACHINE_TYPE="e2-micro"
            GCP_DISK_SIZE="10GB"
            GCP_FIXTURE_DISTRO="ubuntu-24.04"
            GCP_EXPECTED_DISTRO="ubuntu"
            GCP_EXPECTED_PKG="apt"
            GCP_PROVISION_CMD="sudo apt-get update -qq && sudo apt-get install -y -qq git python3-pip python3.12-venv"
            GCP_VENV_PYTHON="python3"
            ;;
        debian)
            GCP_IMAGE_FAMILY="debian-12"
            GCP_IMAGE_PROJECT="debian-cloud"
            GCP_MACHINE_TYPE="e2-micro"
            GCP_DISK_SIZE="10GB"
            GCP_FIXTURE_DISTRO="debian-12"
            GCP_EXPECTED_DISTRO="debian"
            GCP_EXPECTED_PKG="apt"
            GCP_PROVISION_CMD="sudo apt-get update -qq && sudo apt-get install -y -qq git python3-pip python3.11-venv"
            GCP_VENV_PYTHON="python3"
            ;;
        rocky)
            GCP_IMAGE_FAMILY="rocky-linux-9"
            GCP_IMAGE_PROJECT="rocky-linux-cloud"
            GCP_MACHINE_TYPE="e2-medium"
            GCP_DISK_SIZE="20GB"
            GCP_FIXTURE_DISTRO="rocky-9"
            GCP_EXPECTED_DISTRO="rocky"
            GCP_EXPECTED_PKG="dnf"
            GCP_PROVISION_CMD="sudo dnf install -y -q git python3.11"
            GCP_VENV_PYTHON="python3.11"
            ;;
        *)
            echo "[ERROR] Unknown distro: $distro. Use: ubuntu | debian | rocky"
            return 1
            ;;
    esac
}

# -----------------------------------------------------------------------------
# VM lifecycle
# -----------------------------------------------------------------------------

# gcp_create_vm VM_NAME PROJECT ZONE
# Creates a GCP VM using the variables set by gcp_load_distro_config.
# Must be called after gcp_load_distro_config.
gcp_create_vm() {
    local vm_name="$1"
    local project="$2"
    local zone="$3"

    echo "[INFO] Creating VM: $vm_name ($GCP_MACHINE_TYPE, $GCP_DISK_SIZE)"

    gcloud compute instances create "$vm_name" \
        --zone="$zone" \
        --project="$project" \
        --machine-type="$GCP_MACHINE_TYPE" \
        --image-family="$GCP_IMAGE_FAMILY" \
        --image-project="$GCP_IMAGE_PROJECT" \
        --boot-disk-size="$GCP_DISK_SIZE" \
        --quiet
}

# gcp_delete_vm VM_NAME PROJECT ZONE
# Deletes a GCP VM. Does not fail if the VM does not exist.
gcp_delete_vm() {
    local vm_name="$1"
    local project="$2"
    local zone="$3"

    echo "[INFO] Deleting VM: $vm_name"
    gcloud compute instances delete "$vm_name" \
        --zone="$zone" \
        --project="$project" \
        --quiet 2>/dev/null || true
    echo "[OK] VM deleted"
}

# -----------------------------------------------------------------------------
# SSH and file transfer
# -----------------------------------------------------------------------------

# gcp_ssh VM_NAME PROJECT ZONE CMD
# Runs CMD on the remote VM via gcloud compute ssh.
gcp_ssh() {
    local vm_name="$1"
    local project="$2"
    local zone="$3"
    local cmd="$4"

    gcloud compute ssh "$vm_name" \
        --zone="$zone" \
        --project="$project" \
        --command="$cmd" \
        --strict-host-key-checking=no \
        --quiet 2>/dev/null
}

# gcp_ssh_sudo VM_NAME PROJECT ZONE CMD
# Runs CMD as root on the remote VM.
gcp_ssh_sudo() {
    local vm_name="$1"
    local project="$2"
    local zone="$3"
    local cmd="$4"

    gcp_ssh "$vm_name" "$project" "$zone" "sudo bash -c '$cmd'"
}

# gcp_scp_to VM_NAME PROJECT ZONE LOCAL_PATH REMOTE_PATH
# Copies a local file or directory to the remote VM.
gcp_scp_to() {
    local vm_name="$1"
    local project="$2"
    local zone="$3"
    local local_path="$4"
    local remote_path="$5"

    gcloud compute scp \
        --recurse \
        --zone="$zone" \
        --project="$project" \
        --strict-host-key-checking=no \
        --quiet \
        "$local_path" \
        "$vm_name:$remote_path" 2>/dev/null
}

# gcp_scp_from VM_NAME PROJECT ZONE REMOTE_PATH LOCAL_PATH
# Downloads a file or directory from the remote VM.
gcp_scp_from() {
    local vm_name="$1"
    local project="$2"
    local zone="$3"
    local remote_path="$4"
    local local_path="$5"

    gcloud compute scp \
        --recurse \
        --zone="$zone" \
        --project="$project" \
        --strict-host-key-checking=no \
        --quiet \
        "$vm_name:$remote_path" \
        "$local_path" 2>/dev/null
}

# -----------------------------------------------------------------------------
# Readiness check
# -----------------------------------------------------------------------------

# gcp_wait_for_ssh VM_NAME PROJECT ZONE [MAX_WAIT_SECONDS]
# Waits until SSH is available on the VM. Default timeout: 120s.
gcp_wait_for_ssh() {
    local vm_name="$1"
    local project="$2"
    local zone="$3"
    local max_wait="${4:-120}"
    local waited=0

    echo "[INFO] Waiting for SSH..."
    until gcp_ssh "$vm_name" "$project" "$zone" "echo ready" &>/dev/null; do
        if [[ $waited -ge $max_wait ]]; then
            echo "[ERROR] VM not reachable after ${max_wait}s"
            return 1
        fi
        sleep 10
        waited=$((waited + 10))
    done
    echo "[OK] VM is ready"
}

# -----------------------------------------------------------------------------
# Provisioning
# -----------------------------------------------------------------------------

# gcp_provision_server_report VM_NAME PROJECT ZONE REPO_URL INSTALL_PATH
# Clones server-report, creates venv, installs dependencies, writes
# minimal config. Must be called after gcp_load_distro_config.
gcp_provision_server_report() {
    local vm_name="$1"
    local project="$2"
    local zone="$3"
    local repo_url="$4"
    local install_path="$5"

    echo "[INFO] Provisioning..."

    gcp_ssh "$vm_name" "$project" "$zone" "$GCP_PROVISION_CMD"
    gcp_ssh "$vm_name" "$project" "$zone" "sudo git clone $repo_url $install_path"
    gcp_ssh "$vm_name" "$project" "$zone" "sudo chown -R \$USER:\$USER $install_path"
    gcp_ssh "$vm_name" "$project" "$zone" \
        "cd $install_path && $GCP_VENV_PYTHON -m venv .venv && .venv/bin/pip install -q -r requirements.txt"

    # Write minimal .env
    gcp_ssh "$vm_name" "$project" "$zone" \
        "printf 'MAILGUN_API_KEY=key-test-placeholder\n' > $install_path/.env"

    # Write shared config
    gcp_ssh "$vm_name" "$project" "$zone" "mkdir -p $install_path/configs/shared"
    gcp_ssh "$vm_name" "$project" "$zone" \
        "printf 'mailgun_domain: \"mg.example.com\"\nmailgun_api_url: \"https://api.eu.mailgun.net/v3\"\nrecipients:\n  - email: \"test@example.com\"\n    format: \"html\"\n' > $install_path/configs/shared/general.yaml"

    # Copy example config as server override
    gcp_ssh "$vm_name" "$project" "$zone" \
        "cp -r $install_path/configs/example $install_path/configs/\$(hostname)"

    echo "[OK] Provisioning complete"
}

# -----------------------------------------------------------------------------
# Project validation
# -----------------------------------------------------------------------------

# gcp_require_project PROJECT
# Exits with an error if PROJECT is empty.
gcp_require_project() {
    local project="$1"
    if [[ -z "$project" ]]; then
        echo "[ERROR] No GCP project specified and no default project set."
        echo "        Run: gcloud config set project YOUR_PROJECT_ID"
        exit 1
    fi
}
