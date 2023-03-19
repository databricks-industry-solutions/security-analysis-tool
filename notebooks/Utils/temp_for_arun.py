# Databricks notebook source
# MAGIC %sql
# MAGIC select * from `global_temp`.`unitycatalogmsv1`;

# COMMAND ----------

# MAGIC %sql select * from `global_temp`.`unitycatalogmsv2`;

# COMMAND ----------

# MAGIC %sql select * from `global_temp`.`unitycatalogexternallocations`;

# COMMAND ----------

# MAGIC %sql select * from `global_temp`.`unitycatalogcredentials`;

# COMMAND ----------

# MAGIC %sql select * from `global_temp`.`unitycatalogshares`;

# COMMAND ----------

# MAGIC %sql select * from `global_temp`.`unitycatalogshareproviders`;

# COMMAND ----------

# MAGIC %sql select * from `global_temp`.`unitycatalogsharerecipients`;

# COMMAND ----------

# MAGIC %sql select * from `global_temp`.`unitycatalogcatlist`;

# COMMAND ----------

# MAGIC %sql select * from `global_temp`.`endpoints`;

# COMMAND ----------

# MAGIC %sql select * from `global_temp`.`dbsql_alerts`;

# COMMAND ----------

# MAGIC %sql select * from `global_temp`.`dbsql_warehouselist`;

# COMMAND ----------

# MAGIC %sql select explode(warehouses) as warehouse from `global_temp`.`dbsql_warehouselistv2`;

# COMMAND ----------

# MAGIC %sql select * from `global_temp`.`dbsql_workspaceconfig`;

# COMMAND ----------


