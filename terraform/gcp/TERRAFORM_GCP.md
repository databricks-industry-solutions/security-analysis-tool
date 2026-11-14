## Deploying SAT on GCP with Terraform

Terraform deploys the **Security Analysis Tool app** and the SQL warehouse it uses. Everything else — catalog/schema, account id, and account credentials — is configured in the app's own setup flow after it is deployed, and the app provisions its own collection jobs and Genie space. There is no secret scope and no Terraform-created jobs.

Step 1: [Install Terraform](https://developer.hashicorp.com/terraform/tutorials/aws-get-started/install-cli)

Step 2: [Install Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)

Step 3: Clone this repository

```sh
git clone https://github.com/databricks-industry-solutions/security-analysis-tool.git
```

Step 4: Change into the GCP module

```sh
cd security-analysis-tool/terraform/gcp/
```

Step 5: Create `terraform.tfvars` from `template.tfvars`

Set the values with any editor; descriptions are in `variables.tf`. You only need:

- `databricks_url` — the workspace URL.
- `client_id` / `client_secret` — the service principal Terraform authenticates as.
- `sqlw_id` *(optional)* — `new` to create a warehouse, or an existing 16-character warehouse id.

See the [GCP authentication section](../../docs/setup.md#authentication-information) of the setup docs for how to create the service principal.

## Run Terraform

Step 6: `terraform init`

Step 7: `terraform plan`

Step 8: `terraform apply`

This creates the SQL warehouse (if `sqlw_id = "new"`) and the Security Analysis app, binding the warehouse to the app's service principal.

Step 9: Deploy the app code and complete setup

The app shell exists after `apply`; deploy its source, then open it:

```sh
databricks apps deploy sat-permissions-exp \
  --source-code-path <workspace path to app/security-analysis-tool>
```

Open the app from **Compute → Apps** and complete the in-app setup — choose the catalog/schema, enter your account id and account API credentials. The app stores the credentials as Unity Catalog secrets, creates and owns its results schema, and provisions its collection jobs and Genie space. See `app/security-analysis-tool/README.md`.

## Additional Considerations

If `terraform apply` fails with `An app with the same name already exists` for `sat-permissions-exp` (for example because the app was previously deployed via the DABS installer, or prior Terraform state was lost), import the existing app and re-apply:

```bash
terraform import module.common.databricks_app.brickhound sat-permissions-exp
terraform apply
```

Supplemental documentation:

- [Databricks Terraform documentation](https://docs.databricks.com/dev-tools/terraform/index.html)
- [Databricks Terraform Provider docs](https://registry.terraform.io/providers/databricks/databricks/latest/docs)
- [SAT setup documentation](https://github.com/databricks-industry-solutions/security-analysis-tool/blob/main/docs/setup.md)
