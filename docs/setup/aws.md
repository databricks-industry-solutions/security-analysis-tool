# AWS Setup Guide

This guide will help you setup the Security Analysis Tool (SAT) on AWS Databricks.

- [AWS Setup Guide](#aws-setup-guide)
  - [Prerequisites](#prerequisites)
    - [Service Principal](#service-principal)
  - [Installation](#installation)
    - [Credentials Needed](#credentials-needed)
  - [Troubleshooting](#troubleshooting)

## Prerequisites

There are some pre-requisites that need to be met before you can setup SAT on AWS. Make sure you have the appropriate permissions in your Databricks Account Console to create the resources mentioned below.


### Service Principal

The first step is to create a Service Principal in Databricks. This will allow SAT to authenticate with the other workspaces. Follow the steps:
- Go to the [Account Console](https://accounts.cloud.databricks.com)
- On the left side bar menu, click on `User management`
- Select `Service Principal` and then `Add service principal`
- Type a new name for the service principal and then create a new OAuth Secret.
- Save the `Secret` and `Client ID`
- 
Note: The Service Principle requires an [Accounts Admin role](https://learn.microsoft.com/en-us/azure/databricks/admin/users-groups/service-principals#--assign-account-admin-roles-to-a-service-principal), [Admin role](https://learn.microsoft.com/en-us/azure/databricks/admin/users-groups/service-principals#assign-a-service-principal-to-a-workspace-using-the-account-console) for **each workspace** and needs to be a member of the [metastore admin group](https://learn.microsoft.com/en-us/azure/databricks/data-governance/unity-catalog/manage-privileges/admin-privileges#who-has-metastore-admin-privileges) is required to analyze many of the APIs

## Installation

### Credentials Needed

To setup SAT on Azure, you will need the following credentials:
* Databricks Account ID
* Databricks Service Principal ID
* Databricks Service Principal Secret

To execute SAT follow this steps:
- Clone the SAT repository
- Run the `install.sh` script on your terminal.

![](../gif/terminal-aws.gif)

> Remember that the target workspace should have a profile in Databricks CLI




## Troubleshooting

If any issues arise during the installation process, please check your credentials and ensure that you have the appropriate permissions in your Azure cloud account. If you are still facing issues, please send your feedback and comments to sat@databricks.com. 