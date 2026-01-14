# BrickHound Integration into SAT

## Overview

BrickHound is now integrated into SAT as a complementary permissions analysis capability, providing graph-based security analysis for Databricks environments.

## Architecture

```
SAT (Security Analysis Tool)
├── security_analysis_driver (Mon/Wed/Fri - config checks)
├── security_analysis_secrets_scanner (secrets scanning)
└── sat_scope credentials
    └── BrickHound (Permissions Analysis)
        ├── 01_data_collection.py (Weekly - permissions graph)
        ├── 02-05_*.py (Interactive analysis)
        ├── Web App (Gradio UI)
        └── Tables: brickhound_vertices, brickhound_edges, brickhound_collection_metadata
```

## Integration Benefits

- **Shared Credentials**: Uses SAT's `sat_scope` (no separate configuration)
- **Shared Storage**: Same Unity Catalog schema as SAT
- **Complementary Analysis**: SAT (config) + BrickHound (permissions) = Complete security
- **Unified Deployment**: Installed automatically with SAT

## Quick Start

1. **SAT must be installed first** (provides `sat_scope` and credentials)
2. **Run BrickHound data collection**: Workflows → Jobs → "BrickHound Permissions Analysis"
3. **Analyze**: Use notebooks in `/notebooks/brickhound/` or web app

## Key Changes from Standalone BrickHound

| Aspect | Standalone BrickHound | SAT Integration |
|--------|----------------------|----------------|
| Secret Scope | `brickhound` | `sat_scope` |
| Secret Keys | `account-id`, `sp-client-id`, `sp-client-secret` | `account-console-id`, `client-id`, `client-secret` |
| Catalog/Schema | Hardcoded `main.brickhound` | From `analysis_schema_name` secret |
| Table Names | `vertices`, `edges` | `brickhound_vertices`, `brickhound_edges` (namespaced) |
| Schedule | Not configured | Weekly (Sunday 2 AM) |

## Data Model

### Tables Created

All tables in SAT's `analysis_schema_name`:

- **brickhound_vertices**: All Databricks objects (50+ node types: users, groups, tables, etc.)
- **brickhound_edges**: Relationships (60+ types: permissions, memberships, etc.)
- **brickhound_collection_metadata**: Collection run tracking

### Table Naming

Tables are namespaced with `brickhound_` prefix to avoid conflicts with SAT tables:
- ✅ Keeps everything in one schema
- ✅ Clear separation from SAT tables
- ✅ Easy to identify BrickHound data

## Use Cases

1. **Access Audit**: "Who has access to production tables?"
2. **Privilege Escalation**: "Who can become a workspace admin?"
3. **Impersonation Risk**: "Who can run jobs as service principals?"
4. **Compliance Reporting**: "Generate SOC2 access report"

## Comparison: SAT vs. BrickHound

| Feature | SAT | BrickHound |
|---------|-----|------------|
| **Focus** | Configuration security | Permissions analysis |
| **Checks** | 116+ security checks | Graph-based queries |
| **Schedule** | Mon/Wed/Fri | Weekly (Sunday) |
| **Output** | Violations, scores | Permission paths, matrices |
| **Use Case** | "Is the configuration secure?" | "Who can access what?" |

## Deployment

### Automatic (with SAT)

BrickHound is deployed automatically when SAT is installed:
```bash
cd dabs
pip install -r requirements.txt
python main.py  # BrickHound included
```

### Manual Job Creation

If deploying via Terraform:
```bash
cd terraform
terraform apply  # Includes brickhound_job.tf
```

## Web App Deployment

Deploy the interactive UI:
```bash
cd app/brickhound
databricks apps deploy
```

Access at: `https://<workspace-url>/apps/brickhound-sat`

## Troubleshooting

### Data Collection Fails

**Error**: "Authentication failed"
- **Fix**: Verify service principal has Account Admin role
- **Fix**: Check credentials in `sat_scope`

**Error**: "Table already exists"
- **Fix**: Drop and recreate:
  ```sql
  DROP TABLE IF EXISTS {catalog}.{schema}.brickhound_vertices;
  DROP TABLE IF EXISTS {catalog}.{schema}.brickhound_edges;
  ```

### Analysis Notebooks Error

**Error**: "brickhound module not found"
- **Fix**: Run `%run ./install_brickhound_sdk` first

**Error**: "Table not found"
- **Fix**: Run data collection job first (`01_data_collection.py`)

### Web App Won't Load

**Error**: "Warehouse not started"
- **Fix**: Start SQL warehouse or update `WAREHOUSE_ID`

**Error**: "No data displayed"
- **Fix**: Verify tables have data, run data collection if empty

## Performance

| Account Size | Collection Time |
|--------------|-----------------|
| Small (<10 workspaces) | 5-10 minutes |
| Medium (10-50 workspaces) | 10-20 minutes |
| Large (>50 workspaces) | 20-40 minutes |

## Support

For issues or questions:
1. Check `/notebooks/brickhound/README.md`
2. Review job logs: Workflows → Jobs → Run → Logs
3. Contact SAT support team

## Documentation

- **Notebook Guide**: `/notebooks/brickhound/README.md`
- **Permissions Reference**: `/docs/brickhound_PERMISSIONS.md`
- **Original README**: `/docs/brickhound_README.md`
- **CLAUDE.md**: Integration details for AI assistance
