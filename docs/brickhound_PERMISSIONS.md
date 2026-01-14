# Permissions Analysis Tool Permissions Guide

This document describes the permissions required to run Permissions Analysis Tool effectively.

## TL;DR - Quick Summary

**Minimum Required**: Workspace User with read permissions  
**Recommended**: Workspace Admin  
**Optimal**: Account Admin (for account-level objects) + Metastore Admin (for Unity Catalog)

## Authentication Methods

### 1. Personal Access Token (PAT)
- **Best for**: Manual/ad-hoc collection, testing
- **How to create**: User Settings → Developer → Access Tokens
- **Permissions**: Inherits the user's permissions

### 2. Service Principal with OAuth
- **Best for**: Automated/scheduled collection, production use
- **How to create**: Account Console → Service Principals → Create
- **Permissions**: Explicitly granted, follows least-privilege principle

## Required Permissions by Feature

### Core Collection (Users, Groups, Service Principals)

| Object Type | Required Permission | API Endpoint | Notes |
|-------------|-------------------|--------------|-------|
| Users | `users:read` | `/api/2.0/preview/scim/v2/Users` | Workspace admin or account admin |
| Groups | `groups:read` | `/api/2.0/preview/scim/v2/Groups` | Workspace admin or account admin |
| Service Principals | `service-principals:read` | `/api/2.0/preview/scim/v2/ServicePrincipals` | Workspace admin or account admin |

**Minimum Role**: Workspace Admin

### Compute Resources

| Object Type | Required Permission | What's Collected |
|-------------|-------------------|------------------|
| Clusters | Cluster read access | All clusters visible to user |
| Cluster Permissions | `CAN_MANAGE` on cluster or Admin | ACLs for each cluster |
| Instance Pools | Pool read access | Pool configurations |
| Cluster Policies | Policy read access | Policy definitions |

**Minimum Role**: Workspace User (sees only their own clusters)  
**Recommended**: Workspace Admin (sees all clusters + permissions)

### Jobs & Orchestration

| Object Type | Required Permission | What's Collected |
|-------------|-------------------|------------------|
| Jobs | Job read access | Job definitions and owners |
| Job Permissions | `CAN_MANAGE` on job or Admin | Job ACLs |
| Pipelines (DLT) | Pipeline read access | DLT pipeline configurations |

**Minimum Role**: Workspace User (limited visibility)  
**Recommended**: Workspace Admin

### Workspace Objects

| Object Type | Required Permission | What's Collected |
|-------------|-------------------|------------------|
| Notebooks | Workspace read access | Notebook paths and basic info |
| Notebook Permissions | `CAN_MANAGE` or Admin | Notebook ACLs |
| Directories | Workspace read access | Folder structure |
| Repos | Repo read access | Git repo configurations |

**Minimum Role**: Workspace User (limited to their folders)  
**Recommended**: Workspace Admin

### Unity Catalog

| Object Type | Required Permission | What's Collected |
|-------------|-------------------|------------------|
| Catalogs | `USE CATALOG` | Catalog metadata |
| Catalog Grants | Metastore admin or `OWNER` | Catalog-level privileges |
| Schemas | `USE SCHEMA` | Schema metadata |
| Schema Grants | Metastore admin or schema `OWNER` | Schema-level privileges |
| Tables/Views | `SELECT` | Table metadata |
| Table Grants | Metastore admin or table `OWNER` | Table-level privileges |
| Volumes | `READ VOLUME` | Volume metadata |
| Volume Grants | Metastore admin or volume `OWNER` | Volume-level privileges |
| Functions | `EXECUTE` | Function metadata |

**Minimum Role**: Workspace User with UC access (limited visibility)  
**Recommended**: Metastore Admin (full visibility of all grants)

### SQL Warehouses

| Object Type | Required Permission | What's Collected |
|-------------|-------------------|------------------|
| Warehouses | Warehouse read access | Warehouse configurations |
| Warehouse Permissions | `CAN_MANAGE` or Admin | Warehouse ACLs |

**Minimum Role**: Workspace User (sees accessible warehouses)  
**Recommended**: Workspace Admin

### Secrets

| Object Type | Required Permission | What's Collected |
|-------------|-------------------|------------------|
| Secret Scopes | Scope read access | Scope names and types |
| Secret Scope Permissions | `MANAGE` on scope or Admin | Scope ACLs |

**Note**: Secret values are never collected, only metadata and permissions.

**Minimum Role**: Workspace User (sees own scopes)  
**Recommended**: Workspace Admin

## Recommended Permission Configurations

### Configuration 1: Read-Only Security Analyst

**Use Case**: Security team member doing manual analysis

```
Role: Workspace Admin
Additional UC Permissions: 
  - Metastore: USE CATALOG on all catalogs
  - Can see most objects and permissions
  - Cannot see all Unity Catalog grants without metastore admin
```

**Collection Coverage**: ~85%

### Configuration 2: Service Principal for Automated Collection (Recommended)

**Use Case**: Scheduled/automated Permissions Analysis Tool runs

**Setup Steps**:

1. **Create Service Principal** (Account Admin required):
   ```bash
   # Via Databricks CLI
   databricks service-principals create --display-name "Permissions Analysis Collector"
   ```

2. **Grant Workspace Permissions**:
   - Add SP to workspace
   - Grant "Workspace Admin" role
   
3. **Grant Unity Catalog Permissions**:
   ```sql
   -- Grant metastore admin (for full visibility)
   ALTER METASTORE <metastore_name> OWNER TO 'Permissions Analysis Collector';

   -- OR grant specific permissions per catalog (for limited visibility)
   GRANT USE CATALOG, USE SCHEMA ON CATALOG <catalog_name> TO 'Permissions Analysis Collector';
   ```

4. **Generate OAuth Credentials**:
   - Account Console → Service Principals → Permissions Analysis Collector
   - Generate Secret
   - Store client_id and client_secret securely

5. **Configure Permissions Analysis Tool**:
   ```bash
   DATABRICKS_HOST=https://your-workspace.cloud.databricks.com
   DATABRICKS_CLIENT_ID=<sp_client_id>
   DATABRICKS_CLIENT_SECRET=<sp_client_secret>
   ```

**Collection Coverage**: 95-100%

### Configuration 3: Metastore Admin User

**Use Case**: Complete security audit with full visibility

```
Role: Workspace Admin + Metastore Admin
Collection Coverage: 100%
```

**Setup**:
```sql
-- Grant metastore admin
ALTER METASTORE <metastore_name> OWNER TO 'user@company.com';
```

## Permission Checks

Before running Permissions Analysis Tool, verify you have the necessary permissions:

### Check Workspace Permissions

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Check if you can list users (requires admin)
try:
    users = list(w.users.list())
    print(f"✓ Can list users: {len(users)} users found")
except Exception as e:
    print(f"✗ Cannot list users: {e}")

# Check if you can list groups
try:
    groups = list(w.groups.list())
    print(f"✓ Can list groups: {len(groups)} groups found")
except Exception as e:
    print(f"✗ Cannot list groups: {e}")
```

### Check Unity Catalog Permissions

```sql
-- Check if you can see grants
SHOW GRANTS ON CATALOG <catalog_name>;

-- Check metastore ownership
DESCRIBE METASTORE;
```

## What Gets Collected with Different Permission Levels

| Permission Level | Users/Groups | Clusters | Jobs | UC Objects | UC Grants | Permissions/ACLs |
|-----------------|--------------|----------|------|------------|-----------|------------------|
| **Regular User** | ❌ | Own only | Own only | Limited | ❌ | Own only |
| **Workspace Admin** | ✅ | All | All | All visible | Partial | All |
| **+ Metastore Admin** | ✅ | All | All | All | All | All |
| **Account Admin** | ✅ | All (+ account) | All | All | All | All |

## Security Best Practices

### 1. Use Service Principal for Production

**Why**: 
- No human credentials stored
- Easier to rotate secrets
- Clear audit trail
- Follows principle of least privilege

### 2. Limit Permissions Scope

If you don't need Unity Catalog analysis:
```python
collector_config = CollectorConfig(
    collect_unity_catalog=False,  # Skip UC collection
    collect_permissions=True,
)
```

### 3. Store Credentials Securely

**DON'T**:
```python
token = "dapi1234567890..."  # Hardcoded token
```

**DO**:
```python
# Use Databricks secrets
token = dbutils.secrets.get(scope="brickhound", key="token")

# Or environment variables
from dotenv import load_dotenv
config = DatabricksConfig.from_env()
```

### 4. Rotate Credentials Regularly

- PATs: Rotate every 90 days
- Service Principal secrets: Rotate every 180 days
- Monitor for suspicious access patterns

### 5. Audit Permissions Analysis Tool Usage

Permissions Analysis Tool reads data, so audit logs will show:
- API calls made by the collector
- Objects accessed
- Permissions queried

Review these logs regularly to ensure appropriate use.

## Troubleshooting Permission Issues

### Error: "User is not authorized"

**Cause**: Insufficient permissions for the operation  
**Solution**: 
1. Verify you have workspace admin role
2. Check if Unity Catalog objects require metastore admin
3. Try with a more privileged account to identify the gap

### Error: "Cannot list users/groups"

**Cause**: Not a workspace admin  
**Solution**: 
- Request workspace admin role from account admin
- Or use account admin credentials

### Error: "PERMISSION_DENIED" for Unity Catalog

**Cause**: Missing UC grants  
**Solution**:
```sql
-- Grant necessary UC permissions
GRANT USE CATALOG, USE SCHEMA ON CATALOG <catalog> TO `user@company.com`;
```

### Partial Data Collection

**Symptom**: Some objects are missing  
**Cause**: Permission scoping  
**Solution**:
- Review what permissions you have
- Check the logs for skipped objects
- Request additional permissions as needed

## Example: Minimal Service Principal Setup

For organizations wanting the absolute minimum permissions:

```python
# This SP can collect basic info but not all permissions
# Good for initial assessment

# 1. Create SP (account admin required)
# 2. Add to workspace as "User" role
# 3. Grant specific permissions:

# Cluster read
sp.add_to_group("users")  # Basic workspace access

# For Unity Catalog (optional):
GRANT USE CATALOG ON CATALOG main TO `brickhound-sp`;
GRANT USE SCHEMA ON SCHEMA main.default TO `brickhound-sp`;

# Configure Permissions Analysis Tool to skip permission collection
collector_config = CollectorConfig(
    collect_permissions=False,  # Skip detailed ACLs
    collect_unity_catalog=True,  # Still collect UC metadata
)
```

This will collect object metadata but not detailed permission information.

## FAQ

**Q: Can I run Permissions Analysis Tool as a regular user?**
A: Yes, but you'll only see objects you have access to. For security analysis, you need admin permissions for full visibility.

**Q: Do I need account admin permissions?**  
A: Not required for workspace analysis. Only needed if you want to collect account-level objects (account users, account groups, etc.).

**Q: Will Permissions Analysis Tool modify anything?**
A: No. Permissions Analysis Tool only reads data via GET API calls. It never modifies permissions or objects.

**Q: Can I use a personal access token in production?**  
A: Not recommended. Use a service principal with OAuth for production deployments.

**Q: What if I don't have metastore admin?**  
A: You can still collect Unity Catalog metadata, but grant information will be incomplete. Request read-only metastore access from your admin.

**Q: Is my data sent anywhere?**
A: No. Permissions Analysis Tool runs entirely within your environment. All data stays in your Databricks workspace (Delta Lake tables).

## Next Steps

1. Assess your current permissions
2. Choose the appropriate configuration above
3. Request necessary permissions from your admin
4. Set up authentication (PAT or Service Principal)
5. Run a test collection
6. Review the collected data for completeness

