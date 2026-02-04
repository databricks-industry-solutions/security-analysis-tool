#/bin/bash

project=$1
profile=$2
config_file=$3


cp -r ../configs ../notebooks ../dashboards ../app ./dabs_template/template/tmp

databricks bundle init ./dabs_template -p $profile --config-file $config_file
rm -rf $config_file
cd $project
databricks bundle deploy -p $profile --force-lock
cd ../
rm -rf $project
rm -rf ./dabs_template/template/tmp/configs ./dabs_template/template/tmp/dashboards ./dabs_template/template/tmp/notebooks ./dabs_template/template/tmp/app
echo "Run 'databricks apps deploy sat-permission-app --source-code-path /Workspace/Applications/SAT/files/app/brickhound' to deploy the Permission app to your Databricks workspace."
