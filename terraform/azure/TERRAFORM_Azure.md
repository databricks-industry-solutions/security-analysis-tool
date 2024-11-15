## Setting up Terraform

> **SAT v0.2.0 or higher** brings full support for Unity Catalog. Now you can pick your catalog instead of hive_metastore. Plus, you get to choose your own schema name.

> **Note**: SAT requires at least one SAT set up in a workspace per Azure **subscription**. 

<b>Step 1</b>: [Install Terraform](https://developer.hashicorp.com/terraform/tutorials/aws-get-started/install-cli).

<b>Step 2</b>: [Install Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git) on local machine.

<b>Step 3</b>: Git Clone Repo.

```sh
git clone https://github.com/databricks-industry-solutions/security-analysis-tool.git
``` 

<b>Step 4</b>: Change Directories.

```sh
cd security-analysis-tool/terraform/<cloud>/
``` 

<b>Step 5</b>: Generate a `terraform.tfvars` file base on `template.tfvars`.

The descriptions of all the variables are located in the `variables.tf` file. Once the variables are set you are ready to run Terraform.

Azure specific variables can be obtained by following the [Azure Setup Guide](https://github.com/databricks-industry-solutions/security-analysis-tool/blob/main/docs/setup/azure.md).
>[!Note]
> The Service Principal requires:
> * "Reader" role into the subscription level via Access control (IAM).
> * [Accounts Admin role](https://learn.microsoft.com/en-us/azure/databricks/admin/users-groups/service-principals#--assign-account-admin-roles-to-a-service-principal)
> * [Admin role](https://learn.microsoft.com/en-us/azure/databricks/admin/users-groups/service-principals#assign-a-service-principal-to-a-workspace-using-the-account-console) for **each workspace**
> * Member of the [metastore admin group](https://learn.microsoft.com/en-us/azure/databricks/data-governance/unity-catalog/manage-privileges/admin-privileges#who-has-metastore-admin-privileges)

Further Documentation for some of the variables: [workspace_url](https://learn.microsoft.com/en-us/azure/databricks/workspace/workspace-details#workspace-instance-names-urls-and-ids), [workspace_id](https://learn.microsoft.com/en-us/azure/databricks/workspace/workspace-details#--workspace-instance-names-urls-and-ids), and [account_console_id](https://learn.microsoft.com/en-us/azure/databricks/administration-guide/account-settings/#locate-your-account-id)



<b>Step 6</b>: Set up [Azure CLI credentials](https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli#sign-in-interactively) for the provider block in `provider.tf`

The Azure CLI's default authentication method for logins uses a web browser and access token to sign in.

Run the login command and sign in with your account credentials in the browser. 

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

## Run Terraform

<b>Step 7</b>: Terraform [Init](https://developer.hashicorp.com/terraform/cli/commands/init)

The terraform init command initializes a working directory containing configuration files and installs plugins for required providers.

```sh
terraform init
```

<b>Step 8</b>: Terraform [Plan](https://developer.hashicorp.com/terraform/cli/commands/plan)

The terraform plan command creates an execution plan, which lets you preview the changes that Terraform plans to make to your infrastructure. By default, when Terraform creates a plan it:

  * Reads the current state of any already-existing remote objects to make sure that the Terraform state is up-to-date.
  * Compares the current configuration to the prior state and noting any differences.
  * Proposes a set of change actions that should, if applied, make the remote objects match the configuration.

```sh
terraform plan
```

<b>Step 9</b>: Terraform [Apply](https://developer.hashicorp.com/terraform/cli/commands/apply)

The terraform apply command executes the actions proposed in a Terraform plan.

```sh
terraform apply
```

<b>Step 10</b>: Run Jobs

You now have two jobs ("SAT Initializer Notebook" & "SAT Driver Notebook"). Run "SAT Initializer Notebook" and when it completes run "SAT Driver Notebook". "SAT Initializer Notebook" should only be run once (although you can run it multiple times, it only needs to be run successfully one time), and "SAT Driver Notebook" can be run periodically (its scheduled to run once every Monday, Wednesday, and Friday). 

<b>Step 11</b>: SAT Dashboard

Go to the SQL persona, select the Dashboard icon in the left menu and then select the SAT Dashboard. Once the dashboard loads pick the Workspace from the dropdown and refresh the dashboard

Supplemental Documentation:

[Databricks Documentation Terraform](https://docs.databricks.com/dev-tools/terraform/index.html)

[Databricks Terraform Provider Docs](https://registry.terraform.io/providers/databricks/databricks/latest/docs)

Additional Considerations:

Your jobs may fail if there was a pre-existing secret scope named sat_scope when you run terraform apply. To remedy this, you will need to change the name of your secret scope in secrets.tf, re-run terraform apply, and then navigate to Workspace -> Applications -> SAT-TF /notebooks/Utils/initialize and change the secret scope name in  6 places (3 times in CMD 4 and 3 times in CMD 5). You then can re-run your failed jobs.

Congratulations!!! [Please review the setup documentation for the instructions on usage, FAQs and general understanding of SAT setup](https://github.com/databricks-industry-solutions/security-analysis-tool/blob/main/docs/setup.md)
