# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** 7. update_sat_check_configuration.      
# MAGIC **Functionality:** Optional notebooks for updating SAT checks customization.  
# MAGIC
# MAGIC

# COMMAND ----------

# MAGIC %pip install PyYAML

# COMMAND ----------

# MAGIC %run ../Utils/initialize

# COMMAND ----------

# MAGIC %md
# MAGIC ##<img src="https://databricks.com/wp-content/themes/databricks/assets/images/header_logo_2x.png" alt="logo" width="150"/> 
# MAGIC
# MAGIC ## SAT Check Configuration
# MAGIC * <i> This utility helps administrators review their current configuration of SAT checks and modify if needed. </i>
# MAGIC * <b> get_all_sat_checks() </b> 
# MAGIC   * Populates 'SAT Check' drop down widget with all relevant checks for the current cloud type & reset all other widgets
# MAGIC   * Administrator chooses a check from the dropdown list
# MAGIC * <b> get_sat_check_config() </b> 
# MAGIC   * Fetches the specific check details from the database for user to view or modify
# MAGIC * <b> set_all_sat_checks() </b> 
# MAGIC   * Updates Database with user changes to check details

# COMMAND ----------

# MAGIC %run ./../Utils/sat_checks_config

# COMMAND ----------

#Populate 'SAT Check' drop down widget with all relevant checks for the current cloud type & reset all other widgets
get_all_sat_checks()

# COMMAND ----------

#Fetch specific check details from the database for user to view or modify
get_sat_check_config()

# COMMAND ----------

#Update Database with user changes to check details
set_sat_check_config()
#reset widgets
get_all_sat_checks()

# COMMAND ----------


