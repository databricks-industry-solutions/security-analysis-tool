#/bin/bash

project=$1
profile=$2
catalog=$3
cloud_type=$4
gcp_sa=$5

echo "{\"catalog\": \"$catalog\", \"cloud\": \"$cloud_type\", \"google_service_account\": \"$gcp_sa\" }" >config.json
databricks bundle init ./sat_template -p $profile --config-file config.json
cd $project
databricks bundle deploy -p $profile --force-lock
cd ../
rm -rf $project
rm -rf config.json
