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
- Open: `01_data_collection.py`
- Click: "Run All"

### 2. Analyze Permissions

Use the interactive analysis notebooks:

| Notebook | Purpose |
|----------|---------|
| `02_principal_resource_analysis.py` | Query permissions: "Who can access what?" |
| `03_escalation_paths.py` | Find privilege escalation paths |
| `04_impersonation_analysis.py` | Analyze impersonation risks |
| `05_advanced_reports.py` | Generate compliance reports |

### 3. Web UI (Optional)

Access the interactive web interface:
```
https://<workspace-url>/apps/brickhound-sat
```

## Configuration

BrickHound automatically uses SAT's configuration:
- **Credentials**: From `sat_scope` secret scope
- **Schema**: From SAT's `analysis_schema_name`
- **Tables**: `brickhound_vertices`, `brickhound_edges`, `brickhound_collection_metadata`

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
- Run `01_data_collection.py` first
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
