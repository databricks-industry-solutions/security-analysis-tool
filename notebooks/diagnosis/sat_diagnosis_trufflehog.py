# Databricks notebook source
# MAGIC %md
# MAGIC # TruffleHog Secret Scanner Diagnostic
# MAGIC
# MAGIC **Purpose:** Comprehensive validation of TruffleHog installation, configuration, and functionality.
# MAGIC
# MAGIC **Tests Performed:**
# MAGIC 1. Binary installation and version check
# MAGIC 2. Network access to GitHub
# MAGIC 3. Manual installation attempt
# MAGIC 4. Configuration file validation
# MAGIC 5. Built-in detector test scan
# MAGIC 6. Custom detector test scan
# MAGIC 7. JSON output parsing validation
# MAGIC 8. Performance test (scan speed)
# MAGIC
# MAGIC **When to Use:** Run this diagnostic if secret scanning jobs fail or before deploying secret scanner.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Setup and Initialization

# COMMAND ----------

# MAGIC %run ../Includes/install_sat_sdk

# COMMAND ----------

# MAGIC %run ../Utils/initialize

# COMMAND ----------

import os
import subprocess
import json
import yaml
import tempfile
import time
from datetime import datetime

print(f"SAT Version: {json_['sat_version']}")
print(f"Diagnostic run time: {datetime.now().isoformat()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test 1: TruffleHog Binary Check

# COMMAND ----------

print("="*80)
print("TEST 1: TRUFFLEHOG BINARY CHECK")
print("="*80)

trufflehog_path = "/tmp/trufflehog"
binary_exists = os.path.exists(trufflehog_path)

print(f"Binary path: {trufflehog_path}")
print(f"Binary exists: {binary_exists}")

if binary_exists:
    # Check permissions
    stat_info = os.stat(trufflehog_path)
    is_executable = stat_info.st_mode & 0o111
    print(f"Executable: {bool(is_executable)}")
    print(f"Size: {stat_info.st_size:,} bytes")

    # Get version
    try:
        result = subprocess.run(
            [trufflehog_path, "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            print(f"Version: {result.stdout.strip()}")
            print("✅ PASSED")
        else:
            print(f"Version check failed (exit code {result.returncode})")
            print(f"stderr: {result.stderr}")
            print("⚠️  PARTIAL PASS")
    except Exception as e:
        print(f"Error checking version: {str(e)}")
        print("❌ FAILED")
else:
    print("❌ FAILED - Binary not found")

print()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test 2: Network Access to GitHub

# COMMAND ----------

print("="*80)
print("TEST 2: GITHUB NETWORK ACCESS")
print("="*80)

import requests

urls_to_test = {
    "Install Script": "https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh",
    "Releases": "https://github.com/trufflesecurity/trufflehog/releases",
    "Raw Content": "https://raw.githubusercontent.com"
}

all_passed = True
for name, url in urls_to_test.items():
    try:
        response = requests.head(url, timeout=10)
        if response.status_code < 400:
            print(f"✅ {name}: {url} - OK ({response.status_code})")
        else:
            print(f"⚠️  {name}: {url} - Status {response.status_code}")
            all_passed = False
    except requests.exceptions.Timeout:
        print(f"❌ {name}: {url} - TIMEOUT")
        all_passed = False
    except Exception as e:
        print(f"❌ {name}: {url} - {str(e)}")
        all_passed = False

if all_passed:
    print("\n✅ PASSED - All URLs accessible")
else:
    print("\n❌ FAILED - Some URLs not accessible")
    print("ACTION: Contact IT to allowlist GitHub domains")

print()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test 3: Manual Installation Test

# COMMAND ----------

# MAGIC %md
# MAGIC ### Install TruffleHog (if not present)

# COMMAND ----------

# MAGIC %sh
# MAGIC
# MAGIC echo "============================================"
# MAGIC echo "INSTALLING TRUFFLEHOG"
# MAGIC echo "============================================"
# MAGIC
# MAGIC if [ -f /tmp/trufflehog ]; then
# MAGIC     echo "TruffleHog already installed"
# MAGIC     /tmp/trufflehog --version
# MAGIC     echo "✅ PASSED - Already installed"
# MAGIC else
# MAGIC     echo "Downloading TruffleHog..."
# MAGIC
# MAGIC     if curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh | sh -s -- -b /tmp; then
# MAGIC         if [ -f /tmp/trufflehog ]; then
# MAGIC             echo "✅ PASSED - Installation successful"
# MAGIC             /tmp/trufflehog --version
# MAGIC         else
# MAGIC             echo "❌ FAILED - Binary not found after installation"
# MAGIC             exit 1
# MAGIC         fi
# MAGIC     else
# MAGIC         echo "❌ FAILED - Download failed"
# MAGIC         echo "Check network access to:"
# MAGIC         echo "  - raw.githubusercontent.com"
# MAGIC         echo "  - github.com/trufflesecurity"
# MAGIC         exit 1
# MAGIC     fi
# MAGIC fi
