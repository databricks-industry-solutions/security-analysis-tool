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
