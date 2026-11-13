# Security Analysis Tool (SAT)

A Databricks App for security analysis of your Databricks account: permission
analysis, hardcoded-secret detection, and a natural-language security assistant,
all in one interface.

The app is the single, supported way to run SAT. It serves the UI, manages its own
collection jobs, and reads the results from Unity Catalog.

## Capabilities

- **Permission Analysis** — explores the account's access graph (BrickHound):
  who can access a resource, what a principal can reach, privilege-escalation
  paths, resources shared to the whole account, privileged non-IdP identities,
  and denylist candidates.
- **Credential Exposure** — surfaces API keys and tokens found hardcoded in
  notebook source and cluster configurations, scanned with TruffleHog.
- **Data Collection** — shows the status of the collection jobs and lets you
  trigger a fresh run.
- **Security Assistant** — answers natural-language questions over the findings,
  backed by a Databricks Genie space and a model-serving endpoint.
- **Settings & setup** — first-run setup captures the catalog/schema, warehouse,
  and account credentials; credentials are stored as Unity Catalog secrets.

## Architecture

```
Security Analysis Tool (Flask app — app.py)
    ↓ SQL Warehouse
Unity Catalog results schema  {catalog}.{schema}
    • brickhound_vertices / brickhound_edges / brickhound_collection_metadata
    • brickhound_shared_to_account / brickhound_privileged_non_idp / brickhound_denylist_candidates
    • notebooks_secret_scan_results / clusters_secret_scan_results
```

The app **provisions its own collection jobs**. It bundles the collection
notebooks and, after setup, creates and schedules the permissions-analysis and
secret-scanning jobs on serverless compute. There is no separate job to install
or wire up by hand — the app owns their lifecycle.

Configuration is read at runtime from the config the in-app setup flow writes
(`app_config.json` in the app service principal's home); account credentials are
read from Unity Catalog secrets. Nothing is baked into the deploy.

## Installation

SAT is installed with one of the repo's installers, which deploy this app:

- **Terraform** — `terraform/` (`databricks_app` resource).
- **Databricks Asset Bundles** — `dabs/` (`dabs/setup.sh`).

After the app is deployed, open it and complete the first-run setup (catalog/
schema, SQL warehouse, account ID, and account API credentials). The app then
provisions and schedules its collection jobs and begins populating the results
schema. See the top-level repository docs for the full install walkthrough.

### Permissions

The app runs under its own service principal. That identity needs, on the results
schema it uses:

- `USE CATALOG` on the catalog and `USE SCHEMA` on the schema
- `SELECT` on the schema (to read the results tables)
- `CREATE SECRET` on the schema (it gets this by owning the schema it creates at
  setup) so it can store account credentials as Unity Catalog secrets

If you drop and recreate the schema or tables, re-grant these — Unity Catalog
privileges do not survive a DROP/CREATE.

## Credentials

Account API credentials (`client-id` / `client-secret`) are stored as **Unity
Catalog secrets** in the results schema (`{catalog}.{schema}.<key>`). The app
writes them from the Settings screen and the collection jobs read them from the
same location. SAT no longer uses a `sat_scope` secret scope.

The secret value is never returned to the browser; Settings can reveal the stored
client ID (an identifier) but never the secret.

## Configuration

Runtime configuration comes from the setup flow, not deploy-time environment. The
`app.yaml` only sets the port and health check. A few environment variables are
honored when present (useful for local development or to pre-seed an install):

- `WAREHOUSE_ID` / `DATABRICKS_WAREHOUSE_ID` — SQL warehouse for queries
- `SAT_SCHEMA` / `BRICKHOUND_SCHEMA` — pre-seed the results schema as
  `<catalog>.<schema>` and skip the welcome screen
- `GENIE_SPACE_ID` — Genie space backing the assistant
- `DATABRICKS_HOST` — workspace URL (auto-set in Databricks Apps)

## Local development

```bash
cd app/security-analysis-tool
pip install -r requirements.txt

export DATABRICKS_HOST="https://your-workspace.cloud.databricks.com"
export DATABRICKS_TOKEN="dapi..."          # or a client id/secret pair
export WAREHOUSE_ID="<warehouse-id>"
export SAT_SCHEMA="<catalog>.<schema>"

python app.py
```

Then open http://localhost:8000.

## Security notes

- The app reveals sensitive security information — restrict access to authorized
  personnel.
- Grant the app's service principal read access to the results tables; it does
  not need write access to the graph data.
- Queries escape user input, but treat the app as a privileged, read-mostly tool.

## References

- [BloodHound](https://github.com/SpecterOps/BloodHound) — attack-path analysis,
  which inspired the permission graph model
- [Databricks Apps](https://docs.databricks.com/dev-tools/databricks-apps/index.html)
- [TruffleHog](https://github.com/trufflesecurity/trufflehog) — the secret scanner
