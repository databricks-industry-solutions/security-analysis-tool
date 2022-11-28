#!/bin/bash
#This script sets up the accounts API and workpsace API tokens into Databricks secrets. 
#This script follows GCP and Databricks documentation here: https://docs.gcp.databricks.com/dev-tools/api/latest/authentication-google-id-account-private-preview.html


read -p "Please enter path to service account key file path (SA-1-key.json):" cred_file
cred_file=${cred_file:-SA-1-key.json}
echo "Authenticating with ${cred_file}."
./google-cloud-sdk/bin/gcloud auth login --cred-file=$cred_file  

read -p "Please enter impersonate service account :" impersonate_service_account
echo "Generating identity-token for https://accounts.gcp.databricks.com with  ${impersonate_service_account}."
identity_token=$(./google-cloud-sdk/bin/gcloud auth print-identity-token --impersonate-service-account="$impersonate_service_account" --include-email --audiences="https://accounts.gcp.databricks.com")

echo "$identity_token"

echo "Generating access-token for https://accounts.gcp.databricks.com with  ${impersonate_service_account}."
access_token=$(./google-cloud-sdk/bin/gcloud auth print-access-token --impersonate-service-account="$impersonate_service_account")
#access_token=access_token.replace(/\.+$/, '')
echo "$access_token"

read -p "Please enter databricks profile (e2-sat):" profile
echo "Using profile  ${profile}."


read -p "Please enter SAT secrets scope (sat_scope):" sat_scope
sat_scope=${sat_scope:-sat_scope}
echo "Storing secrets  ${sat_scope}."

if [ $profile!="" ]; then
    profile="--profile $profile"
fi

echo "Setting profile option to ${profile}."


databricks $profile secrets put --scope $sat_scope --key user --string-value $identity_token
databricks $profile secrets put --scope $sat_scope --key pass --string-value $access_token


