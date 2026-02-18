## Setting up Terraform for Azure

> **SAT v0.2.0 or higher** introduces full support for Unity Catalog. allowing you to pick your catalog instead of `hive_metastore` and customize your schema name.
> **Note**: SAT requires at least one SAT set up in a workspace per Azure **subscription**. 

### Step 1: Install Required Tools
1. Install [Terraform](https://developer.hashicorp.com/terraform/tutorials/aws-get-started/install-cli).
2. Install [Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git) on your local machine.

### Step 2: Clone the Repository
Clone the Security Analysis Tool repository using:
```sh
git clone https://github.com/databricks-industry-solutions/security-analysis-tool.git
``` 

### Step 3: Navigate to the Terraform Directory
Navigate to the relevant cloud directory:
```sh
cd security-analysis-tool/terraform/<cloud>/
``` 

### Step 4: Configure Variables
1. Create a `terraform.tfvars` file using the `template.tfvars` file as a base.
2. Refer to the `variables.tf` for descriptions of the variables.
3. Set all required variables for your deployment.

#### Azure-Specific Configuration
* Follow the [Azure Setup Guide](https://github.com/databricks-industry-solutions/security-analysis-tool/blob/main/docs/setup/azure.md) for variable setup.

#### Service Principal Role Requirements:
* "Reader" role at the subscription level via Access control (IAM).
* [Accounts Admin role](https://learn.microsoft.com/en-us/azure/databricks/admin/users-groups/service-principals#--assign-account-admin-roles-to-a-service-principal)
* [Admin role](https://learn.microsoft.com/en-us/azure/databricks/admin/users-groups/service-principals#assign-a-service-principal-to-a-workspace-using-the-account-console) for **each workspace**
* Member of the [metastore admin group](https://learn.microsoft.com/en-us/azure/databricks/data-governance/unity-catalog/manage-privileges/admin-privileges#who-has-metastore-admin-privileges)

Refer to the documentation for [workspace_url](https://learn.microsoft.com/en-us/azure/databricks/workspace/workspace-details#workspace-instance-names-urls-and-ids), [workspace_id](https://learn.microsoft.com/en-us/azure/databricks/workspace/workspace-details#--workspace-instance-names-urls-and-ids), and [account_console_id](https://learn.microsoft.com/en-us/azure/databricks/administration-guide/account-settings/#locate-your-account-id)

### Step 5: Configure Azure CLI Credentials
1. Set up [Azure CLI credentials](https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli#sign-in-interactively) for the provider block in `provider.tf`.
2. Use the Azure CLI to log in. The CLI will open a web browser for authentication:
```sh
az login
```
> **Proxies are now supported as part of SAT. You can add your HTTP and HTTPS links to use your proxies.**
```json
{
    "http": "http://example.com",
    "https": "https://example.com"
}
```

### Step 6: Run Terraform Commands
1. Initialize Terraform:
```sh
terraform init
```
2. Plan Terraform Changes - create a plan to preview changes to your infrastructure:
```sh
terraform plan
```
3. Apply Terraform Plan - Execute the proposed changes:
```sh
terraform apply
```

### Step 7: Run Databricks Jobs
1. Run "SAT Initializer Notebook":
* This must be run successfully once. While it can be run multiple times, a single successful run is sufficient.
2. Run "SAT Driver Notebook":
* This notebook can be scheduled to run periodically (e.g., every Monday, Wednesday, and Friday).

### BrickHound App Deployment (Optional)

The BrickHound data collection job is automatically deployed by Terraform. To deploy the BrickHound web app for interactive permissions analysis, follow these steps:

#### 1. Deploy the App

Using the **Databricks CLI** (recommended):
```bash
databricks apps deploy brickhound-sat \
  --source-code-path /Workspace/Repos/SAT-TF/app/brickhound
```

Or using the **Databricks UI**:
1. Navigate to **Compute → Apps**
2. Click **Create App**
3. **Edit metadata** (Step 1):
   - App name: `permissions-analysis-app` (or your preferred name)
   - Description: `Databricks Permission Analysis companion app for SAT`
   - Click **Next: Configure**
4. Select source code path: `/Workspace/Repos/SAT-TF/app/brickhound`

#### 2. Configure App Resources

On the **Configure resources** page (Step 2):

**App resources:**
1. Click **+ Add resource**
2. Select **SQL warehouse**
3. Choose your warehouse (e.g., "SAT Warehouse" created by Terraform)
4. Permission: **Can use**
5. Resource key: `sql-warehouse`

**User authorization** (API Scopes - automatically configured):
The app requires these scopes (preview feature):
- `catalog.catalogs:read` - Read catalogs in Unity Catalog
- `catalog.schemas:read` - Read schemas in Unity Catalog
- `catalog.tables:read` - Read tables in Unity Catalog
- `sql` - Execute SQL and manage SQL resources

**Compute:**
- Instance size: **Medium** (Up to 2 vCPU, 6 GB memory) - sufficient for most use cases
- Can increase to **Large** if analyzing very large accounts

Click **Save** to complete configuration.

#### 3. Grant Unity Catalog Permissions

Grant the app's service principal access to BrickHound tables:
1. Copy the **service principal ID** from the app's **Authorization** tab
2. Run these SQL commands in your workspace (replace `<catalog>.<schema>` with your `analysis_schema_name`):

```sql
-- Grant catalog access (REQUIRED - Unity Catalog hierarchical permissions)
GRANT USE CATALOG ON CATALOG `<catalog>` TO `<service-principal-id>`;

-- Grant schema access
GRANT USE SCHEMA ON SCHEMA `<catalog>`.`<schema>` TO `<service-principal-id>`;

-- Grant table access
GRANT SELECT ON TABLE `<catalog>`.`<schema>`.brickhound_vertices TO `<service-principal-id>`;
GRANT SELECT ON TABLE `<catalog>`.`<schema>`.brickhound_edges TO `<service-principal-id>`;
GRANT SELECT ON TABLE `<catalog>`.`<schema>`.brickhound_collection_metadata TO `<service-principal-id>`;
```

**Note**: The `USE CATALOG` grant is critical. Without it, the app cannot access tables even with SELECT permissions due to Unity Catalog's hierarchical permission model.

**References:**
- [Deploy Databricks Apps](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/deploy)
- [Add Resources to Apps](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/resources)
- [Configure App Authorization](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth)

### Step 8: Access the SAT Dashboard
1. Navigate to the <b>SQL > Dashboard </b> in the left menu from the Databricks workspace.
2. Select the <b>SAT Dashboard</b>, pic a Workspace from the dropdown, and refresh the dashboard.

### Supplemental Documentation

* [Databricks Documentation Terraform](https://docs.databricks.com/dev-tools/terraform/index.html)
* [Databricks Terraform Provider Docs](https://registry.terraform.io/providers/databricks/databricks/latest/docs)

### Additional Considerations:

* If a pre-existing secret scope named `sat_scope` causes jobs to fail:
1. Rename the secret scope in `secrets.tf`
2. Re-run `terraform apply`.
3. Update the secret scope name in 6 locations (`CMD 4` and `CMD 5`) of `Workspace -> Applications -> SAT-TF/notebooks/Utils/initialize`.
4. Re-run failed jobs

Congratulations!!! [Please review the setup documentation for the instructions on usage, FAQs and general understanding of SAT setup](https://github.com/databricks-industry-solutions/security-analysis-tool/blob/main/docs/setup.md)
