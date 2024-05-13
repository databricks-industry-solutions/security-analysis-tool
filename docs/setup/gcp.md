# GCP Setup Guide

This guide will help you setup the Security Analysis Tool (SAT) on GCP Databricks.

- [GCP Setup Guide](#gcp-setup-guide)
  - [Prerequisites](#prerequisites)
    - [Service Principal](#service-principal)
  - [Installation](#installation)
    - [Credentials Needed](#credentials-needed)
  - [Troubleshooting](#troubleshooting)



## Prerequisites

There are some pre-requisites that need to be met before you can setup SAT on GCP. Make sure you have the appropriate permissions in your GCP Cloud account to create the resources mentioned below.


### Service Principal

The first step is to create a Service Principal in GCP. This will allow SAT to authenticate with GCP services. Follow the steps below to create a Service Principal:


## Installation

### Credentials Needed

To setup SAT on Azure, you will need the following credentials:
* Databricks Account ID

To execute SAT follow this steps:
- Clone the SAT repository
- Run the `install.sh` script on your terminal.

![](../gif/terminal-aws.gif)

> Remember that the target workspace should have a profile in Databricks CLI

## Troubleshooting

If any issues arise during the installation process, please check your credentials and ensure that you have the appropriate permissions in your Azure cloud account. If you are still facing issues, please send your feedback and comments to sat@databricks.com. 