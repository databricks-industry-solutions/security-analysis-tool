#--------------****************--------------
#---SENSITIVE FILE. May contain Personal Access Tokens. Please secure---

curl --netrc --request POST 'https://oregon.cloud.databricks.com/api/2.0/secrets/put' -d '{"scope":"sat_master_scope", "key":"sat_token_1657683783405196", "string_value":"<dapireplace>"}'
curl --netrc --request GET 'https://oregon.cloud.databricks.com/api/2.0/secrets/list?scope=sat_master_scope'
