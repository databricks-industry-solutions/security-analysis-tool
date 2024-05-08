# AWS Setup Guide

This guide will help you setup the Security Analysis Tool (SAT) on AWS Databricks.

- [AWS Setup Guide](#aws-setup-guide)
  - [Prerequisites](#prerequisites)
    - [Service Principal](#service-principal)
  - [Installation](#installation)
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


## Installation
- Clone the repo
- Run the `install.sh` 

> Remember that the target workspace should have a profile in Databricks CLI




## Troubleshooting