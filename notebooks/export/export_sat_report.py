# Databricks notebook source
# MAGIC %md
# MAGIC ###Use this notebook to export your SAT findings. 
# MAGIC Run the notebook and downlod the cell content as a CSV  from the Table below

# COMMAND ----------

# DBTITLE 0,Use this notebook to export your SAT findings. Run the notebook and downlod the cell content as a CSV  from the Table below
# MAGIC %sql
# MAGIC select
# MAGIC   workspace_id,
# MAGIC   BP.check_id,
# MAGIC   BP.severity,
# MAGIC   CASE
# MAGIC     WHEN score = 1  THEN 'FAIL'
# MAGIC     WHEN score = 0 THEN 'PASS'
# MAGIC   END as status,  
# MAGIC   chk_date as RunDate,
# MAGIC   BP.recommendation,
# MAGIC   BP.doc_url,
# MAGIC   BP.logic,
# MAGIC   BP.api,
# MAGIC   SC.additional_details
# MAGIC from
# MAGIC   (
# MAGIC     select
# MAGIC       workspace_id,
# MAGIC       max(run_id) as run_id
# MAGIC     from
# MAGIC       security_analysis.workspace_run_complete
# MAGIC     where
# MAGIC       completed = true
# MAGIC     group by
# MAGIC       workspace_id
# MAGIC   ) as lastest_run,
# MAGIC   security_analysis.security_checks SC,
# MAGIC   security_analysis.security_best_practices BP
# MAGIC
# MAGIC Where
# MAGIC   sc.run_id = lastest_run.run_id
# MAGIC   and sc.workspaceid = lastest_run.workspace_id
# MAGIC   and   SC.id = BP.id
# MAGIC order by workspace_id
