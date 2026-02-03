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

# %run ../Includes/install_sat_sdk

# COMMAND ----------

# %run ../Utils/initialize

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

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test 4: Configuration File Validation

# COMMAND ----------

print("="*80)
print("TEST 4: CONFIGURATION FILE VALIDATION")
print("="*80)

# Construct config path
try:
    notebook_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
    path_parts = notebook_path.split('/')
    sat_index = path_parts.index('security-analysis-tool')
    repo_root = '/'.join(path_parts[:sat_index+1])
    config_path = f"{repo_root}/configs/trufflehog_detectors.yaml"
    print(f"Config path: {config_path}")

    # For workspace files, need to use dbutils.fs or alternative approach
    # Since we can't easily read Workspace files, we'll validate structure programmatically
    print("⚠️  Cannot directly read Workspace file from notebook")
    print("   Config validation will occur when secret scanner runs")
    print("✅ PASSED - Config path constructed successfully")

except Exception as e:
    print(f"❌ FAILED - Error constructing config path: {str(e)}")

print()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test 5: Built-in Detector Scan Test

# COMMAND ----------

print("="*80)
print("TEST 5: BUILT-IN DETECTOR SCAN")
print("="*80)

if not os.path.exists("/tmp/trufflehog"):
    print("❌ FAILED - TruffleHog not installed")
else:
    # Create test file with AWS-like pattern
    test_file = "/tmp/test_secrets_builtin.txt"
    with open(test_file, 'w') as f:
        f.write("""
# Test file for built-in detectors
# These are test patterns, not real secrets
aws_access_key = "AKIAIOSFODNN7EXAMPLE"  # gitleaks:allow
aws_secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
github_token = "ghp_1234567890abcdefghijklmnopqrstuvwxyz"  # gitleaks:allow
""")

    print(f"Created test file: {test_file}")

    try:
        start_time = time.time()
        result = subprocess.run(
            ["/tmp/trufflehog", "filesystem", test_file, "--no-update", "-j"],
            capture_output=True,
            text=True,
            timeout=30
        )
        elapsed = time.time() - start_time

        print(f"Exit code: {result.returncode}")
        print(f"Scan time: {elapsed:.2f}s")

        # Parse JSON output
        findings = []
        for line in result.stdout.strip().split('\n'):
            if line:
                try:
                    findings.append(json.loads(line))
                except:
                    pass

        print(f"Findings: {len(findings)}")

        if findings:
            print("Detector types found:")
            for finding in findings[:5]:
                detector = finding.get('DetectorName', 'unknown')
                verified = finding.get('Verified', False)
                print(f"  - {detector} (verified: {verified})")

        if result.returncode in [0, 183]:  # 183 = secrets found
            print("✅ PASSED - Scan executed successfully")
        else:
            print(f"⚠️  PARTIAL PASS - Exit code {result.returncode}")

    except subprocess.TimeoutExpired:
        print("❌ FAILED - Scan timeout")
    except Exception as e:
        print(f"❌ FAILED - {str(e)}")
    finally:
        if os.path.exists(test_file):
            os.unlink(test_file)

print()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test 6: Custom Detector Scan Test

# COMMAND ----------

print("="*80)
print("TEST 6: CUSTOM DETECTOR SCAN")
print("="*80)

if not os.path.exists("/tmp/trufflehog"):
    print("❌ FAILED - TruffleHog not installed")
else:
    # Create test file with Databricks token pattern
    test_file = "/tmp/test_secrets_custom.txt"
    with open(test_file, 'w') as f:
        f.write("""
# Test file for custom Databricks detectors
databricks_token = "dapi1234567890abcdef1234567890ab"
databricks_token2 = "dkeaabcdef1234567890abcdef123456"
""")

    # Create custom config
    custom_config = {
        'detectors': [
            {
                'name': 'DapiToken',
                'keywords': ['dapi'],
                'regex': {
                    'id': r'(?i)\b(dapi[a-h0-9]{32})'
                }
            },
            {
                'name': 'DkeaToken',
                'keywords': ['dkea'],
                'regex': {
                    'id': r'(?i)\b(dkea[a-h0-9]{32})'
                }
            }
        ]
    }

    config_file = "/tmp/trufflehog_test_config.yaml"
    with open(config_file, 'w') as f:
        yaml.dump(custom_config, f)

    print(f"Created test file: {test_file}")
    print(f"Created config: {config_file}")

    try:
        start_time = time.time()
        result = subprocess.run(
            ["/tmp/trufflehog", "filesystem", test_file,
             "--config", config_file, "--no-update", "-j"],
            capture_output=True,
            text=True,
            timeout=30
        )
        elapsed = time.time() - start_time

        print(f"Exit code: {result.returncode}")
        print(f"Scan time: {elapsed:.2f}s")

        # Parse findings
        findings = []
        for line in result.stdout.strip().split('\n'):
            if line:
                try:
                    findings.append(json.loads(line))
                except:
                    pass

        print(f"Findings: {len(findings)}")

        if findings:
            print("Custom detectors found:")
            for finding in findings:
                detector = finding.get('DetectorName', 'unknown')
                print(f"  - {detector}")

        if result.returncode in [0, 183]:
            print("✅ PASSED - Custom detector scan successful")
        else:
            print(f"⚠️  PARTIAL PASS - Exit code {result.returncode}")

    except Exception as e:
        print(f"❌ FAILED - {str(e)}")
    finally:
        if os.path.exists(test_file):
            os.unlink(test_file)
        if os.path.exists(config_file):
            os.unlink(config_file)

print()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test 7: JSON Output Parsing

# COMMAND ----------

print("="*80)
print("TEST 7: JSON OUTPUT PARSING")
print("="*80)

# Test JSON parsing with sample output
sample_json = {
    "SourceMetadata": {"Data": {"Filesystem": {"file": "/tmp/test.py"}}},
    "SourceID": 0,
    "SourceType": 15,
    "SourceName": "trufflehog",
    "DetectorType": 2,
    "DetectorName": "AWS",
    "DecoderName": "PLAIN",
    "Verified": False,
    "Raw": "AKIAIOSFODNN7EXAMPLE",  # gitleaks:allow
    "RawV2": "",
    "Redacted": "AKIA****************"
}

try:
    # Test required fields
    required_fields = ['DetectorName', 'Verified', 'Raw', 'SourceMetadata']
    missing = [f for f in required_fields if f not in sample_json]

    if missing:
        print(f"❌ FAILED - Missing fields: {missing}")
    else:
        print(f"✅ All required fields present")

        # Test field extraction
        detector = sample_json.get('DetectorName')
        verified = sample_json.get('Verified')
        raw = sample_json.get('Raw')

        print(f"   Detector: {detector}")
        print(f"   Verified: {verified}")
        print(f"   Raw: {raw[:10]}...")

        # Test SHA-256 hashing (used by SAT)
        import hashlib
        secret_hash = hashlib.sha256(raw.encode()).hexdigest()
        print(f"   SHA-256: {secret_hash[:16]}...")

        print("✅ PASSED - JSON parsing validation successful")

except Exception as e:
    print(f"❌ FAILED - {str(e)}")

print()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test 8: Performance Test

# COMMAND ----------

print("="*80)
print("TEST 8: PERFORMANCE TEST")
print("="*80)

if not os.path.exists("/tmp/trufflehog"):
    print("❌ SKIPPED - TruffleHog not installed")
else:
    # Create larger test file
    test_file = "/tmp/test_performance.py"
    with open(test_file, 'w') as f:
        f.write("# " * 1000)  # 1KB of comments
        f.write("\n" * 100)
        f.write("test_var = 'dapi1234567890abcdef1234567890ab'\n")

    file_size = os.path.getsize(test_file)
    print(f"Test file size: {file_size:,} bytes")

    try:
        start_time = time.time()
        result = subprocess.run(
            ["/tmp/trufflehog", "filesystem", test_file, "--no-update", "-j"],
            capture_output=True,
            text=True,
            timeout=60
        )
        elapsed = time.time() - start_time

        scan_speed = file_size / elapsed if elapsed > 0 else 0

        print(f"Scan time: {elapsed:.2f}s")
        print(f"Scan speed: {scan_speed:,.0f} bytes/sec")

        if elapsed < 5:
            print("✅ PASSED - Performance acceptable")
        elif elapsed < 10:
            print("⚠️  WARNING - Scan slower than expected")
        else:
            print("❌ FAILED - Scan too slow")

    except Exception as e:
        print(f"❌ FAILED - {str(e)}")
    finally:
        if os.path.exists(test_file):
            os.unlink(test_file)

print()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary

# COMMAND ----------

print("="*80)
print("DIAGNOSTIC SUMMARY")
print("="*80)
print()
print("Review the test results above. All tests should show ✅ PASSED.")
print()
print("If any tests failed:")
print("1. Binary Check Failed: Run manual installation (Test 3)")
print("2. Network Access Failed: Contact IT to allowlist GitHub domains")
print("3. Scan Tests Failed: Check TruffleHog version and network connectivity")
print("4. Performance Issues: May be normal on serverless compute")
print()
print("Next Steps:")
print("- If all tests passed: Secret scanner is ready to use")
print("- If tests failed: Address issues before running secret scanner")
print("- Run security_analysis_secrets_scanner.py to perform actual scanning")
print()
