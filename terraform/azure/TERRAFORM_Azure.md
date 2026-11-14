## Deploying SAT on Azure with Terraform

Terraform deploys the **Security Analysis Tool app** and the SQL warehouse it uses, and registers the SAT service principal. Everything else — catalog/schema, account id, and account credentials — is configured in the app's own setup flow after it is deployed, and the app provisions its own collection jobs and Genie space. There is no secret scope and no Terraform-created jobs.

> **Note**: SAT requires at least one SAT setup per Azure **subscription**.

### Step 1: Install Required Tools
1. Install [Terraform](https://developer.hashicorp.com/terraform/tutorials/aws-get-started/install-cli).
2. Install [Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git).

### Step 2: Clone the Repository
```sh
git clone https://github.com/databricks-industry-solutions/security-analysis-tool.git
```

### Step 3: Navigate to the Azure module
```sh
cd security-analysis-tool/terraform/azure/
```

### Step 4: Configure Variables
Create `terraform.tfvars` from `template.tfvars` (descriptions are in `variables.tf`). You only need:

- `databricks_url` — the workspace URL.
- `client_id` — the Application (client) ID registered as the SAT service principal and added to the workspace admins group.
- `sqlw_id` *(optional)* — `new` to create a warehouse, or an existing 16-character warehouse id.

#### Service Principal Role Requirements
The SAT service principal (the account credentials you later enter in the app) needs:
* "Reader" role at the subscription level via Access control (IAM).
* [Account Admin role](https://learn.microsoft.com/en-us/azure/databricks/admin/users-groups/service-principals#--assign-account-admin-roles-to-a-service-principal).
* [Workspace Admin role](https://learn.microsoft.com/en-us/azure/databricks/admin/users-groups/service-principals#assign-a-service-principal-to-a-workspace-using-the-account-console) for **each workspace**.
* Member of the [metastore admin group](https://learn.microsoft.com/en-us/azure/databricks/data-governance/unity-catalog/manage-privileges/admin-privileges#who-has-metastore-admin-privileges).

### Step 5: Authenticate the Databricks provider
The Azure provider block authenticates through the Azure CLI. Log in (the CLI opens a browser):
```sh
az login
```

### Step 6: Run Terraform
```sh
terraform init
terraform plan
terraform apply
```
This creates the SQL warehouse (if `sqlw_id = "new"`) and the Security Analysis app, binding the warehouse to the app's service principal.

### Step 7: Deploy the app code and complete setup
The app shell exists after `apply`; deploy its source, then open it:
```sh
databricks apps deploy sat-permissions-exp \
  --source-code-path <workspace path to app/security-analysis-tool>
```
Open the app from **Compute → Apps** and complete the in-app setup — choose the catalog/schema, enter your account id and account API credentials. The app stores the credentials as Unity Catalog secrets, creates and owns its results schema, and provisions its collection jobs and Genie space. See `app/security-analysis-tool/README.md`.

### Additional Considerations
* If `terraform apply` fails with `An app with the same name already exists` for `sat-permissions-exp` (for example because the app was previously deployed via the DABS installer, or prior Terraform state was lost), import the existing app and re-apply:

```bash
terraform import module.common.databricks_app.brickhound sat-permissions-exp
terraform apply
```

### Supplemental Documentation
* [Databricks Terraform documentation](https://docs.databricks.com/dev-tools/terraform/index.html)
* [Databricks Terraform Provider docs](https://registry.terraform.io/providers/databricks/databricks/latest/docs)
* [SAT setup documentation](https://github.com/databricks-industry-solutions/security-analysis-tool/blob/main/docs/setup.md)
