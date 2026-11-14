#/bin/bash

project=$1
profile=$2
config_file=$3


cp -r ../configs ../notebooks ../app ../lib ./dabs_template/template/tmp

databricks bundle init ./dabs_template -p $profile --config-file $config_file
rm -rf $config_file
cd $project
# Auto-adopt a pre-existing app so re-deploys don't fail with "app already
# exists". Bind fails silently on first-time installs (app not yet created) or
# when the app is disabled (resource key absent).
databricks bundle deployment bind sat_security_analysis security-analysis -p $profile --auto-approve 2>/dev/null || true
databricks bundle deploy -p $profile --force-lock
cd ../
rm -rf $project
rm -rf ./dabs_template/template/tmp/configs ./dabs_template/template/tmp/notebooks ./dabs_template/template/tmp/app ./dabs_template/template/tmp/lib
echo "The Security Analysis app is deployed. Open it from Compute -> Apps and complete the in-app setup."
echo "If the app code needs a manual redeploy, run: databricks apps deploy security-analysis --source-code-path /Workspace/Applications/SAT/files/app/security-analysis-tool"
