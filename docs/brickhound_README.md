# Permissions Analysis Tool

**Six Degrees of Databricks Admin**

Permissions Analysis Tool is a security analysis tool for Databricks environments. It maps privilege relationships across Databricks objects to identify attack paths and privilege escalation opportunities.

**🚀 Runs entirely on Databricks** - No external infrastructure needed. See [DATABRICKS_SETUP.md](DATABRICKS_SETUP.md) for setup.

## Overview

Permissions Analysis Tool leverages graph theory to reveal hidden relationships within Databricks identity and access management systems. Using GraphFrames on Databricks Spark, it analyzes complex privilege relationships across:

- **Users & Groups**: Account and workspace-level identities
- **Workspaces**: Databricks workspace configurations
- **Clusters**: Interactive and job clusters
- **Notebooks**: Code assets and their permissions
- **Jobs**: Scheduled workflows
- **SQL Warehouses**: Query engines
- **Unity Catalog Objects**: Catalogs, schemas, tables, volumes, functions
- **Secret Scopes**: Credential management
- **Repos**: Git integrations
- **Instance Pools**: Cluster resource pools

## Architecture

**Permissions Analysis Tool runs entirely on Databricks** - no external infrastructure needed.

```
┌─────────────────────────────────────────────────────────┐
│              DATABRICKS WORKSPACE                       │
│                                                         │
│  ┌────────────────────────────────────────────────────┐   │
│  │     Permissions Analysis Tool Collector Notebook   │   │
│  │   (Databricks SDK + REST API)                  │   │
│  └──────────────────┬─────────────────────────────┘   │
│                     │                                   │
│                     ▼                                   │
│  ┌────────────────────────────────────────────────┐   │
│  │     Delta Lake Graph Storage                   │   │
│  │   Catalog: brickhound                          │   │
│  │   Schema: graph                                │   │
│  │     - vertices (nodes)                         │   │
│  │     - edges (relationships)                    │   │
│  └──────────────────┬─────────────────────────────┘   │
│                     │                                   │
│                     ▼                                   │
│  ┌────────────────────────────────────────────────┐   │
│  │     GraphFrames Analysis Engine                │   │
│  │   (Spark + GraphFrames on Databricks)          │   │
│  └──────────────────┬─────────────────────────────┘   │
│                     │                                   │
│                     ▼                                   │
│  ┌────────────────────────────────────────────────┐   │
│  │     Visualization & Dashboards                 │   │
│  │   (Plotly + NetworkX in Notebooks)             │   │
│  └────────────────────────────────────────────────┘   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Key Benefits**:
- ✅ **No external dependencies** - Everything runs on Databricks
- ✅ **Data never leaves your workspace** - Stored in Delta Lake
- ✅ **Native authentication** - Uses workspace context automatically
- ✅ **Scalable** - Leverage Spark for large-scale analysis
- ✅ **Integrated** - Results viewable in Databricks SQL, notebooks, and dashboards

## Features

### 🎯 Interactive Web App (NEW!)
- ✨ **User-friendly web interface** for permission analysis
- 🔍 **9 interactive features** across two categories:
  - **Analysis Tools**: Principal Analysis, Resource Analysis, Escalation Paths, Impersonation Paths
  - **Security Reports**: High Privilege, Isolated, Orphaned, Over-Privileged, Secret Scopes
- 📊 **Real-time results** - No code required
- 🚀 **Deploy as Databricks App** - One-click deployment
- 📱 **Share with security team** - Secure web access

**→ See [app/README.md](app/README.md) for deployment guide**

### Data Collection
- ✅ Enumerate all Databricks objects via REST API
- ✅ Extract permission relationships
- ✅ Map group memberships and role assignments
- ✅ Capture Unity Catalog grants
- ✅ Support for both Account-level and Workspace-level APIs

### Graph Analysis
- 🔍 Find privilege escalation paths
- 🔍 Identify over-privileged users
- 🔍 Discover orphaned resources
- 🔍 Map blast radius of compromised identities
- 🔍 Detect permission inheritance chains

### Visualization
- 📊 Interactive graph visualizations
- 📊 Path highlighting
- 📊 Risk scoring
- 📊 Export capabilities

## Quick Start

### Prerequisites
- **Databricks Workspace** (AWS, Azure, or GCP)
- **DBR 13.3 LTS or higher** (for Unity Catalog support)
- **Permissions**: Workspace Admin (minimum) or Metastore Admin (recommended)  
  See [PERMISSIONS.md](PERMISSIONS.md) for detailed permission requirements
- **Cluster** with access mode: Shared or Single User

### Installation (On Databricks)

BrickHound runs entirely within your Databricks workspace. No external servers or local setup required.

#### Step 1: Clone or Upload Notebooks

**Option A: Using Repos (Recommended)**
1. In Databricks workspace, go to **Repos**
2. Click **Add Repo**
3. Enter URL: `https://github.com/arunpamulapati/BrickHound`
4. All notebooks and code will be available in your workspace

**Option B: Manual Upload**
1. Download this repository
2. Import the `notebooks/` folder into your Databricks workspace

#### Step 2: Create a Cluster (or use existing)

Create or use any cluster with:
- **DBR**: 13.3 LTS or higher
- **Access Mode**: Shared or Single User
- **Libraries**: ✅ Installed automatically by notebooks!

#### Step 3: Run Collection Notebook

1. Open `notebooks/permission_analysis_data_collection.py`
2. Attach to your cluster
3. Run all cells - libraries install automatically!
4. The notebook uses your workspace context (no tokens needed!)
5. Data is saved to Delta Lake tables in your workspace

**First run**: Takes a few extra minutes to install libraries. Subsequent runs are faster.

#### Step 4: Analyze and Visualize

Run the analysis notebooks:
- `01_principal_resource_analysis.py` - Principal and resource permission queries
- `02_escalation_paths.py` - Privilege escalation analysis
- `03_impersonation_analysis.py` - Impersonation path finding
- `04_advanced_reports.py` - Comprehensive security reports

## Project Structure

```
Permissions Analysis Tool/
├── app/                           # 🎯 WEB APP - Interactive Gradio UI
│   ├── app.py                     # Main Gradio application (7 analyses)
│   ├── app.yaml                   # Databricks App configuration
│   ├── requirements.txt           # App dependencies
│   └── README.md                  # App deployment guide
│
├── notebooks/                      # 👈 START HERE - Databricks Notebooks
│   ├── 00_config.py               # ⚙️  Configuration (catalog/schema settings)
│   ├── 00_analysis_common.py      # 📋 Shared analysis setup and utilities
│   ├── permission_analysis_data_collection.py      # 📊 Data collection via Databricks SDK
│   ├── 01_principal_resource_analysis.py  # 🔍 Principal and resource queries
│   ├── 02_escalation_paths.py     # ⚡ Privilege escalation path analysis
│   ├── 03_impersonation_analysis.py      # 🎭 Impersonation path finding
│   └── 04_advanced_reports.py     # 📈 Security reports (High Privilege, Isolated, Orphaned, etc.)
│
├── brickhound/                    # Python library (auto-imported in notebooks)
│   ├── collector/
│   │   └── core.py               # Main collector orchestrator
│   ├── graph/
│   │   ├── schema.py             # Delta Lake schema definitions
│   │   ├── builder.py            # Graph construction logic
│   │   └── permissions_resolver.py # Recursive permission analysis engine
│   └── utils/
│       ├── api_client.py         # Databricks SDK wrapper
│       └── config.py             # Configuration classes
│
├── requirements.txt              # For local development only
├── setup.py                      # Package setup
└── README.md                     # This file
```

**👉 START HERE**: See [DATABRICKS_SETUP.md](DATABRICKS_SETUP.md) for complete setup instructions.

**Quick Start**:
1. Add repo to Databricks
2. Update `CATALOG` in `notebooks/00_config.py` (default: "main")
3. Run `notebooks/permission_analysis_data_collection.py` to collect data
4. **Option A:** Deploy `app/` as Databricks App (user-friendly web UI) - update `app.yaml` first
5. **Option B:** Run analysis notebooks directly (for deep dives)

## Databricks Objects Mapped

### Identity & Access
- Users (account & workspace)
- Groups (account & workspace)
- Service Principals
- Entitlements

### Compute Resources
- Clusters (all-purpose, job, SQL)
- Instance Pools
- Cluster Policies

### Data & Analytics
- Unity Catalog: Catalogs, Schemas, Tables, Views, Volumes, Functions
- Legacy Hive Metastore objects
- SQL Warehouses

### Development Assets
- Notebooks
- Repos
- Libraries
- MLflow Models & Experiments

### Orchestration
- Jobs
- Job runs
- Pipelines (Delta Live Tables)

### Security & Governance
- Secret Scopes
- Tokens
- IP Access Lists

## Important Notes

### Unity Catalog Requirement
Permissions Analysis Tool stores data in Delta Lake using Unity Catalog. You need:
- An existing Unity Catalog catalog (e.g., `main` or custom catalog)
- Permission to CREATE SCHEMA in that catalog
- The collection notebook will verify catalog exists and help you choose one

### Metadata Storage
Graph metadata (properties, permissions details) is stored as JSON strings in Delta Lake columns. This ensures compatibility with Spark DataFrame operations.

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

```
Copyright 2025 Arun Pamulapati

Licensed under the Apache License, Version 2.0
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

## Security & Permissions

Permissions Analysis Tool requires read permissions to collect data. See [PERMISSIONS.md](PERMISSIONS.md) for:
- Minimum required permissions
- Recommended service principal setup
- Permission scoping options
- Security best practices

**Summary**:
- **Minimum**: Workspace User (limited visibility)
- **Recommended**: Workspace Admin + Metastore Admin
- **Production**: Service Principal with OAuth (see setup guide)

## Acknowledgments

Built for the Databricks security community.

## Roadmap

- [ ] Initial data collector implementation
- [ ] Delta Lake graph schema
- [ ] GraphFrames integration
- [ ] Pre-built attack path queries
- [ ] Interactive visualizations
- [ ] CI/CD for Databricks deployment
- [ ] Multi-workspace support
- [ ] Integration with security tools (SIEM, etc.)

