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

# MAGIC %sql  
# MAGIC -- Check serverless is used in the workspace
# MAGIC select warehouse.* from (select explode(warehouses) as warehouse from `global_temp`.`dbsql_warehouselistv2`) where warehouse.enable_serverless_compute = true ;

# COMMAND ----------

# MAGIC %sql  
# MAGIC --Check UC is not used in the workspace
# MAGIC select warehouse.* from (select explode(warehouses) as warehouse from `global_temp`.`dbsql_warehouselistv2`) where warehouse.disable_uc = true;

# COMMAND ----------

# MAGIC %sql  
# MAGIC --Check Delta sharing has token expiration set 
# MAGIC select *  from `global_temp`.`unitycatalogmsv1` where delta_sharing_recipient_token_lifetime_in_seconds < 7776000;

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Check if there are any token based sharing without IP access lists ip_access_list and or token expiration 
# MAGIC select *, explode(tokens) from `global_temp`.`unitycatalogsharerecipients` where authentication_type = 'TOKEN' 

# COMMAND ----------

# MAGIC %sql
# MAGIC -- show current owner 
# MAGIC select * from `global_temp`.`unitycatalogmsv1`;

# COMMAND ----------

# MAGIC %sql 
# MAGIC --Databricks recommends using external locations rather than using storage credentials directly.
# MAGIC select * from `global_temp`.`unitycatalogcredentials`;

# COMMAND ----------

# MAGIC %sql 
# MAGIC -- show recipients as informational
# MAGIC select * from `global_temp`.`unitycatalogsharerecipients`;

# COMMAND ----------

# MAGIC %sql
# MAGIC -- count and show existing metastore, if no UC catalog provide informational deviation
# MAGIC select name,owner, * from `global_temp`.`unitycatalogmsv1`;

# COMMAND ----------

"""1) Is UC used check : count and show existing metastore, if no UC catalog provide informational deviation
2) --Check Delta sharing has token expiration set for given metastore
3) -- Check if there are any token based sharing without IP access lists ip_access_list and or token expiration 
4) -- show current owner is not the metastore creator
5) -- show recipients as informational
6) -- Databricks recommends using external locations rather than using storage credentials directly.
7)  find who has CREATE_RECIPIENT and CREATE_SHARE permissions on metastore. 
8) Check for any tokens that needs to recycled based on 2 & 3
9) DW that don't have UC enabled. """


# COMMAND ----------

# MAGIC %sql
# MAGIC -- 1) count and show existing metastore for this workspace
# MAGIC select * from `global_temp`.`unitycatalogmsv2` where workspace_id='1657683783405196';

# COMMAND ----------

# MAGIC %sql
# MAGIC --Check Delta sharing has token expiration set for given metastore
# MAGIC select * from `global_temp`.`unitycatalogmsv1` where delta_sharing_scope ="INTERNAL_AND_EXTERNAL" and delta_sharing_recipient_token_lifetime_in_seconds > 7776000

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Check if there are any token based sharing without IP access lists ip_access_list
# MAGIC select *  from `global_temp`.`unitycatalogsharerecipients` where authentication_type = 'TOKEN' and ip_access_list != null

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Check if there are any token based sharing without expiration
# MAGIC select tokens.* from (select explode(tokens) as tokens from `global_temp`.`unitycatalogsharerecipients`)  where tokens.expiration_time !=null

# COMMAND ----------

# MAGIC %sql
# MAGIC -- The current owner is account admin ?
# MAGIC select * from `global_temp`.`unitycatalogmsv1` where securable_type = 'METASTORE' and owner != created_by; 

# COMMAND ----------

# MAGIC %sql
# MAGIC --Databricks recommends using external locations rather than using storage credentials directly.
# MAGIC select * from `global_temp`.`unitycatalogcredentials` where securable_type = "STORAGE_CREDENTIAL" ;

# COMMAND ----------

# MAGIC %sql  
# MAGIC --Check UC is not used in the workspace
# MAGIC select warehouse.* from (select explode(warehouses) as warehouse from `global_temp`.`dbsql_warehouselistv2`) where warehouse.disable_uc = true;

# COMMAND ----------

# MAGIC %sql
# MAGIC --serverless enabled
# MAGIC select * from `global_temp`.`dbsql_workspaceconfig` where enable_serverless_compute != true
