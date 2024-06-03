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
LoggingUtils.set_logger_level(LoggingUtils.get_log_level(json_['verbosity']))
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
    mastername = dbutils.secrets.get(json_['master_name_scope'], json_['master_name_key'])
    masterpwd = dbutils.secrets.get(json_['master_pwd_scope'], json_['master_pwd_key'])
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

bootstrap('acctworkspaces', acct_client.get_workspace_list)

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Get List of Credentials

# COMMAND ----------

bootstrap('acctcredentials', acct_client.get_credentials_list)

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Get List of Network

# COMMAND ----------

bootstrap('acctnetwork', acct_client.get_network_list)

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Get List of Storage Configs

# COMMAND ----------

bootstrap('acctstorage', acct_client.get_storage_list)

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Get List of Customer Managed Keys

# COMMAND ----------

bootstrap('acctcmk', acct_client.get_cmk_list)

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Get Log Delivery Configurations

# COMMAND ----------

bootstrap('acctlogdelivery', acct_client.get_logdelivery_list)

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Get Privatelink Information

# COMMAND ----------

bootstrap('acctpvtlink', acct_client.get_privatelink_info)

# COMMAND ----------

from clientpkgs.accounts_settings import AccountsSettings

try:
    acct_settings = AccountsSettings(json_)
except Exception:
    loggr.exception("Exception encountered")

# COMMAND ----------

bootstrap('account_ipaccess_list', acct_settings.get_ipaccess_list)

# COMMAND ----------

bootstrap('account_csp', acct_settings.get_compliancesecurityprofile)

# COMMAND ----------

bootstrap('account_ncc', acct_settings.get_networkconnectivityconfigurations)

# COMMAND ----------

print(f"Account Bootstrap - {time.time() - start_time} seconds to run")
