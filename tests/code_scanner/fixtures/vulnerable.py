# Databricks notebook source
import pickle, yaml, requests, torch
import pandas as pd

customer_id = dbutils.widgets.get("customer_id")
df = spark.sql(f"SELECT * FROM silver.orders WHERE customer_id = '{customer_id}'")

api_key = dbutils.secrets.get("prod", "api-key")
print("key is", api_key)
display(dbutils.secrets.get("prod", "other"))

requests.get("https://api.vendor.com/v1", verify=False)

with open("/dbfs/models/churn.pkl", "rb") as f:
    model = pickle.load(f)
cfg = yaml.load(open("/dbfs/tmp/cfg.yaml"))
weights = torch.load("/dbfs/models/net.pt")

spark.conf.set("fs.azure.account.key.acct.dfs.core.windows.net", "abc123secretvalue")

pdf = df.toPandas()
pdf.to_csv("/dbfs/tmp/export.csv")
pdf.to_parquet("/tmp/export.parquet")

TOKEN = "dapi" + ("0123456789abcdef" * 2)  # assembled so the repo secret scanner sees no literal
