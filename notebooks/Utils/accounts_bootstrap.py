# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** accounts_bootstrap      
# MAGIC **Functionality:** Notebook that queries the account level APIs and creates temp tables with the results.  

# COMMAND ----------

# MAGIC %run ../Includes/install_sat_sdk

# COMMAND ----------

import time
start_time = time.time()

# COMMAND ----------

# MAGIC %run ./common

# COMMAND ----------

test=False #local testing
if test:
    jsonstr = JSONLOCALTEST
    originstr = 'driver'
else:
    jsonstr = dbutils.widgets.get('json_')
    originstr = dbutils.widgets.get('origin')

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
json_.update({"cloud_type": cloud_type})

# Account-level SAT checks that consume collectors in this notebook.
# Azure GOV-3 (8) is collected in workspace_bootstrap, not here.
_account_check_ids = ["3", "35", "36", "39", "103", "110", "111", "112", "119", "122", "124"]
if cloud_type != "azure":
    _account_check_ids.append("8")
need_account_collectors = any_check_enabled(*_account_check_ids, cloud_type=cloud_type)

# COMMAND ----------

# Skip account APIs when the driver has no enabled account-level checks.
# Setup initializer still needs a connection and the workspace list.
if (originstr == "driver" or test) and not need_account_collectors:
    loggr.info("Skipping account API collection; no enabled account-level checks")
    print(f"Account Bootstrap skipped - {time.time() - start_time} seconds")
    dbutils.notebook.exit("Account Bootstrap skipped; no enabled account-level checks")

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
else: # Populate the master key for the Accounts API
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
# MAGIC ##### Connection Test

# COMMAND ----------

is_successful_acct=False
try:
  is_successful_acct = db_client.test_connection(master_acct=True)
  if is_successful_acct == True:
      loggr.info("Account Connection successful!")
  else:
      loggr.info("Unsuccessful account connection. Verify credentials.") 
except requests.exceptions.RequestException as e:
  is_successful_acct = False  
  loggr.exception('Unsuccessful connection. Verify credentials.')
  loggr.exception(e)
except Exception:
  is_successful_acct = False
  loggr.exception("Exception encountered")

# COMMAND ----------

if not is_successful_acct:
  raise Exception('Unsuccessful account connection. Verify credentials.')

# COMMAND ----------

spark.sql(f"USE {json_['intermediate_schema']}")

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Accounts

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Initialize Accounts API

# COMMAND ----------

from clientpkgs.accounts_client import AccountsClient

try:
    acct_client = AccountsClient(json_)
except Exception:
    loggr.exception("Exception encountered")

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Get List of Workspaces

# COMMAND ----------

# if azure then get workspaces and exit. We will do the rest during the driver run
# if local testing then lets run it and not exit.
if originstr == 'initializer' and not test:
    bootstrap('acctworkspaces', acct_client.get_workspace_list)
    dbutils.notebook.exit('Account Initialization Complete')
if originstr == 'driver' or test: # we need this during driver for workspace settings
    if any_check_enabled("3", "35", "36", "39", "111", "122", cloud_type=cloud_type):
        bootstrap('acctworkspaces', acct_client.get_workspace_list)
    else:
        loggr.info("Skipping acctworkspaces; related checks are disabled")


# COMMAND ----------

# MAGIC %md
# MAGIC ##### Get List of Credentials

# COMMAND ----------

# No SAT check reads this table. Left commented for reference.
# bootstrap('acctcredentials', acct_client.get_credentials_list)
loggr.info("Skipping acctcredentials; no SAT check uses this collector")

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Get List of Network

# COMMAND ----------

# No SAT check reads this table. Left commented for reference.
# bootstrap('acctnetwork', acct_client.get_network_list)
loggr.info("Skipping acctnetwork; no SAT check uses this collector")

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Get List of Storage Configs

# COMMAND ----------

# No SAT check reads this table. Left commented for reference.
# bootstrap('acctstorage', acct_client.get_storage_list)
loggr.info("Skipping acctstorage; no SAT check uses this collector")

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Get List of Customer Managed Keys

# COMMAND ----------

# No SAT check reads this table. Left commented for reference.
# bootstrap('acctcmk', acct_client.get_cmk_list)
loggr.info("Skipping acctcmk; no SAT check uses this collector")

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Get Log Delivery Configurations

# COMMAND ----------

# only for azure. we go through the management api that does it on a workspace level
if cloud_type !='azure' and any_check_enabled("8", cloud_type=cloud_type):
    bootstrap('acctlogdelivery', acct_client.get_logdelivery_list)
elif cloud_type !='azure':
    loggr.info("Skipping acctlogdelivery; GOV-3 is disabled")

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Get Privatelink Information

# COMMAND ----------

# No SAT check reads this table. Left commented for reference.
# bootstrap('acctpvtlink', acct_client.get_privatelink_info)
loggr.info("Skipping acctpvtlink; no SAT check uses this collector")

# COMMAND ----------

from clientpkgs.accounts_settings import AccountsSettings

try:
    acct_settings = AccountsSettings(json_)
except Exception:
    loggr.exception("Exception encountered")

# COMMAND ----------

if any_check_enabled("110", "124", cloud_type=cloud_type):
    bootstrap('account_ipaccess_list', acct_settings.get_ipaccess_list)
else:
    loggr.info("Skipping account_ipaccess_list; NS-8/NS-13 are disabled")

# COMMAND ----------

if any_check_enabled("103", cloud_type=cloud_type):
    bootstrap('account_csp', acct_settings.get_compliancesecurityprofile)
else:
    loggr.info("Skipping account_csp; INFO-38 is disabled")

# COMMAND ----------

# No SAT check reads this table. Left commented for reference.
# bootstrap('account_ncc', acct_settings.get_networkconnectivityconfigurations)
loggr.info("Skipping account_ncc; no SAT check uses this collector")

# COMMAND ----------

# Custom bootstrap for network policies with explicit schema to ensure dry_run_mode_product_filter is captured
from pyspark.sql.types import StructType, StructField, StringType, ArrayType
from pyspark.sql.functions import col, from_json
import json

# Define explicit schema matching API documentation
network_policy_schema = StructType([
    StructField("account_id", StringType(), True),
    StructField("network_policy_id", StringType(), True),
    StructField("egress", StructType([
        StructField("network_access", StructType([
            StructField("restriction_mode", StringType(), True),
            StructField("policy_enforcement", StructType([
                StructField("enforcement_mode", StringType(), True),
                StructField("dry_run_mode_product_filter", ArrayType(StringType()), True)  # EXPLICIT!
            ]), True),
            StructField("allowed_storage_destinations", ArrayType(StructType([
                StructField("bucket_name", StringType(), True),
                StructField("region", StringType(), True),
                StructField("storage_destination_type", StringType(), True)
            ])), True),
            StructField("allowed_internet_destinations", ArrayType(StructType([
                StructField("destination", StringType(), True),
                StructField("internet_destination_type", StringType(), True)
            ])), True)
        ]), True)
    ]), True),
    # Ingress enforcement is represented structurally, not via an
    # enforcement_mode sub-field: the API puts the ingress block under
    # `ingress` when the policy is set to "Enforced for all products", and
    # under `ingress_dry_run` (same nested shape) when set to "Dry run mode
    # for all products". A policy with no CBI configured has neither key
    # populated. Capture both so NS-12 can read whichever one applies.
    StructField("ingress", StructType([
        StructField("public_access", StructType([
            StructField("restriction_mode", StringType(), True)
        ]), True)
    ]), True),
    StructField("ingress_dry_run", StructType([
        StructField("public_access", StructType([
            StructField("restriction_mode", StringType(), True)
        ]), True)
    ]), True)
])

if any_check_enabled("111", "122", cloud_type=cloud_type):
    try:
        # Get policies from API
        policies_list = acct_settings.get_networkpolicies()
        if policies_list:
            # Convert to JSON strings
            json_strings = [json.dumps(p) for p in policies_list]
            # Create DataFrame with explicit schema
            policies_df = spark.createDataFrame([(x,) for x in json_strings], ["json_string"])
            policies_df = policies_df.select(from_json(col("json_string"), network_policy_schema).alias("data")).select("data.*")
            # Save as table
            policies_df.write.option("delta.columnMapping.mode", "name").mode("overwrite").saveAsTable('account_networkpolicies')
            loggr.info(f"Table created: `account_networkpolicies` with explicit schema including dry_run_mode_product_filter")
        else:
            from pyspark.sql.types import StructType as EmptyStructType
            apiDF = spark.createDataFrame([], EmptyStructType([]))
            apiDF.write.option("delta.columnMapping.mode", "name").mode("overwrite").saveAsTable('account_networkpolicies')
            loggr.info("No network policies found")
    except Exception:
        loggr.exception("Exception encountered while bootstrapping network policies")
else:
    loggr.info("Skipping account_networkpolicies; NS-9/NS-12 are disabled")

# COMMAND ----------

# Collect workspace network configurations
# This links workspaces to their assigned network policies
# Scope to SAT-enabled workspaces only (account_workspaces.analysis_enabled=true),
# matching the driver's own workspace iteration at
# security_analysis_driver.py:68 and avoiding N API calls for unused workspaces.
if any_check_enabled("111", "122", cloud_type=cloud_type):
    try:
        schema = json_['analysis_schema_name']
        workspaces = spark.sql(
            f"SELECT workspace_id FROM {schema}.account_workspaces "
            f"WHERE analysis_enabled = true"
        ).collect()
        loggr.info(f"Collecting network configurations for {len(workspaces)} SAT-enabled workspaces")
        for ws in workspaces:
            workspace_id = str(ws.workspace_id)
            try:
                bootstrap(f'workspace_network_config_{workspace_id}',
                          lambda wid=workspace_id: acct_settings.get_workspace_network_configuration(wid))
            except Exception as e:
                loggr.warning(f"Could not collect network config for workspace {workspace_id}: {e}")
    except Exception as e:
        loggr.warning(f"Could not collect workspace network configurations: {e}")
else:
    loggr.info("Skipping workspace_network_config; NS-9/NS-12 are disabled")

# COMMAND ----------

if any_check_enabled("112", cloud_type=cloud_type):
    bootstrap('account_disable_legacy_features', acct_settings.get_disablelegacyfeatures)
else:
    loggr.info("Skipping account_disable_legacy_features; GOV-37 is disabled")

# COMMAND ----------

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Get Service Principal Secrets

# COMMAND ----------

from clientpkgs.accounts_oauth import AccountsOAuth

if any_check_enabled("119", cloud_type=cloud_type):
    try:
        acct_oauth = AccountsOAuth(json_)
        sp_list = acct_oauth.get_account_service_principals()
        sp_secrets_all = []
        for sp in sp_list:
            sp_id = str(sp.get('id', ''))
            sp_display_name = sp.get('displayName', '')
            sp_app_id = str(sp.get('applicationId', ''))
            try:
                secrets = acct_oauth.get_service_principal_secrets(sp_id)
                for secret in secrets:
                    secret['sp_id'] = sp_id
                    secret['sp_display_name'] = sp_display_name
                    secret['sp_app_id'] = sp_app_id
                    sp_secrets_all.append(secret)
            except Exception as e:
                loggr.warning(f"Could not fetch secrets for SP {sp_id} ({sp_display_name}): {e}")
        if sp_secrets_all:
            sp_secrets_json = [json.dumps(s) for s in sp_secrets_all]
            sp_secrets_df = spark.read.json(spark.sparkContext.parallelize(sp_secrets_json))
            sp_secrets_df.write.option("delta.columnMapping.mode", "name").mode("overwrite").saveAsTable('acctserviceprincipalssecrets')
            loggr.info(f"Table created: `acctserviceprincipalssecrets` with {len(sp_secrets_all)} secret records")
        else:
            from pyspark.sql.types import StructType as EmptyStructType
            spark.createDataFrame([], EmptyStructType([])).write.option("delta.columnMapping.mode", "name").mode("overwrite").saveAsTable('acctserviceprincipalssecrets')
            loggr.info("No service principal secrets found")
    except Exception:
        loggr.exception("Exception encountered while bootstrapping SP secrets")
else:
    loggr.info("Skipping acctserviceprincipalssecrets; IA-9 is disabled")

# COMMAND ----------

print(f"Account Bootstrap - {time.time() - start_time} seconds to run")
