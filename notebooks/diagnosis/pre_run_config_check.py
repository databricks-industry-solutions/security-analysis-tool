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


# COMMAND ----------

# MAGIC %md
# MAGIC ### Let us check if there is an SAT scope configured

# COMMAND ----------

found = False
for secret_scope in secret_scopes:
   
   if secret_scope.name == json_['master_name_scope']:
      print('Your SAT configuration has the required scope name')
      found=True
      break
if not found:
   dbutils.notebook.exit(f'Your SAT configuration is missing required scope {json_["master_name_scope"]}, please review setup instructions')

      

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

# COMMAND ----------

scope = json_["master_name_scope"]
workspace_only = bool(json_.get("workspace_only"))
required_secrets = ["sql-warehouse-id", "analysis_schema_name"]
if not workspace_only:
    required_secrets.append("account-console-id")

if cloud_type in ("aws", "gcp"):
    required_secrets.extend(["client-id", "client-secret", "use-sp-auth"])
elif cloud_type == "azure":
    # Databricks SP client-id/secret always. Entra (tenant-id + subscription-id)
    # is required for full Azure, or for workspace-only when GOV-3 stays enabled.
    required_secrets.extend(["client-id", "client-secret"])
    azure_entra_complete = bool(str(json_.get("tenant_id", "")).strip()) and bool(
        str(json_.get("subscription_id", "")).strip()
    )
    if (not workspace_only) or azure_entra_complete or any_check_enabled(
        "8", cloud_type=cloud_type
    ):
        required_secrets.extend(["tenant-id", "subscription-id"])

try:
    for key in required_secrets:
        dbutils.secrets.get(scope=scope, key=key)
    print("Your SAT configuration has required secret names")
except Exception as e:
    dbutils.notebook.exit(
        f"Your SAT configuration is missing required secret, please review setup instructions {e}"
    )

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
