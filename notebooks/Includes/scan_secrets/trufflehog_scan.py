# Databricks notebook source
# MAGIC %md
# MAGIC # TruffleHog Secret Scanner for Databricks Notebooks
# MAGIC
# MAGIC ## Overview
# MAGIC This notebook scans Databricks workspace notebooks for exposed secrets using TruffleHog. It integrates with the Security Analysis Tool (SAT) to provide comprehensive secret detection across your Databricks environment.
# MAGIC
# MAGIC ## Features
# MAGIC - Scans all notebooks modified within a specified timeframe
# MAGIC - Uses custom detectors for Databricks-specific tokens
# MAGIC - Excludes built-in Databricks tokens to reduce false positives  
# MAGIC - Provides detailed reporting with SHA-256 hashed secrets for security
# MAGIC - Handles pagination for large workspaces
# MAGIC - Includes proper error handling and rate limiting
# MAGIC
# MAGIC ## Prerequisites
# MAGIC - Databricks workspace with appropriate permissions
# MAGIC - Access to install packages and run shell commands
# MAGIC - Valid Databricks API token (automatically extracted from notebook context)
# MAGIC
# MAGIC ---

# COMMAND ----------

# MAGIC %run ../install_sat_sdk

# COMMAND ----------

import time
start_time = time.time()

# COMMAND ----------

# MAGIC %run ../../Utils/common

# COMMAND ----------

test=False #local testing
if test:
    jsonstr = JSONLOCALTEST
else:
    jsonstr = dbutils.widgets.get('json_')

# COMMAND ----------

import json
if not jsonstr:
    print('cannot run notebook by itself')
    dbutils.notebook.exit('cannot run notebook by itself')
else:
    json_ = json.loads(jsonstr)

# COMMAND ----------


from core.logging_utils import LoggingUtils

LoggingUtils.set_logger_level(LoggingUtils.get_log_level(json_["verbosity"]))
loggr = LoggingUtils.get_logger()

# COMMAND ----------

hostname = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().getOrElse(None)
cloud_type = getCloudType(hostname)

# COMMAND ----------

import requests
from core import  parser as pars
from core.dbclient import SatDBClient

if cloud_type =='azure': # use client secret
  client_secret = dbutils.secrets.get(json_['master_name_scope'], json_["client_secret_key"])
  json_.update({'token':'dapijedi', 'client_secret': client_secret})
elif (cloud_type =='aws' and json_['use_sp_auth'].lower() == 'true'):  
  client_secret = dbutils.secrets.get(json_['master_name_scope'], json_["client_secret_key"])
  json_.update({'token':'dapijedi', 'client_secret': client_secret})
  mastername =' ' # this will not be present when using SPs
  masterpwd = ' '  # we still need to send empty user/pwd.
  json_.update({'token':'dapijedi', 'mastername':mastername, 'masterpwd':masterpwd})
else: #lets populate master key for accounts api
  client_secret = dbutils.secrets.get(json_['master_name_scope'], json_["client_secret_key"])
  json_.update({'token':'dapijedi', 'client_secret': client_secret})
  mastername = ' '
  masterpwd = ' '
  #mastername = dbutils.secrets.get(json_['master_name_scope'], json_['master_name_key'])
  #masterpwd = dbutils.secrets.get(json_['master_pwd_scope'], json_['master_pwd_key'])
  json_.update({'token':'dapijedi', 'mastername':mastername, 'masterpwd':masterpwd})

db_client = SatDBClient(json_)


# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1: Install Dependencies and Setup TruffleHog
# MAGIC
# MAGIC This cell installs required Python packages and downloads TruffleHog binary.

# COMMAND ----------

# MAGIC %sh 
# MAGIC # Install required Python packages
# MAGIC pip install requests pyyaml
# MAGIC
# MAGIC # Download and install TruffleHog binary to /tmp directory
# MAGIC echo "Installing TruffleHog..."
# MAGIC curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh | sh -s -- -b /tmp
# MAGIC
# MAGIC echo "Setup completed successfully!"
# MAGIC echo "TruffleHog binary location: /tmp/trufflehog"
# MAGIC echo "Configuration will be loaded from: /Workspace/Repos/.../configs/trufflehog_detectors.yaml"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2: Configuration and Authentication
# MAGIC
# MAGIC This cell sets up configuration constants and extracts Databricks authentication context.

# COMMAND ----------

# Import required libraries
import os
import requests
import time
import json
import base64
import subprocess
import hashlib
import logging
import yaml
from datetime import timedelta, datetime
from urllib.parse import quote
from typing import Dict, List, Optional, Any

# Configure logging for better debugging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_config_from_file():
    """Load configuration from the external YAML file in the configs directory."""
    try:
        # Get the current notebook's directory and construct path to config file
        notebook_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
        config_folder = getConfigPath()
        config_path = f"{config_folder}/trufflehog_detectors.yaml"
        
        logger.info(f"Loading configuration from: {config_path}")
        
        # Read the configuration file
        with open(config_path, 'r') as file:
            config_data = yaml.safe_load(file)
        
        return config_data
    except Exception as e:
        logger.warning(f"Could not load external config file: {str(e)}")
        logger.info("Using default configuration")
        # Fallback to default configuration
        return {
            "detectors": [
                {"name": "DkeaToken", "keywords": ["dkea"], "regex": {"id": "(?i)\\b(dkea[a-h0-9]{32})"}},
                {"name": "DapiToken", "keywords": ["dapi"], "regex": {"id": "(?i)\\b(dapi[a-h0-9]{32})"}},
                {"name": "DoseToken", "keywords": ["dose"], "regex": {"id": "(?i)\\b(dose[a-h0-9]{32})"}}
            ],
            "settings": {
                "excluded_detectors": ["DatabricksToken"],
                "rate_limiting": {"api_sleep_seconds": 10},
                "search_settings": {"page_size": 50, "days_back": 1}
            }
        }

def create_trufflehog_config(config_data: Dict[str, Any]) -> str:
    """Create TruffleHog configuration file from loaded config data."""
    config_file_path = "/tmp/trufflehog_config.yaml"
    
    # Extract just the detectors section for TruffleHog
    trufflehog_config = {"detectors": config_data.get("detectors", [])}
    
    try:
        with open(config_file_path, 'w') as file:
            yaml.dump(trufflehog_config, file, default_flow_style=False)
        
        logger.info(f"TruffleHog configuration created at: {config_file_path}")
        return config_file_path
    except Exception as e:
        logger.error(f"Failed to create TruffleHog config file: {str(e)}")
        raise

# Load configuration from external file
config_data = load_config_from_file()

# Configuration class using loaded values
class Config:
    """Configuration class for TruffleHog scanning parameters"""
    
    # File paths
    TRUFFLEHOG_BINARY = "/tmp/trufflehog"
    TRUFFLEHOG_CONFIG = create_trufflehog_config(config_data)
    TEMP_NOTEBOOKS_DIR = config_data.get("settings", {}).get("file_paths", {}).get("temp_notebooks", "/tmp/notebooks")
    RESULTS_LOG_FILE = config_data.get("settings", {}).get("file_paths", {}).get("results_log", "/tmp/trufflehog_scan_results.json")
    
    # API settings from config
    API_SLEEP_SECONDS = config_data.get("settings", {}).get("rate_limiting", {}).get("api_sleep_seconds", 10)
    PAGE_SIZE = config_data.get("settings", {}).get("search_settings", {}).get("page_size", 50)
    DAYS_BACK = config_data.get("settings", {}).get("search_settings", {}).get("days_back", 1)
    
    # TruffleHog settings from config
    EXCLUDED_DETECTORS = config_data.get("settings", {}).get("excluded_detectors", ["DatabricksToken"])
    
# Extract Databricks authentication context
# These are automatically available in Databricks notebooks
try:
    token = db_client.get_temporary_oauth_token() 
    base_url = json_["url"] 
    
    if not token or not base_url:
        raise ValueError("Unable to extract Databricks authentication context")
        
    logger.info(f"Successfully extracted Databricks context. Base URL: {base_url}")
    
except Exception as e:
    logger.error(f"Failed to extract Databricks context: {str(e)}")
    raise

# Create temporary directories if they don't exist
os.makedirs(Config.TEMP_NOTEBOOKS_DIR, exist_ok=True)
logger.info(f"Temporary directory created: {Config.TEMP_NOTEBOOKS_DIR}")

print("✅ Configuration loaded from external file and authentication setup completed successfully!")
print(f"📁 Config file: {Config.TRUFFLEHOG_CONFIG}")
print(f"🔧 Loaded {len(config_data.get('detectors', []))} custom detectors")
print(f"⚙️  API sleep: {Config.API_SLEEP_SECONDS}s, Page size: {Config.PAGE_SIZE}, Days back: {Config.DAYS_BACK}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3: Utility Functions
# MAGIC
# MAGIC This cell defines all the utility functions for API interactions, file operations, and secret scanning.

# COMMAND ----------

# Utility Functions for TruffleHog Secret Scanning

def get_yesterday_utc_midnight() -> int:
    """
    Get yesterday's date in UTC at midnight as milliseconds timestamp.
    
    Returns:
        int: Timestamp in milliseconds for yesterday at 00:00 UTC
    """
    today_utc_midnight = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_utc_midnight = today_utc_midnight - timedelta(days=Config.DAYS_BACK)
    return int(yesterday_utc_midnight.timestamp() * 1000)

def convert_time_to_databricks_format(env_time: int) -> int:
    """
    Convert environment time to Databricks format.
    
    Args:
        env_time (int): Time in milliseconds
        
    Returns:
        int: Time in Databricks format (milliseconds)
    """
    return int(env_time)

def generate_sha256_hash(secret: str) -> str:
    """
    Generate SHA-256 hash of a secret for secure logging.
    
    Args:
        secret (str): The secret string to hash
        
    Returns:
        str: SHA-256 hash in hexadecimal format
    """
    secret_bytes = secret.encode("utf-8")
    sha = hashlib.sha256()
    sha.update(secret_bytes)
    return sha.hexdigest()

def make_api_request(url: str, headers: Dict[str, str], data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """
    Make API request to Databricks with proper error handling.
    
    Args:
        url (str): API endpoint URL
        headers (Dict[str, str]): Request headers
        data (Optional[Dict[str, Any]]): Request payload
        
    Returns:
        Optional[Dict[str, Any]]: JSON response or None if error
    """
    try:
        response = requests.get(url, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            logger.warning(f"Rate limit hit for URL: {url}. Waiting before retry...")
            time.sleep(Config.API_SLEEP_SECONDS * 2)  # Wait longer for rate limits
            return None
        else:
            logger.warning(f"API request failed. URL: {url}, Status: {response.status_code}")
            return None
            
    except requests.exceptions.Timeout:
        logger.error(f"Request timeout for URL: {url}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error for URL: {url}. Error: {str(e)}")
        return None

def check_notebook_status(notebook_path: str) -> int:
    """
    Check if a notebook exists and is accessible.
    
    Args:
        notebook_path (str): Path to the notebook
        
    Returns:
        int: HTTP status code (200=accessible, 403=no permission, 404=not found)
    """
    check_url = f"{base_url}/api/2.0/workspace/get-status?path={notebook_path}"
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "databricks-sat/0.1.0"}

    try:
        response = requests.get(check_url, headers=headers, timeout=30)
        return response.status_code
    except requests.exceptions.RequestException as e:
        logger.error(f"Error checking notebook status for {notebook_path}: {str(e)}")
        return 500  # Internal server error

def export_notebook_content(notebook_path: str) -> Optional[Dict[str, Any]]:
    """
    Export notebook content from Databricks workspace.
    
    Args:
        notebook_path (str): Path to the notebook
        
    Returns:
        Optional[Dict[str, Any]]: Notebook export response or None if error
    """
    try:
        headers = {"Authorization": f"Bearer {token}","User-Agent": "databricks-sat/0.1.0"}
        url = f"{base_url}/api/2.0/workspace/export?path={notebook_path}"
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error exporting notebook content for {notebook_path}: {str(e)}")
        return None

def decode_and_write_content(content: str, output_path: str) -> bool:
    """
    Decode base64 content and write to file.
    
    Args:
        content (str): Base64 encoded content
        output_path (str): Path to write decoded content
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        decoded_content = base64.b64decode(content).decode("utf-8")
        with open(output_path, "w", encoding="utf-8") as file:
            file.write(decoded_content)
        return True
    except Exception as e:
        logger.error(f"Error writing content to {output_path}: {str(e)}")
        return False

def scan_for_secrets(file_path: str) -> Optional[str]:
    """
    Run TruffleHog scan on a file to detect secrets.
    Runs two scans: one with built-in detectors and one with custom detectors,
    then combines the results.
    
    Args:
        file_path (str): Path to file to scan
        
    Returns:
        Optional[str]: TruffleHog output in JSON format or None if error
    """
    all_results = []
    
    # Scan 1: Run with built-in detectors (excluding specified ones)
    excluded_detectors = ",".join(Config.EXCLUDED_DETECTORS)
    builtin_command = (
        f"{Config.TRUFFLEHOG_BINARY} filesystem {file_path} "
        f"--exclude-detectors={excluded_detectors} "
        f"--no-update -j"
    )
    
    try:
        logger.info(f"Running built-in detectors scan on {file_path}")
        logger.info(f"Built-in scan command: {builtin_command}")
        result = subprocess.run(
            builtin_command, 
            shell=True, 
            check=True,  # Don't raise exception on non-zero exit code
            capture_output=True, 
            text=True,
            timeout=300  # 5 minute timeout
        )
        logger.info(f"Built-in scan exit code: {result.returncode}")
        
        if result.stdout:
            all_results.append(result.stdout)
            logger.info(f"Built-in detectors scan completed with {len(result.stdout.splitlines())} output lines")
            # Print first 1000 chars of output for debugging
            print(f"Built-in scan found secrets: {result.stdout[:1000]}")
        else:
            logger.info(f"Built-in detectors scan completed with no secrets found")
            print(f"Built-in scan stdout was empty")
        
        if result.stderr:
            logger.info(f"Built-in scan stderr: {result.stderr}")
            print(f"Built-in scan stderr: {result.stderr}")
    except subprocess.TimeoutExpired:
        logger.error(f"Built-in detectors scan timed out for file: {file_path}")
    
    # Scan 2: Run with custom detectors from config file
    custom_command = (
        f"{Config.TRUFFLEHOG_BINARY} filesystem {file_path} "
        f"--no-update --config {Config.TRUFFLEHOG_CONFIG} -j"
    )
    
    try:
        logger.info(f"Running custom detectors scan on {file_path}")
        result = subprocess.run(
            custom_command, 
            shell=True, 
            check=True,  # Don't raise exception on non-zero exit code
            capture_output=True, 
            text=True,
            timeout=300  # 5 minute timeout
        )
        if result.stdout:
            all_results.append(result.stdout)
            logger.info(f"Custom detectors scan completed with output")
        else:
            logger.info(f"Custom detectors scan completed with no secrets found")
        
        if result.stderr:
            logger.debug(f"Custom scan stderr: {result.stderr}")
        if result.returncode != 0:
            logger.warning(f"Custom scan returned non-zero exit code: {result.returncode}")
    except subprocess.TimeoutExpired:
        logger.error(f"Custom detectors scan timed out for file: {file_path}")
    
    # Combine results from both scans
    if all_results:
        return "\n".join(all_results)
    else:
        logger.warning(f"Both scans completed but no results found for {file_path}")
        return ""

def process_trufflehog_output(trufflehog_output: str) -> List[Dict[str, str]]:
    """
    Process TruffleHog JSON output and extract relevant information.
    
    Args:
        trufflehog_output (str): Raw TruffleHog output in JSON format
        
    Returns:
        List[Dict[str, str]]: List of detected secrets with hashed values
    """
    results = []
    
    if not trufflehog_output or not trufflehog_output.strip():
        return results
    
    for line in trufflehog_output.strip().splitlines():
        try:
            data = json.loads(line)
            detector_name = data.get("DetectorName", "Unknown")
            raw_value = data.get("Raw", "")
            
            if raw_value:
                # Generate SHA-256 hash for security (don't log actual secrets)
                raw_sha = generate_sha256_hash(raw_value)
                
                # Add metadata about the detection
                result = {
                    "DetectorName": detector_name,
                    "Raw_SHA": raw_sha,
                    "SourceFile": data.get("SourceMetadata", {}).get("Data", {}).get("Filesystem", {}).get("file", "Unknown"),
                    "Verified": data.get("Verified", False)
                }
                results.append(result)
                
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse TruffleHog output line: {line}. Error: {str(e)}")
            continue
    
    return results

print("✅ Utility functions defined successfully!")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3.5: Database Storage Functions
# MAGIC
# MAGIC This cell contains functions for storing secret scan results in the SAT database.

# COMMAND ----------

def insert_secret_scan_results(workspace_id: str, notebook_metadata: Dict[str, Any], run_id: int) -> None:
    """
    Insert secret scan results into the secret_scan_results table.
    Only inserts records when secrets are actually found to avoid database bloat.
    
    Args:
        workspace_id (str): Workspace ID being scanned
        notebook_metadata (Dict[str, Any]): Notebook metadata with secret details
        run_id (int): SAT run ID for tracking
    """
    import time
    
    try:
        # Create the table if it doesn't exist
        create_secret_scan_results_table()
        logger.info(f"Inserting secret scan results for workspace_id: {workspace_id}")
        logger.info(f"Notebook metadata: {json.dumps(notebook_metadata, indent=2)}")
        scan_time = time.time()
        notebook_id = notebook_metadata.get("object_id", "")
        notebook_path = notebook_metadata.get("path", "")
        notebook_name = notebook_metadata.get("name", "")
        secrets_found = notebook_metadata.get("secrets_found", 0)
        
        if secrets_found > 0:
            # Only insert records when secrets are found
            secret_details = notebook_metadata.get("secret_details", [])
            
            for secret in secret_details:
                detector_name = secret.get("DetectorName", "Unknown")
                secret_sha256 = secret.get("Raw_SHA", "")
                source_file = secret.get("SourceFile", "")
                verified = secret.get("Verified", False)
                
                # Insert individual secret record
                sql = f"""
                INSERT INTO {json_["analysis_schema_name"]}.secret_scan_results 
                (workspace_id, notebook_id, notebook_path, notebook_name, detector_name, 
                 secret_sha256, source_file, verified, secrets_found, run_id, scan_time)
                VALUES ('{workspace_id}', '{notebook_id}', '{notebook_path}', '{notebook_name}', 
                        '{detector_name}', '{secret_sha256}', '{source_file}', {verified}, 
                        {secrets_found}, {run_id}, cast({scan_time} as timestamp))
                """
                
                spark.sql(sql)
                logger.info(f"Inserted secret scan result for notebook {notebook_id}, detector: {detector_name}")
        else:
            # Don't insert anything for clean notebooks to avoid database bloat
            logger.debug(f"No secrets found in notebook {notebook_id}, skipping database insert")
            
    except Exception as e:
        logger.error(f"Failed to insert secret scan results for notebook {notebook_id}: {str(e)}")
        # Don't raise exception to avoid stopping the scan process

def get_current_run_id() -> int:
    """
    Get the current SAT run ID for tracking scan results.
    
    Returns:
        int: Current run ID from SAT run tracking system
    """
    try:
        result = spark.sql(f'SELECT max(runID) FROM {json_["analysis_schema_name"]}.run_number_table').collect()
        if result and result[0][0] is not None:
            return result[0][0]
        else:
            # If no run ID exists, create a new one
            insertNewBatchRun()
            result = spark.sql(f'SELECT max(runID) FROM {json_["analysis_schema_name"]}.run_number_table').collect()
            return result[0][0] if result and result[0][0] is not None else 1
    except Exception as e:
        logger.error(f"Failed to get run ID: {str(e)}")
        return 1  # Default run ID

print("✅ Database storage functions defined successfully!")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4: Main Scanning Functions
# MAGIC
# MAGIC This cell contains the main functions for processing notebooks and orchestrating the secret scanning workflow.

# COMMAND ----------

# Main Scanning Functions

def scan_notebook_for_secrets(notebook_path: str, object_id: str) -> Optional[List[Dict[str, str]]]:
    """
    Scan a single notebook for secrets using TruffleHog.
    
    Args:
        notebook_path (str): Path to the notebook in Databricks workspace
        object_id (str): Unique identifier for the notebook
        
    Returns:
        Optional[List[Dict[str, str]]]: List of detected secrets or None if error
    """
    try:
        # Check if notebook exists and is accessible
        notebook_status = check_notebook_status(notebook_path)
        
        if notebook_status == 200:
            # Export notebook content
            export_response = export_notebook_content(notebook_path)
            if export_response is None:
                logger.warning(f"Failed to export notebook content: {notebook_path}")
                return None
                
            content = export_response.get("content")
            if not content:
                logger.warning(f"No content found in notebook: {notebook_path}")
                return None
            
            # Write content to temporary file
            output_file_path = os.path.join(Config.TEMP_NOTEBOOKS_DIR, f"notebook_content_{object_id}.txt")
            if not decode_and_write_content(content, output_file_path):
                logger.error(f"Failed to write notebook content to file: {output_file_path}")
                return None
                
            logger.info(f"Notebook content exported to: {output_file_path}")
            
            # Scan for secrets using TruffleHog
            trufflehog_output = scan_for_secrets(output_file_path)
            if trufflehog_output is None:
                logger.warning(f"TruffleHog scan failed for: {notebook_path}")
                return None
            
            # Process TruffleHog output
            results = process_trufflehog_output(trufflehog_output)
            
            if results:
                logger.info(f"Found {len(results)} potential secrets in notebook: {notebook_path}")
                # Log results securely (with hashed secrets)
                for result in results:
                    logger.info(f"Secret detected - Type: {result['DetectorName']}, SHA: {result['Raw_SHA'][:16]}...")
            else:
                logger.info(f"No secrets found in notebook: {notebook_path}")
            
            # Clean up temporary file
            try:
                os.remove(output_file_path)
            except OSError as e:
                logger.warning(f"Failed to clean up temporary file {output_file_path}: {str(e)}")
            
            return results
            
        elif notebook_status == 403:
            logger.warning(f"Access denied for notebook: {notebook_path}")
            return None
        elif notebook_status == 404:
            logger.warning(f"Notebook not found: {notebook_path}")
            return None
        else:
            logger.warning(f"Unexpected status {notebook_status} for notebook: {notebook_path}")
            return None
            
    except Exception as e:
        logger.error(f"Error scanning notebook {notebook_path}: {str(e)}")
        return None

def process_search_response(response: Dict[str, Any], results_list: List[Dict[str, Any]], 
                          output_filename: Optional[str] = None, run_id: Optional[int] = None, 
                          workspace_id: Optional[str] = None) -> Optional[str]:
    """
    Process search API response and scan notebooks for secrets.
    
    Args:
        response (Dict[str, Any]): API response from unified search
        results_list (List[Dict[str, Any]]): List to store notebook metadata
        output_filename (Optional[str]): File to log notebook metadata
        run_id (Optional[int]): SAT run ID for database tracking
        workspace_id (Optional[str]): Workspace ID for database storage
        
    Returns:
        Optional[str]: Next page token for pagination or None if no more pages
    """
    if not response:
        logger.warning("Empty response received")
        return None
        
    results = response.get("results", [])
    logger.info(f"Processing {len(results)} notebooks from search response")
    
    for notebook in results:
        notebook_id = notebook.get("id", "")
        notebook_name = notebook.get("name", "")
        parent_path = notebook.get("workspace_path", "")
        
        if not notebook_id or not notebook_name:
            logger.warning("Skipping notebook with missing ID or name")
            continue
            
        # Construct full notebook path
        temp_path = f"{parent_path}/{notebook_name}"
        path = quote(temp_path)
        
        logger.info(f"Processing notebook: {notebook_id} - {temp_path}")
        
        # Store notebook metadata
        notebook_metadata = {"object_id": notebook_id, "path": path, "name": notebook_name}
        results_list.append(notebook_metadata)
        
        # Log to file if specified
        if output_filename:
            try:
                with open(output_filename, mode="a", encoding="utf-8") as output_file:
                    json.dump(notebook_metadata, output_file)
                    output_file.write("\n")
            except IOError as e:
                logger.error(f"Failed to write to output file {output_filename}: {str(e)}")
        
        # Scan notebook for secrets
        secret_results = scan_notebook_for_secrets(path, notebook_id)
        
        if secret_results:
            # Store results with notebook metadata
            notebook_metadata["secrets_found"] = len(secret_results)
            notebook_metadata["secret_details"] = secret_results
            
            # Log summary - only show when secrets are found
            print(f"🚨 SECRETS DETECTED in {temp_path}:")
            print(json.dumps(secret_results, indent=2))
        else:
            notebook_metadata["secrets_found"] = 0
            # Don't print "No secrets found" to avoid overwhelming output with thousands of notebooks
        
        # Store results in database if run_id and workspace_id are provided
        logger.info(f"Inserting secret scan results for workspace_id: {workspace_id} and run_id: {run_id}")
        logger.info(f"Notebook metadata: {json.dumps(notebook_metadata, indent=2)}")
        if run_id is not None and workspace_id is not None:
            insert_secret_scan_results(workspace_id, notebook_metadata, run_id)
    
    # Return next page token for pagination
    return response.get("next_page_token")

print("✅ Main scanning functions defined successfully!")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5: Execute Secret Scanning
# MAGIC
# MAGIC This cell executes the main scanning workflow to search for notebooks and scan them for secrets.

# COMMAND ----------

# Execute TruffleHog Secret Scanning Workflow

def main_scanning_workflow():
    """
    Main function to orchestrate the secret scanning process.
    """
    print("🔍 Starting TruffleHog Secret Scanning Workflow")
    print("=" * 60)
    
    # Get current workspace ID and run ID for database storage
    workspace_id = json_.get("workspace_id", "unknown")
    current_run_id = get_current_run_id()
    
    logger.info(f"TruffleHog scan starting for workspace: {workspace_id}, run_id: {current_run_id}")
    
    # Get time range for notebook search
    # Use environment variable TIME if provided, otherwise use config setting
    env_time = os.environ.get("TIME")
    if env_time:
        try:
            last_edited_after = convert_time_to_databricks_format(int(env_time))
            logger.info(f"Using provided TIME environment variable: {env_time}")
            time_filter_enabled = True
        except ValueError:
            logger.warning(f"Invalid TIME environment variable: {env_time}. Using default.")
            if Config.DAYS_BACK == 0:
                time_filter_enabled = False
            else:
                last_edited_after = get_yesterday_utc_midnight()
                time_filter_enabled = True
    else:
        # Check if days_back is 0 (scan all notebooks)
        if Config.DAYS_BACK == 0:
            time_filter_enabled = False
            logger.info(f"Scanning ALL notebooks (days_back = 0)")
        else:
            last_edited_after = get_yesterday_utc_midnight()
            time_filter_enabled = True
            logger.info(f"Using default time range: last {Config.DAYS_BACK} day(s)")
    
    # Initialize tracking variables
    results_list = []
    total_notebooks_processed = 0
    total_secrets_found = 0
    notebooks_with_secrets = 0
    
    # Setup API request parameters
    url = f"{base_url}/api/2.0/search-midtier/unified-search"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": "databricks-sat/0.1.0"}
    
    # Build filters - only include time filter if enabled
    filters = {"result_types": ["NOTEBOOK"]}
    if time_filter_enabled:
        filters["last_edited_after"] = last_edited_after
    
    data = {
        "query": {"query": ""},
        "filters": filters,
        "page_size": Config.PAGE_SIZE,
    }
    
    if time_filter_enabled:
        print(f"📅 Searching for notebooks modified after: {datetime.fromtimestamp(last_edited_after/1000).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    else:
        print(f"📅 Searching for ALL notebooks (no time filter)")
    print(f"📄 Page size: {Config.PAGE_SIZE}")
    print()
    
    # Pagination loop
    next_page_token = ""  # Start with empty token
    page_number = 1
    
    try:
        while next_page_token is not None:
            print(f"📖 Processing page {page_number}...")
            
            # Add pagination token to request
            if next_page_token:
                data["page_token"] = next_page_token
            elif "page_token" in data:
                del data["page_token"]  # Remove token for first request
            
            # Make API request
            response = make_api_request(url, headers, data)
            
            if response is None:
                logger.warning(f"Failed to get response for page {page_number}")
                break
            
            # Process response and scan notebooks
            page_start_time = time.time()
            next_page_token = process_search_response(response, results_list, Config.RESULTS_LOG_FILE, 
                                                     current_run_id, workspace_id)
            page_end_time = time.time()
            
            # Update counters
            page_notebooks = len(response.get("results", []))
            total_notebooks_processed += page_notebooks
            
            # Count secrets found in this page
            page_secrets = sum(1 for notebook in results_list[-page_notebooks:] if notebook.get("secrets_found", 0) > 0)
            page_total_secrets = sum(notebook.get("secrets_found", 0) for notebook in results_list[-page_notebooks:])
            notebooks_with_secrets += page_secrets
            total_secrets_found += page_total_secrets
            
            # Only show page summary if secrets were found or if it's a significant milestone
            if page_total_secrets > 0:
                print(f"   ⚠️  Page {page_number}: {page_notebooks} notebooks processed, {page_total_secrets} secrets found in {page_secrets} notebook(s)")
            elif page_number % 10 == 0:  # Show progress every 10 pages
                print(f"   📖 Page {page_number}: {page_notebooks} notebooks processed (no secrets found)")
            
            print()
            
            page_number += 1
            
            # Rate limiting - sleep between API calls
            if next_page_token is not None:
                logger.info(f"Sleeping for {Config.API_SLEEP_SECONDS} seconds to prevent rate limiting...")
                time.sleep(Config.API_SLEEP_SECONDS)
        
        # Final summary
        print("🎉 Secret Scanning Completed!")
        print("=" * 60)
        print(f"📊 Total notebooks processed: {total_notebooks_processed}")
        print(f"🔍 Notebooks with secrets: {notebooks_with_secrets}")
        print(f"🚨 Total secrets detected: {total_secrets_found}")
        
        if notebooks_with_secrets > 0:
            print(f"⚠️  Security Alert: {notebooks_with_secrets} notebook(s) contain potential secrets!")
            print("   Please review the detailed results above and take appropriate action.")
        else:
            print("✅ No secrets detected in any notebooks. Great job!")
        
        print(f"📝 Detailed results logged to: {Config.RESULTS_LOG_FILE}")
        
        # Return summary statistics
        return {
            "total_notebooks": total_notebooks_processed,
            "notebooks_with_secrets": notebooks_with_secrets,
            "total_secrets": total_secrets_found,
            "results": results_list
        }
        
    except KeyboardInterrupt:
        print("\n⏹️  Scanning interrupted by user")
        logger.info("Scanning workflow interrupted by user")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in scanning workflow: {str(e)}")
        print(f"❌ Error occurred during scanning: {str(e)}")
        return None

# Execute the scanning workflow
if __name__ == "__main__":
    scan_results = main_scanning_workflow()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6: Results Analysis and Cleanup
# MAGIC
# MAGIC This cell provides additional analysis of the results and cleanup operations.

# COMMAND ----------

# Results Analysis and Cleanup

# Display scan results summary if available
if 'scan_results' in locals() and scan_results:
    print("📈 Detailed Scan Results Analysis")
    print("=" * 50)
    
    # Group results by secret type
    secret_types = {}
    for notebook in scan_results.get("results", []):
        if notebook.get("secrets_found", 0) > 0:
            for secret in notebook.get("secret_details", []):
                detector_name = secret.get("DetectorName", "Unknown")
                if detector_name not in secret_types:
                    secret_types[detector_name] = 0
                secret_types[detector_name] += 1
    
    if secret_types:
        print("🔍 Secret Types Detected:")
        for secret_type, count in sorted(secret_types.items()):
            print(f"   • {secret_type}: {count} occurrence(s)")
        print()
    
    # Show notebooks with most secrets
    notebooks_by_secrets = sorted(
        [nb for nb in scan_results.get("results", []) if nb.get("secrets_found", 0) > 0],
        key=lambda x: x.get("secrets_found", 0),
        reverse=True
    )
    
    if notebooks_by_secrets:
        print("📚 Top Notebooks with Secrets:")
        for i, notebook in enumerate(notebooks_by_secrets[:5]):  # Show top 5
            print(f"   {i+1}. {notebook.get('name', 'Unknown')} - {notebook.get('secrets_found', 0)} secret(s)")
        print()

# Cleanup and file operations
print("🧹 Cleanup Operations")
print("=" * 30)

# List temporary files created
print("📁 Temporary files in /tmp/notebooks:")

display(notebooks_by_secrets)


# COMMAND ----------

# MAGIC %sh ls -la /tmp/notebooks/ 2>/dev/null || echo "Directory not found or empty"

# COMMAND ----------

print("📄 Configuration files:")

# COMMAND ----------

# MAGIC %sh ls -la /tmp/trufflehog* 2>/dev/null || echo "No TruffleHog config files found"

# COMMAND ----------

print("📊 Results log file:")

# COMMAND ----------

# MAGIC %sh ls -la /tmp/trufflehog_scan_results.json 2>/dev/null || echo "No results log file found"

# COMMAND ----------

print("✅ Cleanup completed. Temporary files will be automatically removed when the cluster terminates.")

# Display final recommendations
print("\n🎯 Next Steps and Recommendations")
print("=" * 40)
print("1. 🔍 Review any detected secrets immediately")
print("2. 🔄 Rotate any exposed credentials")
print("3. 📝 Update notebooks to remove hardcoded secrets")
print("4. 🔐 Use Databricks secrets or environment variables instead")
print("5. 📅 Schedule regular secret scans as part of your security workflow")
print("6. 📋 Consider integrating this scan into your CI/CD pipeline")

if 'scan_results' in locals() and scan_results and scan_results.get("notebooks_with_secrets", 0) > 0:
    print("\n⚠️  IMMEDIATE ACTION REQUIRED:")
    print("   Secrets were detected in your notebooks. Please address them promptly!")
else:
    print("\n✅ No immediate action required - no secrets detected.")

# COMMAND ----------

print(f"TruffleHog Secret Scanner - {time.time() - start_time} seconds to run")
