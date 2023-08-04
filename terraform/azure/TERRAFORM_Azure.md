## Setting up Terraform

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

Step 5: Set values in `terraform.tfvars` file

Using any editor set the values in the `terraform.tfvars` file. The descriptions of all the variables are located in the `variables.tf` file. Once the variables are set you are ready to run Terraform.

Further Documentation for some of the variables:

[workspace_id](https://learn.microsoft.com/en-us/azure/databricks/workspace/workspace-details#--workspace-instance-names-urls-and-ids)

[account_console_id](https://learn.microsoft.com/en-us/azure/databricks/administration-guide/account-settings/#locate-your-account-id)

[Azure Specific variables](https://github.com/databricks-industry-solutions/security-analysis-tool/blob/main/docs/setup.md#authentication-information) and navigate to the Azure section
Note: Please notice the instruction in the above link about adding the service principle with "Reader" role into the subscription level via Access control (IAM) using Role assignments under your subscription, Access control (IAM) section

Step 6: Set up [Azure CLI credentials](https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli#sign-in-interactively) for the provider block in `provider.tf`

The Azure CLI's default authentication method for logins uses a web browser and access token to sign in.

Run the login command and sign in with your account credentials in the browser. 

```sh
az login
```


## Run Terraform

Step 7: Terraform [Init](https://developer.hashicorp.com/terraform/cli/commands/init)

The terraform init command initializes a working directory containing configuration files and installs plugins for required providers.

```sh
terraform init
```

Step 8: Terraform [Plan](https://developer.hashicorp.com/terraform/cli/commands/plan)

The terraform plan command creates an execution plan, which lets you preview the changes that Terraform plans to make to your infrastructure. By default, when Terraform creates a plan it:

  * Reads the current state of any already-existing remote objects to make sure that the Terraform state is up-to-date.
  * Compares the current configuration to the prior state and noting any differences.
  * Proposes a set of change actions that should, if applied, make the remote objects match the configuration.

```sh
terraform plan
```

Step 9: Terraform [Apply](https://developer.hashicorp.com/terraform/cli/commands/apply)

The terraform apply command executes the actions proposed in a Terraform plan.

```sh
terraform apply
```

Step 10: Run Jobs

You now have two jobs ("SAT Initializer Notebook" & "SAT Driver Notebook"). Run "SAT Initializer Notebook" and when it completes run "SAT Driver Notebook". "SAT Initializer Notebook" should only be run once (although you can run it multiple times, it only needs to be run successfully one time), and "SAT Driver Notebook" can be run periodically (its scheduled to run once every Monday, Wednesday, and Friday). 

Step 11: SAT Dashboard

Go to the SQL persona, select the Dashboard icon in the left menu and then select the SAT Dashboard. Once the dashboard loads pick the Workspace from the dropdown and refresh the dashboard

Supplemental Documentation:

[Databricks Documentation Terraform](https://docs.databricks.com/dev-tools/terraform/index.html)

[Databricks Terraform Provider Docs](https://registry.terraform.io/providers/databricks/databricks/latest/docs)

Additional Considerations:

Your jobs may fail if there was a pre-existing secret scope named sat_scope when you run terraform apply. To remedy this, you will need to change the name of your secret scope in secrets.tf, re-run terraform apply, and then navigate to /Repos/<your_email_address>/security-analysis-tool.git/notebooks/Utils/initialize and change the secret scope name in  6 places (3 times in CMD 4 and 3 times in CMD 5). You then can re-run your failed jobs.

Congratulations!!! [Please review the setup documentation for the instructions on usage, FAQs and general understanding of SAT setup](https://github.com/databricks-industry-solutions/security-analysis-tool/blob/main/docs/setup.md)
