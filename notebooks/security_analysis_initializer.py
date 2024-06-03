# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** security_analysis_initializer.
# MAGIC **Functionality:** Main notebook to initialize setup of SAT
# MAGIC

# COMMAND ----------

# MAGIC %run ./Includes/install_sat_sdk

# COMMAND ----------

# MAGIC %run ./Utils/initialize

# COMMAND ----------

# MAGIC %run ./Utils/common

# COMMAND ----------

from core.logging_utils import LoggingUtils

LoggingUtils.set_logger_level(LoggingUtils.get_log_level(json_["verbosity"]))
loggr = LoggingUtils.get_logger()

# COMMAND ----------

hostname = (
    dbutils.notebook.entry_point.getDbutils()
    .notebook()
    .getContext()
    .apiUrl()
    .getOrElse(None)
)
cloud_type = getCloudType(hostname)

# COMMAND ----------

if cloud_type == "gcp":
    # generate account level tokens for GCP for connection
    gcp_status1 = dbutils.notebook.run(
        f"{basePath()}/notebooks/Setup/gcp/configure_sa_auth_tokens", 3000
    )
    if gcp_status1 != "OK":
        loggr.exception("Error Encountered in GCP Step#1", gcp_status1)
        dbutils.notebook.exit()


# COMMAND ----------


status1 = dbutils.notebook.run(
    f"{basePath()}/notebooks/Setup/1. list_account_workspaces_to_conf_file", 3000
)
if status1 != "OK":
    loggr.exception("Error Encountered in Step#1", status1)
    dbutils.notebook.exit()
status3 = dbutils.notebook.run(
    f"{basePath()}/notebooks/Setup/3. test_connections", 12000
)
if status3 != "OK":
    loggr.exception("Error Encountered in Step#3", status3)
    dbutils.notebook.exit()

status4 = dbutils.notebook.run(
    f"{basePath()}/notebooks/Setup/4. enable_workspaces_for_sat", 3000
)
if status4 != "OK":
    loggr.exception("Error Encountered in Step#4", status4)
    dbutils.notebook.exit()

status5 = dbutils.notebook.run(
    f"{basePath()}/notebooks/Setup/5. import_dashboard_template", 3000
)
if status5 != "OK":
    loggr.exception("Error Encountered in Step#5", status5)
    dbutils.notebook.exit()

status5_1 = dbutils.notebook.run(
    f"{basePath()}/notebooks/Setup/5. import_dashboard_template_lakeview", 3000
)
if status5_1 != "OK":
    loggr.exception("Error Encountered in Step#5_1", status5_1)
    dbutils.notebook.exit()

status6 = dbutils.notebook.run(
    f"{basePath()}/notebooks/Setup/6. configure_alerts_template", 3000
)
if status6 != "OK":
    loggr.exception("Error Encountered in Step#6", status6)
    dbutils.notebook.exit()

# COMMAND ----------

# MAGIC %md
# MAGIC Read manual self assesment file and load workspace configurations for analysis

# COMMAND ----------

# DBTITLE 0,%md Running Manual SAT Checks here (/notebooks/setup/update_workspace_configurations)

status9 = dbutils.notebook.run(
    f"{basePath()}/notebooks/Setup/9. self_assess_workspace_configuration", 3000
    )
if (status9 != 'OK'):
    loggr.exception('Error Encountered in Step#9', status9)
    dbutils.notebook.exit()
