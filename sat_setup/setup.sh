#/bin/bash

project=$1
profile=$2
config_file=$3

databricks bundle init ./dabs_template -p $profile --config-file $config_file
rm -rf $config_file
cd $project
databricks bundle deploy -p $profile --force-lock
cd ../
rm -rf $project

