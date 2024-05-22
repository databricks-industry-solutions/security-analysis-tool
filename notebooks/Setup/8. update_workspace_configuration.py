# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** 8. update_workspace_configuration.      
# MAGIC **Functionality:** Optional notebooks for updating SAT workspace customization. 

# COMMAND ----------

# MAGIC %pip install PyYAML

# COMMAND ----------

# MAGIC %run ../Utils/initialize

# COMMAND ----------

# MAGIC %md
# MAGIC ##<img src="https://databricks.com/wp-content/themes/databricks/assets/images/header_logo_2x.png" alt="logo" width="150"/> 
# MAGIC
# MAGIC ## Workspace Configuration
# MAGIC * <i> This utility helps administrators review their current configuration of SAT checks and modify if needed. </i>
# MAGIC * <b> get_all_workspaces() </b> 
# MAGIC   * Populates 'Workspaces' drop down widget with all workspaces 
# MAGIC   * Administrator chooses one from the dropdown list
# MAGIC * <b> get_workspace_check_config() </b> 
# MAGIC   * Fetches the specific check details from the database for user to view or modify
# MAGIC * <b> get_workspace_check_config() </b> 
# MAGIC   * Updates Database with user changes to workspace level checks

# COMMAND ----------

# MAGIC %run ./../Utils/sat_checks_config

# COMMAND ----------

#Populates 'Workspaces' drop down widget with all workspaces
get_all_workspaces()

# COMMAND ----------

#Fetches the specific check details from the database for user to view or modify
get_workspace_check_config()

# COMMAND ----------

#Updates Database with user changes to workspace level checks
set_workspace_check_config()
#reset widgets
get_all_workspaces()

# COMMAND ----------


