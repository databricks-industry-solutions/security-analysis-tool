# Databricks notebook source
# MAGIC %md
# MAGIC ##<img src="https://databricks.com/wp-content/themes/databricks/assets/images/header_logo_2x.png" alt="logo" width="150"/> 
# MAGIC
# MAGIC ## Self Assessment of Workspace Configurations
# MAGIC * <b> This utility helps customers self assess configurations across all workspaces by using the self_assessment_checks.yaml file in config folder. </b>
# MAGIC
# MAGIC
# MAGIC * <b> The configs are processed during the initialization phase of SAT</b> 
# MAGIC * <b> You can update the self_assessment_checks.yaml file anytime and rerun this notebook and run the driver notebook or job to see the updated report as per the latest values in self_assessment_checks.yaml </b> 
# MAGIC  

# COMMAND ----------

# MAGIC %pip install PyYAML

# COMMAND ----------

# MAGIC %run ../Utils/initialize

# COMMAND ----------

# MAGIC %run ../Utils/sat_checks_config

# COMMAND ----------

#Fetches the specific check details from the YAML file
checks_data=get_workspace_self_assessment_check_config()


# COMMAND ----------

#Updates Database with user self asseements to all workspace level checks
set_workspace_self_assessment_check_config(checks_data)



# COMMAND ----------

dbutils.notebook.exit('OK')
