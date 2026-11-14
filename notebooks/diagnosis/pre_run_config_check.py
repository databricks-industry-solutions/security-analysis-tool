# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** pre_run_config_check  
# MAGIC **Functionality:** Diagnose basic setup before running the job

# COMMAND ----------

# This pre-flight only checks that the TruffleHog scanner is installed and that
# the network it needs is reachable; it needs neither the SAT SDK nor the shared
# config, so it does not %run install_sat_sdk / initialize / common (the secrets
# scanner that runs this does that itself).
# The SAT app supplies all configuration as job parameters and stores credentials
# as Unity Catalog secrets, so there is no secret scope to validate here. The
# checks below confirm the TruffleHog scanner is installed and reachable.

# COMMAND ----------

# MAGIC %md
# MAGIC ## TruffleHog Installation Check
# MAGIC
# MAGIC Verifies that TruffleHog secret scanner is installed and accessible.

# COMMAND ----------

import os
import subprocess
import requests

print("=" * 80)
print("TRUFFLEHOG INSTALLATION CHECK")
print("=" * 80)

# Check if TruffleHog binary exists
trufflehog_path = "/tmp/trufflehog"
if os.path.exists(trufflehog_path):
    print(f"✅ TruffleHog binary found at: {trufflehog_path}")

    # Get TruffleHog version
    try:
        result = subprocess.run(
            [trufflehog_path, "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"✅ TruffleHog version: {version}")
        else:
            print(f"⚠️  TruffleHog installed but version check failed")
            print(f"   stdout: {result.stdout}")
            print(f"   stderr: {result.stderr}")
    except Exception as e:
        print(f"⚠️  Error checking TruffleHog version: {str(e)}")
else:
    print(f"❌ TruffleHog binary NOT found at: {trufflehog_path}")
    print()
    print("TruffleHog Installation Instructions:")
    print("1. TruffleHog is automatically installed when running secret scanner")
    print("2. Manual installation:")
    print("   %sh curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh | sh -s -- -b /tmp")
    print()
    print("Network Requirements:")
    print("- Access to raw.githubusercontent.com (install script)")
    print("- Access to github.com/trufflesecurity (binary download)")

print()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Network Access Check for TruffleHog

# COMMAND ----------

print("=" * 80)
print("NETWORK ACCESS CHECK (TRUFFLEHOG)")
print("=" * 80)

# Test access to GitHub raw content
github_urls = [
    "https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh",
    "https://github.com/trufflesecurity/trufflehog/releases"
]

for url in github_urls:
    try:
        response = requests.head(url, timeout=10)
        if response.status_code == 200:
            print(f"✅ Access OK: {url}")
        else:
            print(f"⚠️  Access issue ({response.status_code}): {url}")
    except requests.exceptions.Timeout:
        print(f"❌ Timeout accessing: {url}")
    except requests.exceptions.ConnectionError:
        print(f"❌ Connection failed: {url}")
        print("   ACTION: Allowlist GitHub domains in firewall")
    except Exception as e:
        print(f"❌ Error accessing {url}: {str(e)}")

print()
