# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** pre_run_config_check  
# MAGIC **Functionality:** Diagnose basic setup before running the job

# COMMAND ----------

# MAGIC %run ../Includes/install_sat_sdk

# COMMAND ----------

# MAGIC %run ../Utils/initialize

# COMMAND ----------

# MAGIC %run ../Utils/common

# COMMAND ----------

secret_scopes = dbutils.secrets.listScopes()

# Resolve the configured scope and key map from json_ (set by initialize.py).
# Falls back to defaults for standalone / manual notebook runs.
_sat_scope = json_.get("secret_scope", json_.get("master_name_scope", "sat_scope"))
_sat_keys  = json_.get("secret_keys", DEFAULT_SECRET_KEYS)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Let us check if there is an SAT scope configured

# COMMAND ----------

found = False
for _scope_entry in secret_scopes:
   if _scope_entry.name == _sat_scope:
      print(f'Your SAT configuration has the required scope: {_sat_scope}')
      found = True
      break
if not found:
   dbutils.notebook.exit(
       f'Your SAT configuration is missing required scope "{_sat_scope}". '
       f'Please review setup instructions or set the secret_scope job parameter.'
   )

# COMMAND ----------

# replace values for accounts exec
hostname = (
    dbutils.notebook.entry_point.getDbutils()
    .notebook()
    .getContext()
    .apiUrl()
    .getOrElse(None)
)
cloud_type = getCloudType(hostname)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Let us check if there are required configs in the SAT scope
# MAGIC
# MAGIC For 0.9+ installs most values are delivered as job parameters (not secrets),
# MAGIC so this check validates that **at minimum** the credential secret is readable.
# MAGIC Non-secret values (account_id, client_id, etc.) are verified via json_ which
# MAGIC was already populated by initialize.py — a missing param or scope value would
# MAGIC have caused initialize.py to fail before reaching this point.

# COMMAND ----------

# Only client_secret is required to be in the scope for all clouds.
_missing = []
_client_secret_key = _sat_keys.get("client_secret", "client-secret")
try:
   dbutils.secrets.get(scope=_sat_scope, key=_client_secret_key)
except Exception as e:
   _missing.append(f"  - client_secret (scope='{_sat_scope}', key='{_client_secret_key}'): {e}")

if _missing:
   dbutils.notebook.exit(
       "Your SAT configuration is missing required secret(s):\n"
       + "\n".join(_missing)
       + "\nPlease review setup instructions."
   )
else:
   print(f"SAT scope '{_sat_scope}' has the required credential secret.")

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
