# AWS Setup Guide

This guide will help you setup the Security Analysis Tool (SAT) on AWS Databricks.

- [AWS Setup Guide](#aws-setup-guide)
  - [Prerequisites](#prerequisites)
    - [Service Principal](#service-principal)
  - [Installation](#installation)
    - [Credentials Needed](#credentials-needed)
  - [Troubleshooting](#troubleshooting)

## Prerequisites

There are some prerequisites that need to be met before you can set up SAT on AWS. Make sure you have the appropriate permissions in your Databricks Account Console to create the resources mentioned below.

> SAT is beneficial to customers on **Databrics Premium or Enterprise** as most of the checks and recommendations involve security features available in tiers higher than the Standard.


### Service Principal

The first step is to create a Service Principal in Databricks. This will allow SAT to authenticate with the other workspaces. Follow the steps:
- Go to the [Account Console](https://accounts.cloud.databricks.com)
- On the left side bar menu, click on `User management`
- Select `Service Principal` and then `Add service principal`
- Type a new name for the service principal and then create a new OAuth Secret.
- Save the `Secret` and `Client ID`
- To deploy SAT in a workspace, you must add the Service Principal to the workspace.
  
![AWS_SP_Workspace](../images/aws_ws.png)

> The Service Principle requires an [Accounts Admin role](https://docs.databricks.com/en/admin/users-groups/service-principals.html#assign-account-admin-roles-to-a-service-principal), [Admin role](https://docs.databricks.com/en/admin/users-groups/service-principals.html#assign-a-service-principal-to-a-workspace-using-the-account-console) for **each workspace** and needs to be a member of the [metastore admin group](https://docs.databricks.com/en/data-governance/unity-catalog/manage-privileges/admin-privileges.html#who-has-metastore-admin-privileges) is required to analyze many of the APIs



## Installation

### Credentials Needed

To setup SAT on AWS, you will need the following credentials:
* Databricks Account ID
* Databricks Service Principal ID
* Databricks Service Principal Secret

To execute SAT follow this steps:
- Clone the SAT repository
- Run the `install.sh` script on your terminal.

![](../gif/terminal-aws.gif)

> Remember that the target workspace should have a [profile](https://docs.databricks.com/en/dev-tools/cli/profiles.html) in [Databricks CLI](https://docs.databricks.com/en/dev-tools/cli/index.html)




## Troubleshooting

Please review the FAQs and Troubleshooting resources documented [here](./faqs_and_troubleshooting.md) including a notebook to help diagnose your SAT setup.
If any issues arise during the installation process, please check your credentials and ensure that you have the appropriate configurations and permissions for your Databricks. If you are still facing issues, please send your feedback and comments to sat@databricks.com. 
