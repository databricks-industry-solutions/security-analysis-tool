## Checklist to prepare for SAT setup

(SAT is supported for Databricks AWS accounts only, we are planning to release SAT for Azure and GCP for Q4,  Jan 30th 2023   )

You will need the following information to set up SAT, we will show you how to gather them in the next section.

We created a companion Security Analysis Tool (SAT) [Setup primer video](https://www.youtube.com/watch?v=kLSc3UHKL40) and a [Deployment checklist sheet](./SAT%20Deployment%20Checklist.xlsx) to help prepare for the SAT setup. 

 1. Databricks Account ID, administrative user id and password  (To use the account REST APIs)
 2. A Single user job cluster (To run the SAT checks)
 3. Databricks SQL Warehouse  (To run the SQL dashboard)
 4. Ensure that Databricks Repos is enabled (To access the SAT git)
 5. Pipy access from your workspace (To install the SAT utility library)
 6. PAT token for the SAT primary deployment workspace 
  
**Note**: SAT creates a new **security_analysis** database and Delta tables. 



## Prerequisites 

 (Estimated time to complete these steps: 15 - 30 mins)

Please gather the following information before you start setting up: 
 
 1. Databricks Account ID 
     * Please test your administrator account and password to make sure this is a working account: [https://accounts.cloud.databricks.com/login](https://accounts.cloud.databricks.com/login)
     * Copy the account id as shown below

        <img src="./images/account_id.png" width="30%" height="30%">

 2. A Single user cluster  
    *  Databricks Runtime Version  11.3 LTS or above
    *  Node type i3.xlarge (please start with a max of a two node cluster and adjust to 5 nodes if you have many workspaces that will be analyzed with SAT)  

        <img src="./images/job_cluster.png" width="50%" height="50%">
     **Note:**  In our tests we found that the full run of SAT takes about 10 mins per workspace. 
     
 3. Databricks SQL Warehouse  
    * Goto SQL (pane) -> SQL Warehouse -> and pick the SQL Warehouse for your dashboard and note down the ID as shown below
    * This Warehouse needs to be in a running state when you run steps in the Setup section.
    
        <img src="./images/dbsqlwarehouse_id.png" width="50%" height="50%">

 4. Databricks Repos to access SAT git
    Import git repo into Databricks repo 

    ``` 
           https://github.com/databricks-industry-solutions/security-analysis-tool
    ```


      <img src="./images/git_import.png" width="50%" height="50%">

 5. Please confirm that PyPI access is available

    * Open the \<SATProject\>/notebooks/Includes/install_sat_sdk  and run on the cluster that was created in the Step 2 above. 
    Please make sure there are no errors.
 

6. Configure secrets

  * Download and setup Databricks CLI by following the instructions [here](https://docs.databricks.com/dev-tools/cli/index.html)  
  * Note: if you have multiple Databricks profiles you will need to use --profile <profile name> switch to access the correct workspace,
    follow the instructions [here](https://docs.databricks.com/dev-tools/cli/index.html#connection-profiles) . Throughout the documentation below we use an example profile **e2-sat**, please adjust your commands as per your workspace profile or exclude  --profile <optional-profile-name> if you are using the default profile. 
  * Setup authentication to your Databricks workspace by following the instructions [here](https://docs.databricks.com/dev-tools/cli/index.html#set-up-authentication)

       ```
            databricks configure --token --profile e2-sat
       ```

     <img src="./images/cli_authentication.png" width="50%" height="50%">

     You should see a listing of folders in your workspace : 
      ```
           databricks --profile e2-sat workspace ls
      ```

     <img src="./images/workspace_ls.png" width="50%" height="50%">


  *  Set up the secret scope with the scope name you prefer and note it down:
     
     Note: The values you place below are case sensitive and need to be exact. 
 
     ```
      databricks --profile e2-sat  secrets create-scope --scope sat_scope
      ```

     For more details refer [here](https://docs.databricks.com/dev-tools/cli/secrets-cli.html) 

  *  Create username secret and password secret of administrative user id and password  as  "user" and "pass" under the above "sat_scope" scope using Databricks Secrets CLI 

      *  Create secret for master account username
        ```
        databricks --profile e2-sat secrets put --scope sat_scope --key user
        ```

      *  Create secret for master account password

        ```
        databricks --profile e2-sat secrets put --scope sat_scope --key pass
        ```    
        

  * Create a secret for the workspace PAT token

      **Note**: Replace \<workspace_id\> with your SAT deployment workspace id. 
       You can find your workspace id by following the instructions [here](https://docs.databricks.com/workspace/workspace-details.html)

       You can create a PAT token by following the instructions [here](https://docs.databricks.com/dev-tools/api/latest/authentication.html#generate-a-personal-access-token)


       ```
       databricks --profile e2-sat secrets put --scope sat_scope --key sat_token_<workspace_id> 
       ``` 

   * In your environment where you imported SAT project from git (Refer to Step 4 in Prerequisites) Open the \<SATProject\>/notebooks/Utils/initialize notebook and modify the JSON string with :  
     * Set the value for the account id 
     * Set the value for the sql_warehouse_id
     * Set the value for username_for_alerts
     * databricks secrets scope/key names to pick the secrets from the steps above.

  * Your config in  \<SATProject\>/notebooks/Utils/initialize CMD 2 should look like this:

     ```
           {
              "account_id":"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",  <- update this value
              "sql_warehouse_id":"4d9fef7de2b9995c",     <- update this value
              "username_for_alerts":"john.doe@org.com", <- update this value with a valid Databricks user id 
           }
                                 
     ```

 
## Setup option 1 (Simple and recommended method)
                                                           
  (Estimated time to complete these steps: 5 - 10 mins)  
 This method uses admin credentials (configured in the Step 6 of Prerequisites section) to call workspace APIs.   
                                                           
 Make sure both SAT job cluster (Refer to Prerequisites Step 2 ) and Warehouse (Refer to Prerequisites Step 3) are running.                                                                   
<details>
  <summary>Setup instructions</summary>                                                                          
 Following is the one time easy setup to get your workspaces setup with the SAT:

* (Optional) Modify security_best_practices
   *  Goto \<SATProject\>/configs/security_best_practices.csv and make a copy as \<SATProject\>/configs/security_best_practices_user.csv if security_best_practices_user.csv already does not exist. 
   * Modify **enable** to 0 if you don't want a specific check to be performed. 
   * Modify **alert** to 1 if you would like to receive an email when a deviation is detected, in addition to marking the deviation on the report
                                                          
* Attach  \<SATProject\>/notebooks/security_analysis_initializer to the SAT cluster you created above and Run -> Run all 
 
    <img src="./images/initialize_sat.png" width="70%" height="70%">
 
 
    
    <img src="./images/initialize_sat_complete.png" width="70%" height="70%">
   
</details>
 
## Setup option 2 (Most flexible for the power users)
 
  (Estimated time to complete these steps:30 mins)  
   This method uses admin credentials (configured in the Step 6 of Prerequisites section) by default to call workspace APIs. But can be changed to use workspace PAT tokens instead.
<details>
  <summary>Setup instructions</summary> 
 Following are the one time easy steps to get your workspaces setup with the SAT:
                  <img src="./images/setup_steps.png" width="100%" height="100%">  
 
1. Modify security_best_practices
   *  Goto \<SATProject\>/configs/security_best_practices.csv and make a copy as \<SATProject\>/configs/security_best_practices_user.csv if security_best_practices_user.csv already does not exist. 
   * Modify **enable** to 0 if you don't want a specific check to be performed. 
   * Modify **alert** to 1 if you would like to receive an email when a deviation is detected, in addition to marking the deviation on the report
   
2. List account workspaces to analyze with SAT
   * Goto  \<SATProject\>/notebooks/Setup/1.list_account_workspaces_to_conf_file and Run -> Run all 
   * This creates a configuration file as noted at the bottom of the notebook.

    <img src="./images/list_workspaces.png" width="70%" height="70%">
   
   * Goto  \<SATProject\>/configs/workspace_configs.csv which is generated after the above step and update the file for each workspace listed as a new line. 
     You will need to set analysis_enabled as True or False based on if you would like to enroll a workspace to analyze by the SAT.
     
     Set alert_subscriber_user_id to a valid user login email address to receive alerts by workspace
 
     Note: Please avoid  ???+??? character in the alert_subscriber_user_id values due to a limitation with the alerts API. 
     
     Update values for each workspace for the manual checks:(    sso_enabled,scim_enabled,vpc_peering_done,object_storage_encypted,table_access_control_enabled)
 
     * sso_enabled : True if you enabled Single Singn-on for the workspace
     * scim_enabled: True if you integrated with  SCIM for the workspace
     * vpc_peering_done: False if you have not peered with another VPC 
     * object_storage_encypted: True if you encrypted your data buckets
     * table_access_control_enabled : True if you enabled ACLs so that you can utilize Table ACL clusters that enforce user isolation
    <img src="./images/workspace_configs.png" width="70%" height="70%">
   
   
   
3. Generate secrets setup file
  Note: You can skip this step and go to step 4, if you would like to use admin credentials (configured in the Step 6 of Prerequisites section) to call workspace APIs.
 
   * Change \<SATProject\>/notebooks/Utils/initialize value of from  "use_mastercreds":"true" to "use_mastercreds":"false"
   * Run the \<SATProject\>/notebooks/Setup/2.generate_secrets_setup_file notebook.  Setup your PAT tokens for each of the workspaces under the "master_name_scope??? 

    <img src="./images/setup_secrets.png" width="70%" height="70%">

    We generated a template file: \<SATProject\>/configs/setupsecrets.sh to make this easy for you with 
    [curl](https://docs.databricks.com/dev-tools/api/latest/authentication.html#store-tokens-in-a-netrc-file-and-use-them-in-curl), 
    copy and paste and run the commands from the file with your PAT token values. 
    You will need to [setup .netrc file](https://docs.databricks.com/dev-tools/api/latest/authentication.html#store-tokens-in-a-netrc-file-and-use-them-in-curl) to use this method

   Example:

    curl --netrc --request POST 'https://oregon.cloud.databricks.com/api/2.0/secrets/put' -d '{"scope":"
 sat_scope", "key":"sat_token_1657683783405197", "string_value":"<dapi...>"}' 
   
   
4. Test API Connections    
   * Test connections from your workspace to accounts API calls and all workspace API calls by running \<SATProject\>/notebooks/Setup/3. test_connections. The workspaces that didn't pass the connection test are marked in workspace_configs.csv with connection_test as False and are not analyzed.

    <img src="./images/test_connections.png" width="70%" height="70%">
   
5. Enable workspaces for SAT 
   * Enable workspaces by running \<SATProject\>/notebooks/Setup/4. enable_workspaces_for_sat.  This makes the registered workspaces ready for SAT to monitor 

    <img src="./images/enable_workspaces.png" width="70%" height="70%">
   
6. Import SAT dashboard template
   * We built a ready to go DBSQL dashboard for SAT. Import the dashboard by running \<SATProject\>/notebooks/Setup/5. import_dashboard_template

    <img src="./images/import_dashboard.png" width="70%" height="70%">   
   
7. Configure Alerts 
   SAT can deliver alerts via email via Databricks SQL Alerts. Import the alerts template by running \<SATProject\>/notebooks/Setup/6. configure_alerts_template (optional)

   <img src="./images/configure_alerts.png" width="70%" height="70%">
   
</details>
   
 
   
## Usage
 
 (Estimated time to complete these steps: 5 - 10 mins per workspace)  
 
1. Attach and run the notebook \<SATProject\>/notebooks/security_analysis_driver 
   Note: This process takes upto 10 mins per workspace
 
   <img src="./images/run_analysis.png" width="70%" height="70%">
   
 
   At this point you should see **SAT** database and tables in your SQL Warehouses:

   <img src="./images/sat_database.png" width="70%" height="70%">
   
   
   
2. Access Databricks SQL Dashboards section and find "SAT - Security Analysis Tool" dashboard  to see the report. You can filter the dashboard by **SAT** tag. 
   
   <img src="./images/sat_dashboard_loc.png" width="70%" height="70%">

    Note: You need to select the workspace and click "Apply Changes" to get the report.  

    You can share SAT dashboard with other members of your team by using the "Share" functionality on the top right corner of the dashboard. 
    
    Here is what your SAT Dashboard should look like:
 
   <img src="../images/sat_dashboard_partial.png" width="50%" height="50%">   
    
3.  Activate Alerts 
  * Goto Alerts and find the alert(s) created by SAT tag and adjust the schedule to your needs. 


      <img src="./images/alerts_1.png" width="50%" height="50%">   
 

      <img src="./images/alerts_2.png" width="50%" height="50%">   

   
   
## Configure Workflow (Optional) 
 
 (Estimated time to complete these steps: 5 mins)  
 
  * Databricks Workflows is the fully-managed orchestration service. You can configure SAT to automate when and how you would like to schedule it by using by taking advantage of Workflows. 

  * Goto Workflows - > click on create jobs -> setup as following:

    Task Name  : security_analysis_driver

    Type: Notebook

    Source: Workspace (or your git clone of SAT)

    Path : \<SATProject\>/SAT/SecurityAnalysisTool-BranchV2Root/notebooks/security_analysis_driver

    Cluster: Make sure to pick the Single user mode job compute cluster you created before. 

    <img src="./images/workflow.png" width="50%" height="50%">   

    Add a schedule as per your needs. That???s it. Now you are continuously monitoring the health of your account workspaces.


## FAQs
 1. How can SAT be configured if access to github is not possible due to firewall restrictions to git or other organization policies?
    
    You can still setup SAT by downloading the [release zip](https://github.com/databricks-industry-solutions/security-analysis-tool/releases) file and by using Git repo to load SAT project into your workspace.
     * Add Repo by going to Repos in your workspace:  
     
      <img src="./images/add_repo_1.png" width="50%" height="50%">   
 
     * Type SAT as your "Repository name" and uncheck "Create repo by cloning a Git repository"
 
      <img src="./images/add_repo_2.png" width="50%" height="50%">
 
     * Click on the pulldown menu and click on Import
      
      <img src="./images/add_repo_3.png" width="50%" height="50%">

     * Drag and drop the release zip file and click Import
 
      <img src="./images/add_repo_4.png" width="50%" height="50%">
      
      <img src="./images/add_repo_5.png" width="50%" height="50%"> 
    
    You should see the SAT project in your workspace. 
    
## Troubleshooting
   
1. Incorrectly configured secrets
    * Error:
   
      Secret does not exist with scope: sat_scope and key: sat_tokens

    * Resolution:
      Check if the tokens are configured with the correct names by listing and comparing with the configuration.
      databricks secrets list --scope sat_scope

2. Invalid access token
   
    * Error:
   
      Error 403 Invalid access token.

    * Resolution: 
   
      Check your PAT token configuration for  ???workspace_pat_token??? key 

3. Firewall blocking databricks accounts console

    * Error: 
         <p/>   
         Traceback (most recent call last): File "/databricks/python/lib/python3.8/site-packages/urllib3/connectionpool.py", line 670, in urlopen  httplib_response = self._make_request(  File "/databricks/python/lib/python3.8/site-packages/urllib3/connectionpool.py", line 381, in _make_request  self._validate_conn(conn)  File "/databricks/python/lib/python3.8/site-packages/urllib3/connectionpool.py", line 978, in _validate_conn  conn.connect()  File "/databricks/python/lib/python3.8/site-packages/urllib3/connection.py", line 362, in connect  self.sock = ssl_wrap_socket(  File "/databricks/python/lib/python3.8/site-packages/urllib3/util/ssl_.py", line 386, in ssl_wrap_socket  return context.wrap_socket(sock, server_hostname=server_hostname)  File "/usr/lib/python3.8/ssl.py", line 500, in wrap_socket  return self.sslsocket_class._create(  File "/usr/lib/python3.8/ssl.py", line 1040, in _create  self.do_handshake()  File "/usr/lib/python3.8/ssl.py", line 1309, in do_handshake  self._sslobj.do_handshake() ConnectionResetError: [Errno 104] Connection reset by peer During handling of the above exception, another exception occurred:

    * Resolution: 
   
      Run this following command in your notebook %sh 
      curl -X GET -H "Authorization: Basic <base64 of userid:password>" -H "Content-Type: application/json" https://accounts.cloud.databricks.com/api/2.0/accounts/<account_id>/workspaces

      If you don???t see a JSON with a clean listing of workspaces you are likely having a firewall issue that is blocking calls to the accounts console.  Please have your infrastructure team add Databricks accounts.cloud.databricks.com to the allow-list.   


                                                          
