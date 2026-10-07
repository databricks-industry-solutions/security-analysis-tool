#!/bin/bash
# Databricks cluster init script: installs TruffleHog once at cluster startup.
#
# Used when var.install_trufflehog_via_init_script is set to true in the SAT
# Terraform (terraform/common/jobs.tf, databricks_job.secrets_scanner). This
# avoids the secrets-scanner notebooks racing on /tmp/trufflehog when multiple
# concurrent scans land on the same cluster.
#
# NOTE: TRUFFLEHOG_VERSION here must be kept in sync with the copies hardcoded
# in notebooks/Includes/scan_secrets/notebook_secret_scan.py and
# notebooks/Includes/scan_secrets/cluster_secrets_scan.py.

set -euo pipefail

if [ -f /tmp/trufflehog ]; then
    echo "TruffleHog already installed at /tmp/trufflehog"
    exit 0
fi

# Pinned to a tagged release to prevent supply-chain tampering via the
# mutable main branch. Bump TRUFFLEHOG_VERSION to upgrade.
TRUFFLEHOG_VERSION=v3.94.3
echo "Installing TruffleHog ${TRUFFLEHOG_VERSION}..."

if curl -sSfL "https://raw.githubusercontent.com/trufflesecurity/trufflehog/refs/tags/${TRUFFLEHOG_VERSION}/scripts/install.sh" | sh -s -- -b /tmp "${TRUFFLEHOG_VERSION}"; then
    if [ -f /tmp/trufflehog ]; then
        echo "TruffleHog installed successfully at /tmp/trufflehog"
    else
        echo "ERROR: TruffleHog binary not found after installation!"
        exit 1
    fi
else
    echo "=========================================="
    echo "ERROR: Failed to download TruffleHog"
    echo "=========================================="
    echo ""
    echo "The TruffleHog security scanner could not be downloaded from:"
    echo "https://raw.githubusercontent.com/trufflesecurity/trufflehog/refs/tags/${TRUFFLEHOG_VERSION}/scripts/install.sh"
    echo ""
    echo "Possible causes:"
    echo "  1. Network connectivity issues"
    echo "  2. Firewall or proxy blocking external downloads"
    echo "  3. GitHub.com access is restricted in your environment"
    echo ""
    echo "ACTION REQUIRED:"
    echo "Please contact your IT/Security team to allowlist access to:"
    echo "  - raw.githubusercontent.com"
    echo "  - github.com/trufflesecurity"
    exit 1
fi
