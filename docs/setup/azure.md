# Azure Setup Guide

This guide will help you setup the Security Analysis Tool (SAT) on Azure Databricks.


- [Azure Setup Guide](#azure-setup-guide)
  - [Prerequisites](#prerequisites)
    - [App Registration](#app-registration)
    - [App Client Secrets](#app-client-secrets)
    - [Add Service Principle to Databricks](#add-service-principle-to-databricks)
  - [Installation](#installation)
    - [Credentials Needed](#credentials-needed)
  - [Troubleshooting](#troubleshooting)
  - [References](#references)

## Prerequisites

There are some pre-requisites that need to be met before you can setup SAT on Azure. Make sure you have the appropriate permissions in your Azure cloud account to create the resources mentioned below.

> SAT is beneficial to customers on **Databrics Premium or Enterprise** as most of the checks and recommendations involve security features available in tiers higher than the Standard.


### App Registration

The first step is to create an App Registration in Azure. This will allow SAT to authenticate with Azure services. Follow the steps below to create an App Registration:

- Open the Azure portal and navigate to Microsoft Entra ID.
- Click on `App registrations` and then click on `New registration`.
- Enter a name for the App Registration and select the appropriate permissions. The minimum requirement is to have access in a single tenant.

![alt text](../images/azure_app_reg.png)



### App Client Secrets

After creating the App Registration, you will need to create a client secret. This secret will be used to authenticate with Azure services. Follow the steps below to create a client secret:

- Open the App Registration you created in the previous step.
- Click on `Certificates & secrets` and then click on `New client secret`.
- Enter a description for the client secret and select the expiry date. Click on `Add`.
- Copy the value of the client secret and save it in a secure location.
- Please add the created app with "Reader" role into the subscription level via Access control (IAM) using Role assignments under your [subscription, Access control (IAM) section](https://learn.microsoft.com/en-us/azure/role-based-access-control/role-assignments-portal#step-2-open-the-add-role-assignment-page)

![alt text](../images/azure_role_assignment.png)

### Add Service Principle to Databricks

After creating the App Registration and client secret, you will need to add the App Registration as a service principal in Databricks. Follow the steps below to add the service principal:

- Go to the [Account Console](https://accounts.azuredatabricks.net/)
- On the left side bar menu, click on `User management`
- Select `Service Principal` and then `Add service principal`
- Select `Microsoft Entra ID Managed Application` as the service principal type.
- Paste the App Client ID and create a new name for the service principal.
- Click Add.
- The Service Principal must be granted the `Account Admin` role. This role provides the ability to manage account-level settings and permissions.
- Assign the Workspace Admin Role: The Service Principal must be assigned the `Workspace Admin` role for each workspace it will manage. This role provides the ability to manage workspace-level settings and permissions.
- Add to the Metastore Admin Group: The Service Principal must be added to the `Metastore Admin` group or role. This role provides the ability to manage metastore-level settings and permissions.

![Azure_SP_Workspace](../images/azure_ws.png)

See the [Databricks documentation](https://learn.microsoft.com/en-us/azure/databricks/admin/users-groups/service-principals#--databricks-and-microsoft-entra-id-formerly-azure-active-directory-service-principals) for more information on adding service principals.

> The Service Principle requires an [Accounts Admin role](https://learn.microsoft.com/en-us/azure/databricks/admin/users-groups/service-principals#--assign-account-admin-roles-to-a-service-principal), [Admin role](https://learn.microsoft.com/en-us/azure/databricks/admin/users-groups/service-principals#assign-a-service-principal-to-a-workspace-using-the-account-console) for **each workspace** and needs to be a member of the [metastore admin group](https://learn.microsoft.com/en-us/azure/databricks/data-governance/unity-catalog/manage-privileges/admin-privileges#who-has-metastore-admin-privileges) is required to analyze many of the APIs.

## Installation

### Credentials Needed

To setup SAT on Azure, you will need the following credentials:

- Databricks Account ID
- Azure Tenant ID
- Azure Subscription ID
- Azure App Client ID (Obtained from App Registration)
- Azure App Client Secret (Obtained from App Client Secrets)

To execute the SAT follow these steps on your workstation or a compatible VM that has access to the internet and the Databricks workspace:

- Clone the SAT repository locally 
  
  ```sh
    git clone https://github.com/databricks-industry-solutions/security-analysis-tool.git
   ```

> Remember that the target workspace should have a [profile](https://docs.gcp.databricks.com/en/dev-tools/cli/profiles.html) in [Databricks CLI](https://docs.gcp.databricks.com/en/dev-tools/cli/tutorial.html)

- Run the `install.sh` script on your terminal.

> To ensure that the install.sh script is executable, you need to modify its permissions using the chmod command.
    ```sh
      chmod +x install.sh
      ./install.sh
    ```

![](../gif/terminal-azure.gif)

Congratulations! 🎉 You are now ready to start using the SAT. Please click [here](../setup.md#usage) for a detailed description on how to run and use it.


## Troubleshooting
Please review the FAQs and Troubleshooting resources documented [here](./faqs_and_troubleshooting.md) including a notebook to help diagnose your SAT setup.
If any issues arise during the installation process, please check your credentials and ensure that you have the appropriate permissions in your Azure cloud account. If you are still facing issues, please send your feedback and comments to sat@databricks.com. 

## References

- [Azure App Registration](https://docs.microsoft.com/en-us/azure/active-directory/develop/quickstart-register-app)
- [Databricks Service Principals](https://learn.microsoft.com/en-us/azure/databricks/admin/users-groups/service-principals#--databricks-and-microsoft-entra-id-formerly-azure-active-directory-service-principals)
