# Databricks notebook source
# MAGIC %md
# MAGIC ###Use this notebook to export your SAT findings. 
# MAGIC Run the notebook and downlod the cell content as a CSV  from the Table below

# COMMAND ----------

# MAGIC %run ../Utils/initialize

# COMMAND ----------

display(
    spark.sql(
        f"select workspace_id, BP.check_id, BP.severity, CASE WHEN score = 1  THEN 'FAIL' WHEN score = 0 THEN 'PASS' END as status,chk_date as RunDate, BP.recommendation, BP.doc_url, BP.logic, BP.api,SC.additional_details from (select workspace_id, max(run_id) as run_id from {json_['analysis_schema_name']}.workspace_run_complete where completed = true group by workspace_id   ) as lastest_run, {json_['analysis_schema_name']}.security_checks SC, {json_ ['analysis_schema_name']}.security_best_practices BP Where sc.run_id = lastest_run.run_id and sc.workspaceid = lastest_run.workspace_id and SC.id = BP.id order by workspace_id" )
)
