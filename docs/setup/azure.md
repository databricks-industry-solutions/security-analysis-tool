# Azure Setup Guide

This guide will help you setup the Security Analysis Tool (SAT) on Azure Databricks.


- [Azure Setup Guide](#azure-setup-guide)
  - [Prerequisites](#prerequisites)
    - [App Registration](#app-registration)
    - [App Client Secrets](#app-client-secrets)
    - [Add Service Principal to Databricks](#add-service-principal-to-databricks)
  - [Installation](#installation)
    - [Credentials Needed](#credentials-needed)
    - [Setup Instructions](#setup-instructions)
  - [Troubleshooting](#troubleshooting)
  - [References](#references)

## Prerequisites

Before setting up SAT on Azure, ensure you have the appropriate permissions in your Azure cloud account to create the necessary resources.

> SAT is beneficial for customers on **Databricks Premium or Enterprise**, as most checks and recommendations involve security features available in higher tiers than Standard.

### App Registration

Create an App Registration in Azure to allow SAT to authenticate with Azure services. Follow these steps:

1. **Open Azure Portal:**
   - Navigate to **Microsoft Entra ID**.
  
2. **Create New App Registration:**
   - Click on **App registrations**.
   - Click on **New registration**.
   - Enter a name for the App Registration.
   - Select the appropriate permissions (minimum requirement: access in a single tenant).

![Azure App Registration](../images/azure_app_reg.png)

### App Client Secrets

Create a client secret for the App Registration to authenticate with Azure services. Follow these steps:

1. **Open the App Registration:**
   - Select the App Registration you created.

2. **Create Client Secret:**
   - Click on **Certificates & secrets**.
   - Click on **New client secret**.
   - Enter a description for the client secret.
   - Select the expiry date.
   - Click **Add**.

3. **Save Client Secret:**
   - Copy the value of the client secret.
   - Save it in a secure location.

4. **Assign Role:**
   - Add the created Service Principal with the "Reader" role at the subscription level via **Access control (IAM)**.
   - Use [Role assignments](https://learn.microsoft.com/en-us/azure/role-based-access-control/role-assignments-portal#step-2-open-the-add-role-assignment-page).

![Azure Role Assignment](../images/azure_role_assignment.png)

### Add Service Principal to Databricks

Add the App Registration as a service principal in Databricks. Follow these steps:

1. **Go to Account Console:**
   - Visit the [Account Console](https://accounts.azuredatabricks.net/).

2. **User Management:**
   - In the left sidebar menu, click **User management**.

3. **Add Service Principal:**
   - Select **Service Principal**.
   - Click **Add service principal**.

4. **Service Principal Type:**
   - Select **Microsoft Entra ID Managed Application**.

5. **App Client ID:**
   - Paste the App Client ID.
   - Create a new name for the service principal.
   - Click **Add**.

6. **Assign Roles:**
   - Grant the Service Principal the `Account Admin` role to manage account-level settings and permissions.
   - Assign the `Workspace Admin` role to the Service Principal for each workspace it will manage.
   - Add the Service Principal to the `Metastore Admin` group or role to manage metastore-level settings and permissions.

![Azure SP Workspace](../images/azure_ws.png)

For more information, see the [Databricks documentation](https://learn.microsoft.com/en-us/azure/databricks/admin/users-groups/service-principals#--databricks-and-microsoft-entra-id-formerly-azure-active-directory-service-principals).

> The Service Principal requires an [Accounts Admin role](https://learn.microsoft.com/en-us/azure/databricks/admin/users-groups/service-principals#--assign-account-admin-roles-to-a-service-principal), an [Admin role](https://learn.microsoft.com/en-us/azure/databricks/admin/users-groups/service-principals#assign-a-service-principal-to-a-workspace-using-the-account-console) for **each workspace**, and must be a member of the [metastore admin group](https://learn.microsoft.com/en-us/azure/databricks/data-governance/unity-catalog/manage-privileges/admin-privileges#who-has-metastore-admin-privileges) to analyze many of the APIs.

## Installation

### Credentials Needed

To set up SAT on Azure, you will need the following credentials:

- **Databricks Account ID**
- **Azure Tenant ID**
- **Azure Subscription ID**
- **Azure App Client ID** (obtained from App Registration)
- **Azure App Client Secret** (obtained from App Client Secrets)

### Setup Instructions

Follow these steps to execute SAT:

1. **Clone the SAT Repository:**
   
   Clone the SAT repository to your local machine using the following command:
   
   ```sh
   git clone https://github.com/databricks-industry-solutions/security-analysis-tool.git
   ```

> **Note:** Ensure the target workspace has a [profile](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/cli/profiles) set up in the [Databricks CLI](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/cli/tutorial).

2. **Run the `install.sh` script on your terminal:**

> To ensure that the install.sh script is executable, you need to modify its permissions using the chmod command.

   ```sh
   chmod +x install.sh
   ./install.sh
   ```

![](../gif/terminal-azure.gif)

Congratulations! 🎉 You are now ready to start using SAT. Please click [here](../setup.md#usage) for a detailed description on how to run and use it.


## Troubleshooting
Please review the FAQs and Troubleshooting resources documented [here](./faqs_and_troubleshooting.md) including a notebook to help diagnose your SAT setup.
If any issues arise during the installation process, please check your credentials and ensure that you have the appropriate permissions in your Azure cloud account. If you are still facing issues, please send your feedback and comments to sat@databricks.com. 

## References

- [Azure App Registration](https://docs.microsoft.com/en-us/azure/active-directory/develop/quickstart-register-app)
- [Databricks Service Principals](https://learn.microsoft.com/en-us/azure/databricks/admin/users-groups/service-principals#--databricks-and-microsoft-entra-id-formerly-azure-active-directory-service-principals)
