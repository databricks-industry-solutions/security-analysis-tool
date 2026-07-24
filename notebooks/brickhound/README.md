# BrickHound Permissions Analysis Notebooks

Graph-based permissions analysis for Databricks, integrated into SAT.

## Quick Start

### 1. Run Data Collection (First Time)

Execute the data collection job to build the permissions graph:

**Option A: Via Databricks UI**
- Navigate to: Workflows → Jobs
- Find: "BrickHound Permissions Analysis - Data Collection"
- Click: "Run Now"
- Wait: ~10-30 minutes (depends on account size)

**Option B: Run Notebook Directly**
- Open: `/notebooks/permission_analysis_data_collection.py`
- Click: "Run All"

### 2. Analyze Permissions

Use the interactive analysis notebooks:

| Notebook | Purpose |
|----------|---------|
| `01_principal_resource_analysis.py` | Query permissions: "Who can access what?" |
| `02_escalation_paths.py` | Find privilege escalation paths |
| `03_impersonation_analysis.py` | Analyze impersonation risks |
| `04_advanced_reports.py` | Generate compliance reports |
| `05_share_to_account.py` | Detect (and optionally remediate) resources shared with all account users |
| `06_privileged_non_idp_identities.py` | Detect (and optionally remediate) privileged identities that are not IdP-managed |
| `07_denylist_candidates.py` | Rank account groups by inactive members as account-denylist candidates |

> **Note:** `05`–`07` are **audit-log / account-SCIM based**, not graph based. They read
> `system.access.audit`, `system.access.workspaces_latest`, and the account SCIM API
> directly, so they do **not** require the data collection job to have run first. Each writes
> its own `brickhound_*` table and has a scheduled job (in both `terraform/common/` and the
> DABS template):
>
> - `05_share_to_account.py` → `brickhound_shared_to_account`. Detection-only by default; set
>   `remediate=yes` to auto-remove the "account users" ACL entry (SP must be a member of each
>   affected workspace).
> - `06_privileged_non_idp_identities.py` → `brickhound_privileged_non_idp`. Flags non-IdP
>   (no `externalId`) groups with Account/Workspace Admin, plus users/SPs with those roles
>   assigned directly. Opt-in remediation removes the `account_admin` role via SCIM.
> - `07_denylist_candidates.py` → `brickhound_denylist_candidates`. Ranks account groups by
>   inactive-member count (inactive = no `system.access.audit` activity in the window — a
>   heuristic). Feeds the "Account Denylist Builder" tab.

### 3. Web UI (Optional)

Access the interactive web interface:
```
https://<workspace-url>/apps/brickhound-sat
```

## Configuration

BrickHound automatically uses SAT's configuration:
- **Credentials**: From `sat_scope` secret scope
- **Schema**: From SAT's `analysis_schema_name`
- **Tables**: `brickhound_vertices`, `brickhound_edges`, `brickhound_collection_metadata`, `brickhound_shared_to_account`

No additional configuration needed if SAT is installed!

## Scheduling

- **Automatic**: Data collection runs every Sunday at 2 AM
- **Manual**: Run any time via job UI or notebook

## Integration with SAT

BrickHound complements SAT's security checks:
- **SAT**: Configuration security (encryption, network, policies)
- **BrickHound**: Permissions and access analysis

Both write to the same Unity Catalog schema for unified security analysis.

## Troubleshooting

**No data found?**
- Run `/notebooks/permission_analysis_data_collection.py` first
- Check job logs for errors

**Authentication failed?**
- Verify SAT is installed (`sat_scope` exists)
- Check service principal has Account Admin role

**Tables not found?**
- Verify catalog/schema in `00_config.py`
- Check Unity Catalog permissions

## Documentation

- **Integration Guide**: `/docs/BRICKHOUND_INTEGRATION.md`
- **Permissions Reference**: `/docs/brickhound_PERMISSIONS.md`
- **Main README**: `/docs/brickhound_README.md`
