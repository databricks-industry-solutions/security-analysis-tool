# GCP Setup Guide

This guide will help you setup the Security Analysis Tool (SAT) on GCP Databricks.

- [GCP Setup Guide](#gcp-setup-guide)
  - [Prerequisites](#prerequisites)
    - [Service Accounts](#service-accounts)
  - [Installation](#installation)
    - [Credentials Needed](#credentials-needed)
  - [Troubleshooting](#troubleshooting)

## Prerequisites

There are some pre-requisites that need to be met before you can setup SAT on GCP. Make sure you have the appropriate permissions in your GCP Cloud account to create the resources mentioned below.

> SAT is beneficial to customers on **Databrics Premium or Enterprise** as most of the checks and recommendations involve security features available in tiers higher than the Standard.

### Service Accounts

The first step is to create a Service Principal in GCP. This will allow SAT to authenticate with GCP services. Follow the steps below to create a Service Principal:

- Please follow [this](https://docs.gcp.databricks.com/en/dev-tools/authentication-google-id.html) guide to create the required service accounts.
- Now upload the SA-1.json file into a GCS bucket.
- To add the service account to the Account Console:
  - You will need to create a new user and add the service account email as the user email.
- To finish the setup, we will need to add the **user** as an admin in the workspace where we are going to deploy SAT.

## Installation

### Credentials Needed

To setup SAT on Azure, you will need the following credentials:
- Databricks Account ID
- Service Account email
- gsutil URI from GCS Bucket
- ![alt text](../images/gs_path_to_json.png)


To execute SAT follow this steps:

- Clone the SAT repository
- Run the `install.sh` script on your terminal.

![](../gif/terminal-aws.gif)

> Remember that the target workspace should have a profile in Databricks CLI

## Troubleshooting

If any issues arise during the installation process, please check your credentials and ensure that you have the appropriate permissions in your Azure cloud account. If you are still facing issues, please send your feedback and comments to <sat@databricks.com>.
