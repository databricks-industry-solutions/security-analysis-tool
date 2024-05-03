# Azure Setup Guide

This guide will help you setup the Security Analysis Tool (SAT) on Azure Databricks.


- [Azure Setup Guide](#azure-setup-guide)
  - [Prerequisites](#prerequisites)
    - [App Registration](#app-registration)
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

## Installation

## Troubleshooting