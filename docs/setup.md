# Setup Guide

Follow this guide to setup the Security Analysis Tool (SAT) on your Databricks workspace.

## Prerequisites

Before proceeding with the installation, make sure you have the following prerequisites:

- Python 3.9 or higher
- Databricks CLI installed with a profile logged (See [here](https://docs.databricks.com/en/dev-tools/cli/install.html).)
- Databricks Account ID
- Databricks SQL Warehouse (To run the SQL dashboard)
- Pypi access from your workspace (To install the SAT utility library)
  
> SAT is beneficial to customers on **Databrics Premium or Enterprise** as most of the checks and recommendations involve security features available in tiers higher than the Standard.

### Considerations

SAT creates a new security_analysis database and Delta tables. If you are an existing SAT user please run the following command:

### Hive metastore based schema

```sql
  drop  database security_analysis cascade;
```

### Unity Catalog based schema

```sql
  drop  database <uc_catalog_name>.security_analysis cascade;
```

## Setup

> SAT is a productivity tool to help verify security configurations of Databricks deployments, it's not meant to be used as certification or attestation of your deployments. SAT project is regularly updated to improve the correctness of checks, add new checks, and fix bugs. Please send your feedback and comments to sat@databricks.com. 

SAT can be setup on any of the cloud providers where Databricks is hosted. Follow the setup guide for the cloud provider you are using:

- [AWS Setup Guide](./setup/aws.md)
- [Azure Setup Guide](./setup/azure.md)
- [GCP Setup Guide](./setup/gcp.md)

**Note**: SAT can be setup as Terraform based deployment, if you use Terraform in your organization please prefer Terraform instructions: 
* [SAT AWS Terraform deployment](https://github.com/databricks-industry-solutions/security-analysis-tool/blob/main/terraform/aws/TERRAFORM_AWS.md) 
* [SAT Azure Terraform deployment](https://github.com/databricks-industry-solutions/security-analysis-tool/blob/main/terraform/azure/TERRAFORM_Azure.md) 
* [SAT GCP Terraform deployment](https://github.com/databricks-industry-solutions/security-analysis-tool/blob/main/terraform/gcp/TERRAFORM_GCP.md)

## FAQs and Troubleshooting

[Find answers to frequently asked questions, troubleshoot SAT issues, or diagnose SAT setup](./setup/faqs_and_troubleshooting.md)


## Usage
 
 
 **Note**:  Limit number of workspaces to be analyzed by SAT to 100. 
1.Run jobs
   Note: This process takes upto 10 mins per workspace
 
   You now have two jobs (SAT Initializer Notebook & SAT Driver Notebook). Run SAT Initializer Notebook and when it completes run SAT Driver Notebook; SAT Initializer Notebook should only be run once (although you can run it multiple times, it only needs to be run successfully one time), and SAT Driver Notebook can be run periodically (it's scheduled to run once every Monday, Wednesday, and Friday)
   
 
   At this point you should see **SAT** database and tables in your SQL Warehouses:

   <img src="./images/sat_database.png" width="70%" height="70%">
   
   
   
2. Access Databricks SQL Dashboards section and find "SAT - Security Analysis Tool" dashboard  to see the report. You can filter the dashboard by **SAT** tag. 
   
   <img src="./images/sat_dashboard_loc.png" width="70%" height="70%">

    **Note:** You need to select the workspace and date and click "Apply Changes" to get the report.  
    **Note:** The dashbord shows last valid run for the selected date if there is one, if not it shows the latest report for that workspace.  
 
    You can share SAT dashboard with other members of your team by using the "Share" functionality on the top right corner of the dashboard. 
      
     
    Here is what your SAT Dashboard should look like:
 
   <img src="../images/sat_dashboard_partial.png" width="50%" height="50%">   
    
3.  Activate Alerts 
  * Goto Alerts and find the alert(s) created by SAT tag and adjust the schedule to your needs. You can add more recpients to alerts by configuring  [notification destinations](https://docs.databricks.com/sql/admin/notification-destinations.html).
     

      <img src="./images/alerts_1.png" width="50%" height="50%">   
 

      <img src="./images/alerts_2.png" width="50%" height="50%">   

