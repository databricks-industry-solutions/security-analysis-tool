# Databricks notebook source
# MAGIC %sql
# MAGIC select * from `global_temp`.`unitycatalogmsv1_1657683783405196`;

# COMMAND ----------

# MAGIC %sql select * from `global_temp`.`unitycatalogmsv2_1657683783405196`;

# COMMAND ----------

# MAGIC %sql select * from `global_temp`.`unitycatalogexternallocations_1657683783405196`;

# COMMAND ----------

# MAGIC %sql select * from `global_temp`.`unitycatalogcredentials_1657683783405196`;

# COMMAND ----------

# MAGIC %sql select * from `global_temp`.`unitycatalogshares_1657683783405196`;

# COMMAND ----------

# MAGIC %sql select * from `global_temp`.`unitycatalogshareproviders_1657683783405196`;

# COMMAND ----------

# MAGIC %sql select * from `global_temp`.`unitycatalogsharerecipients_1657683783405196`;

# COMMAND ----------

# MAGIC %sql select * from `global_temp`.`unitycatalogcatlist_1657683783405196`;

# COMMAND ----------

# MAGIC %sql select * from `global_temp`.`endpoints_1657683783405196`;

# COMMAND ----------

# MAGIC %sql select * from `global_temp`.`dbsql_alerts_1657683783405196`;

# COMMAND ----------

# MAGIC %sql select * from `global_temp`.`dbsql_warehouselist_1657683783405196`;

# COMMAND ----------

# MAGIC %sql select explode(warehouses) as warehouse from `global_temp`.`dbsql_warehouselistv2_1657683783405196`;

# COMMAND ----------

# MAGIC %sql select * from `global_temp`.`dbsql_workspaceconfig_1657683783405196`;

# COMMAND ----------

# MAGIC %sql  
# MAGIC -- Check serverless is used in the workspace
# MAGIC select warehouse.* from (select explode(warehouses) as warehouse from `global_temp`.`dbsql_warehouselistv2_1657683783405196`) where warehouse.enable_serverless_compute = true ;

# COMMAND ----------

# MAGIC %sql  
# MAGIC --Check UC is not used in the workspace
# MAGIC select warehouse.* from (select explode(warehouses) as warehouse from `global_temp`.`dbsql_warehouselistv2_1657683783405196`) where warehouse.disable_uc = true;

# COMMAND ----------

# MAGIC %sql  
# MAGIC --Check Delta sharing has token expiration set 
# MAGIC select *  from `global_temp`.`unitycatalogmsv1_1657683783405196` where delta_sharing_recipient_token_lifetime_in_seconds < 7776000;

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Check if there are any token based sharing without IP access lists ip_access_list and or token expiration 
# MAGIC select *, explode(tokens) from `global_temp`.`unitycatalogsharerecipients_1657683783405196` where authentication_type = 'TOKEN' 

# COMMAND ----------

# MAGIC %sql
# MAGIC -- show current owner 
# MAGIC select * from `global_temp`.`unitycatalogmsv1_1657683783405196`;

# COMMAND ----------

# MAGIC %sql 
# MAGIC --Databricks recommends using external locations rather than using storage credentials directly.
# MAGIC select * from `global_temp`.`unitycatalogcredentials_1657683783405196`;

# COMMAND ----------

# MAGIC %sql 
# MAGIC -- show recipients as informational
# MAGIC select * from `global_temp`.`unitycatalogsharerecipients_1657683783405196`;

# COMMAND ----------

# MAGIC %sql
# MAGIC -- count and show existing metastore, if no UC catalog provide informational deviation
# MAGIC select name,owner, * from `global_temp`.`unitycatalogmsv1_1657683783405196`;

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
# MAGIC select * from `global_temp`.`unitycatalogmsv2_1657683783405196` where workspace_id='1657683783405196';

# COMMAND ----------

# MAGIC %sql
# MAGIC --Check Delta sharing has token expiration set for given metastore
# MAGIC select * from `global_temp`.`unitycatalogmsv1_1657683783405196` where delta_sharing_scope ="INTERNAL_AND_EXTERNAL" and delta_sharing_recipient_token_lifetime_in_seconds <=7776000

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Check if there are any token based sharing without IP access lists ip_access_list
# MAGIC select *  from `global_temp`.`unitycatalogsharerecipients_1657683783405196` where authentication_type = 'TOKEN' and ip_access_list is NULL

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Check if there are any token based sharing without expiration or expired or too far into the future
# MAGIC --select tokens.* from (select explode(tokens) as tokens from `global_temp`.`unitycatalogsharerecipients_1657683783405196` where authentication_type = 'TOKEN')   where tokens.expiration_time is NULL  or (tokens.expiration_time <= current_timestamp() or tokens.expiration_time >= ) 
# MAGIC 
# MAGIC select  tokens.* from (select explode(tokens) as tokens, full_name, owner from `global_temp`.`unitycatalogsharerecipients_1657683783405196` Zwhere authentication_type = 'TOKEN')   where tokens.expiration_time is NULL 

# COMMAND ----------

# MAGIC %sql
# MAGIC -- The is there a metastore ?
# MAGIC select name, owner from `global_temp`.`unitycatalogmsv1_1657683783405196` where securable_type = 'METASTORE'

# COMMAND ----------

# MAGIC %sql
# MAGIC -- The current owner is account admin ?
# MAGIC select * from `global_temp`.`unitycatalogmsv1_1657683783405196` where securable_type = 'METASTORE' and owner == created_by; 

# COMMAND ----------

# MAGIC %sql
# MAGIC --Databricks recommends using external locations rather than using storage credentials directly.
# MAGIC select * from `global_temp`.`unitycatalogcredentials_1657683783405196` where securable_type = "STORAGE_CREDENTIAL" ;

# COMMAND ----------

# MAGIC %sql  
# MAGIC --Check UC is not used in the workspace
# MAGIC select warehouse.name as name , warehouse.creator_name as creator_name  from (select explode(warehouses) as warehouse from `global_temp`.`dbsql_warehouselistv2_1657683783405196`) where warehouse.disable_uc = true;

# COMMAND ----------

# MAGIC %sql
# MAGIC --serverless enabled
# MAGIC select * from `global_temp`.`dbsql_workspaceconfig_1657683783405196` where enable_serverless_compute = true

# COMMAND ----------

# MAGIC %sql
# MAGIC      SELECT warehouse.name as name , warehouse.creator_name as creator_name  from (select explode(warehouses) as warehouse  
# MAGIC      FROM `global_temp`.`dbsql_warehouselistv2_1657683783405196`)   where warehouse.disable_uc = true
# MAGIC         
# MAGIC --select warehouse.name as name , warehouse.creator_name as creator_name  from (select explode(warehouses) as warehouse from `global_temp`.`dbsql_warehouselistv2_1657683783405196`) where warehouse.disable_uc = true;  
