# Azure Setup Guide

This guide will help you setup the Security Analysis Tool (SAT) on Azure Databricks.


- [Azure Setup Guide](#azure-setup-guide)
  - [Prerequisites](#prerequisites)
    - [App Registration](#app-registration)
    - [App Client Secrets](#app-client-secrets)
    - [Credentials Needed](#credentials-needed)
  - [Installation](#installation)
  - [Troubleshooting](#troubleshooting)

## Prerequisites

There are some pre-requisites that need to be met before you can setup SAT on Azure. Make sure you have the appropriate permissions in your Azure cloud account to create the resources mentioned below.

### App Registration

The first step is to create an App Registration in Azure. This will allow SAT to authenticate with Azure services. Follow the steps below to create an App Registration:

* Open the Azure portal and navigate to Microsoft Entra ID.
* Click on `App registrations` and then click on `New registration`.
* Enter a name for the App Registration and select the appropriate permissions. The minimum requirement is to have access in a single tenant.

![alt text](../images/azure_app_reg.png)

### App Client Secrets

After creating the App Registration, you will need to create a client secret. This secret will be used to authenticate with Azure services. Follow the steps below to create a client secret:

* Open the App Registration you created in the previous step.
* Click on `Certificates & secrets` and then click on `New client secret`.
* Enter a description for the client secret and select the expiry date. Click on `Add`.
* Copy the value of the client secret and save it in a secure location.

### Credentials Needed

To setup SAT on Azure, you will need the following credentials:
* Databricks Account ID
* Azure Tenant ID
* Azure Subscription ID
* Azure App Client ID (Obtained from App Registration)
* Azure App Client Secret (Obtained from App Client Secrets)

## Installation

To execute SAT run the `install.sh` script on your terminal.

## Troubleshooting