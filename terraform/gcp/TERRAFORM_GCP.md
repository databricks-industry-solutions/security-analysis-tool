## Setting up Terraform

> **SAT v0.2.0 or higher** brings full support for Unity Catalog. Now you can pick your catalog instead of hive_metastore. Plus, you get to choose your own schema name.

Step 1: [Install Terraform](https://developer.hashicorp.com/terraform/tutorials/aws-get-started/install-cli)

Step 2: [Install Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git) on local machine

Step 3: Git Clone Repo

```sh
git clone https://github.com/databricks-industry-solutions/security-analysis-tool.git
```

Step 4: Change Directories

```sh
cd security-analysis-tool/terraform/<cloud>/
```

Step 5: Generate a `terraform.tfvars` file base on `template.tfvars`

Using any editor set the values in the ``terraform.tfvars`` file. The descriptions of all the variables are located in the `variables.tf` file. Once the variables are set you are ready to run Terraform.

Further Documentation for some of the variables:

[workspace_id](https://docs.gcp.databricks.com/workspace/workspace-details.html#workspace-instance-names-urls-and-ids)

[account_console_id](https://docs.gcp.databricks.com/administration-guide/account-settings/#locate-your-account-id)

[GCP Specific variables](../../docs/setup.md#authentication-information) and navigate to the GCP section

> **Proxies are now supported as part of SAT. You can add your HTTP and HTTPS links to use your proxies.**
```json
{
    "http": "http://example.com",
    "https": "https://example.com"
}
```

## Run Terraform

Step 6: Terraform [Init](https://developer.hashicorp.com/terraform/cli/commands/init)

The terraform init command initializes a working directory containing configuration files and installs plugins for required providers.

```sh
terraform init
```

Step 7: Terraform [Plan](https://developer.hashicorp.com/terraform/cli/commands/plan)

The terraform plan command creates an execution plan, which lets you preview the changes that Terraform plans to make to your infrastructure. By default, when Terraform creates a plan it:

* Reads the current state of any already-existing remote objects to make sure that the Terraform state is up-to-date.
* Compares the current configuration to the prior state and noting any differences.
* Proposes a set of change actions that should, if applied, make the remote objects match the configuration.

```sh
terraform plan
```

Step 8: Terraform [Apply](https://developer.hashicorp.com/terraform/cli/commands/apply)

The terraform apply command executes the actions proposed in a Terraform plan.

```sh
terraform apply
```

Step 9: Run Jobs

You now have two jobs ("SAT Initializer Notebook" & "SAT Driver Notebook"). Run "SAT Initializer Notebook" and when it completes run "SAT Driver Notebook". "SAT Initializer Notebook" should only be run once (although you can run it multiple times, it only needs to be run successfully one time), and "SAT Driver Notebook" can be run periodically (its scheduled to run once every Monday, Wednesday, and Friday).

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

Step 10: SAT Dashboard

Go to the SQL persona, select the Dashboard icon in the left menu and then select the SAT Dashboard. Once the dashboard loads pick the Workspace from the dropdown and refresh the dashboard

Supplemental Documentation:

[Databricks Documentation Terraform](https://docs.databricks.com/dev-tools/terraform/index.html)

[Databricks Terraform Provider Docs](https://registry.terraform.io/providers/databricks/databricks/latest/docs)

Additional Considerations:

Your jobs may fail if there was a pre-existing secret scope named `sat_scope` when you run `terraform apply`. To remedy this, you will need to change the name of your secret scope in `secrets.tf`, re-run terraform apply, and then navigate to `Workspace -> Applications -> SAT-TF /notebooks/Utils/initialize` and change the secret scope name in  6 places (3 times in CMD 4 and 3 times in CMD 5). You then can re-run your failed jobs.

Congratulations!!! [Please review the setup documentation for the instructions on usage, FAQs and general understanding of SAT setup](https://github.com/databricks-industry-solutions/security-analysis-tool/blob/main/docs/setup.md)
