# Databricks notebook source
# MAGIC %md
# MAGIC **Functionality:** Initializes the Security Analysis Tool (SAT) schema and tables.

# COMMAND ----------

# The SAT app provisions collection as per-workspace jobs and has its own UI, so
# the initializer's only responsibility is to create the SAT schema and its
# tables -- done by the %run of Utils/initialize below. The classic
# multi-workspace setup (account enumeration, connection tests, Lakeview
# dashboard import) and the driver cleanup are not part of the app.

# COMMAND ----------

# MAGIC %run ./Includes/install_sat_sdk

# COMMAND ----------

# MAGIC %run ./Utils/initialize

# COMMAND ----------

# MAGIC %run ./Utils/common
