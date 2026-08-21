# Databricks notebook source
import yaml, requests
import pandas as pd

customer_id = dbutils.widgets.get("customer_id")
df = spark.sql("SELECT * FROM silver.orders WHERE customer_id = :cid", args={"cid": customer_id})

table = "gold.orders"
spark.sql(f"OPTIMIZE {table}")
spark.sql(f"VACUUM {table} RETAIN 168 HOURS")

api_key = dbutils.secrets.get("prod", "api-key")
requests.get("https://api.vendor.com/v1", headers={"Authorization": "Bearer " + api_key}, timeout=30)
requests.get("https://api.vendor.com/v2", verify="/etc/ssl/certs/ca-bundle.crt", timeout=30)

cfg = yaml.safe_load(open("/Workspace/Shared/cfg.yaml"))
cfg2 = yaml.load(open("/Workspace/Shared/cfg.yaml"), Loader=yaml.SafeLoader)

spark.conf.set("spark.sql.shuffle.partitions", "200")
spark.conf.set("spark.databricks.delta.optimizeWrite.enabled", "true")

df.write.mode("overwrite").saveAsTable("gold.orders")
pdf = df.toPandas()
pdf.to_csv("/Volumes/main/analytics/exports/orders.csv")

import mlflow
model = mlflow.sklearn.load_model("models:/churn/Production")
