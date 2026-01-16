# Databricks API Reference for SAT Enhancements

**Version**: 1.0
**Date**: 2026-01-16
**API Version**: 2.0, 2.1 (Unity Catalog)

---

## Table of Contents

1. [Unity Catalog APIs](#unity-catalog-apis)
2. [AI/ML APIs](#aiml-apis)
3. [Serverless Network APIs](#serverless-network-apis)
4. [Workspace Settings APIs](#workspace-settings-apis)
5. [Apps & Git APIs](#apps--git-apis)
6. [Monitoring APIs](#monitoring-apis)
7. [Authentication](#authentication)
8. [Rate Limits & Pagination](#rate-limits--pagination)
9. [MCP Tool Mapping](#mcp-tool-mapping)

---

## Unity Catalog APIs

### UC Tables API (2.1)

**Base Endpoint**: `/api/2.1/unity-catalog/tables`

#### List All Tables
```http
GET /api/2.1/unity-catalog/tables
```

**Query Parameters**:
- `catalog_name` (optional): Filter by catalog
- `schema_name` (optional): Filter by schema
- `max_results` (optional): Max tables per page (default: 100, max: 1000)
- `page_token` (optional): Pagination token

**Response**:
```json
{
  "tables": [
    {
      "catalog_name": "main",
      "schema_name": "default",
      "name": "customers",
      "full_name": "main.default.customers",
      "table_type": "MANAGED",
      "data_source_format": "DELTA",
      "columns": [...],
      "storage_location": "s3://...",
      "owner": "data_engineers",
      "created_at": 1640000000000,
      "updated_at": 1640000000000,
      "row_filter": {
        "name": "customer_filter",
        "function_name": "filter_by_region"
      },
      "comment": "Customer master data"
    }
  ],
  "next_page_token": "..."
}
```

**MCP Tool**: `mcp__databricks__list_tables`

---

#### Get Table Details
```http
GET /api/2.1/unity-catalog/tables/{full_name}
```

**Path Parameters**:
- `full_name`: Catalog.schema.table (e.g., `main.default.customers`)

**Response**:
```json
{
  "catalog_name": "main",
  "schema_name": "default",
  "name": "customers",
  "table_type": "MANAGED",
  "columns": [
    {
      "name": "customer_id",
      "type_text": "BIGINT",
      "type_name": "LONG",
      "position": 0,
      "comment": "Primary key"
    },
    {
      "name": "ssn",
      "type_text": "STRING",
      "type_name": "STRING",
      "position": 1,
      "mask": {
        "function_name": "mask_ssn",
        "using_column_names": ["ssn"]
      },
      "comment": "Social security number (masked)"
    },
    {
      "name": "email",
      "type_text": "STRING",
      "type_name": "STRING",
      "position": 2,
      "mask": {
        "function_name": "mask_email"
      }
    }
  ],
  "row_filter": {
    "name": "customer_filter",
    "function_name": "main.security.filter_by_region",
    "using_column_names": ["region"]
  },
  "owner": "data_engineers"
}
```

**MCP Tool**: `mcp__databricks__get_table_details`

**Key Fields for Checks**:
- `row_filter`: Row-level security configuration (UC-1)
- `columns[].mask`: Column masking configuration (UC-2)
- `owner`: Ownership (UC-6)
- `table_type`: MANAGED vs EXTERNAL (UC-8)

---

### UC External Locations API

**Base Endpoint**: `/api/2.1/unity-catalog/external-locations`

#### List External Locations
```http
GET /api/2.1/unity-catalog/external-locations
```

**Response**:
```json
{
  "external_locations": [
    {
      "name": "raw-data-s3",
      "url": "s3://mybucket/raw-data/",
      "credential_name": "s3-readonly-cred",
      "credential_id": "cred-abc123",
      "owner": "data_engineers",
      "read_only": true,
      "created_at": 1640000000000,
      "updated_at": 1640000000000,
      "comment": "Raw data landing zone"
    }
  ]
}
```

**MCP Tool**: `mcp__databricks__list_external_locations`

**Key Fields for Checks**:
- `credential_name`: Must not be NULL (UC-4)
- `credential_id`: Reference to storage credential
- `read_only`: Scope restriction (UC-5)

---

### UC Storage Credentials API

**Base Endpoint**: `/api/2.1/unity-catalog/storage-credentials`

#### List Storage Credentials
```http
GET /api/2.1/unity-catalog/storage-credentials
```

**Response**:
```json
{
  "storage_credentials": [
    {
      "name": "s3-readonly-cred",
      "id": "cred-abc123",
      "aws_iam_role": {
        "role_arn": "arn:aws:iam::123456789:role/uc-readonly",
        "external_id": "databricks-uc-123"
      },
      "owner": "account admins",
      "read_only": true,
      "created_at": 1640000000000,
      "comment": "Read-only S3 access"
    }
  ]
}
```

**MCP Tool**: `mcp__databricks__list_storage_credentials`

**Key Fields for Checks**:
- `aws_iam_role.role_arn`: Check IAM policy scope (UC-5)
- `azure_service_principal`: Check RBAC scope (UC-5)
- `gcp_service_account_key`: Check GCS permissions (UC-5)
- `read_only`: Least privilege indicator

---

### UC Volumes API

**Base Endpoint**: `/api/2.1/unity-catalog/volumes`

#### List Volumes
```http
GET /api/2.1/unity-catalog/volumes
?catalog_name=main&schema_name=ml_models
```

**Response**:
```json
{
  "volumes": [
    {
      "catalog_name": "main",
      "schema_name": "ml_models",
      "name": "artifacts",
      "full_name": "main.ml_models.artifacts",
      "volume_type": "MANAGED",
      "storage_location": "/Volumes/main/ml_models/artifacts",
      "owner": "ml_engineers",
      "created_at": 1640000000000,
      "comment": "Model artifacts storage"
    }
  ]
}
```

**MCP Tool**: `mcp__databricks__list_volumes`

**Key Fields for Checks**:
- `volume_type`: MANAGED vs EXTERNAL (UC-8)
- `storage_location`: Path validation
- Need to query permissions separately via `/api/2.0/permissions/volumes/{full_name}`

---

### UC Lineage API

**Base Endpoint**: `/api/2.1/unity-catalog/lineage`

#### Get Table Lineage
```http
GET /api/2.1/unity-catalog/lineage/table/{full_name}
```

**Response**:
```json
{
  "table_info": {
    "catalog_name": "main",
    "schema_name": "analytics",
    "name": "customer_metrics"
  },
  "upstream_tables": [
    {
      "catalog_name": "main",
      "schema_name": "default",
      "name": "customers"
    },
    {
      "catalog_name": "main",
      "schema_name": "transactions",
      "name": "orders"
    }
  ],
  "downstream_tables": [
    {
      "catalog_name": "main",
      "schema_name": "reports",
      "name": "monthly_dashboard"
    }
  ]
}
```

**MCP Tool**: `mcp__databricks__get_table_lineage`

**Key Fields for Checks**:
- `upstream_tables`: Data sources (UC-7)
- `downstream_tables`: Data consumers (UC-7)
- Empty arrays indicate missing lineage

---

### UC ABAC API (Preview - Needs Verification)

**Base Endpoint**: `/api/2.1/unity-catalog/attribute-based-access-control`

**Status**: ⚠️ API endpoint needs verification - may be preview or not yet available

**Expected Endpoint**:
```http
GET /api/2.1/unity-catalog/policies
```

**Expected Response**:
```json
{
  "policies": [
    {
      "policy_id": "policy-123",
      "name": "sensitive-data-policy",
      "tag_key": "sensitivity",
      "tag_values": ["high", "confidential"],
      "principals": ["data_analysts", "data_scientists"],
      "permissions": ["SELECT"],
      "scope": "catalog:main"
    }
  ]
}
```

**Action Required**: Verify API availability in Sprint 1

---

## AI/ML APIs

### Serving Endpoints API (2.0)

**Base Endpoint**: `/api/2.0/serving-endpoints`

#### List Serving Endpoints
```http
GET /api/2.0/serving-endpoints
```

**Response**:
```json
{
  "endpoints": [
    {
      "name": "chatbot-endpoint",
      "id": "ep-abc123",
      "creator": "user@company.com",
      "creation_timestamp": 1640000000000,
      "last_updated_timestamp": 1640000000000,
      "state": {
        "ready": "READY",
        "config_update": "NOT_UPDATING"
      },
      "config": {
        "served_models": [
          {
            "name": "gpt-4",
            "model_name": "gpt-4",
            "model_version": "1",
            "workload_size": "Small",
            "scale_to_zero_enabled": true
          }
        ],
        "traffic_config": {
          "routes": [
            {
              "served_model_name": "gpt-4",
              "traffic_percentage": 100
            }
          ]
        }
      },
      "tags": [
        {"key": "environment", "value": "production"}
      ]
    }
  ]
}
```

**MCP Tool**: `mcp__databricks__list_model_serving_endpoints`

---

#### Get Serving Endpoint Config
```http
GET /api/2.0/serving-endpoints/{name}
```

**Response with AI Gateway Guardrails**:
```json
{
  "name": "chatbot-endpoint",
  "config": {
    "served_models": [...],
    "auto_capture_config": {
      "catalog_name": "main",
      "schema_name": "ai_logs",
      "table_name_prefix": "chatbot",
      "enabled": true
    },
    "route_optimized": true,
    "ai_gateway": {
      "guardrails": {
        "input": {
          "pii": {
            "enabled": true,
            "behavior": "BLOCK",
            "types": ["SSN", "CREDIT_CARD", "EMAIL", "PHONE"]
          },
          "malicious_urls": {
            "enabled": true
          },
          "invalid_keywords": {
            "enabled": true,
            "keywords": ["DROP TABLE", "DELETE FROM"]
          }
        },
        "output": {
          "pii": {
            "enabled": true,
            "behavior": "REDACT",
            "types": ["SSN", "CREDIT_CARD"]
          },
          "safety": {
            "enabled": true,
            "threshold": 0.8,
            "categories": ["HATE", "VIOLENCE", "SEXUAL"]
          },
          "keywords": {
            "enabled": true,
            "keywords": ["confidential", "internal-only"]
          }
        }
      },
      "rate_limits": [
        {
          "key": "user",
          "renewal_period": "minute",
          "calls": 100
        },
        {
          "key": "endpoint",
          "renewal_period": "minute",
          "calls": 1000
        }
      ],
      "usage_tracking": {
        "enabled": true
      }
    }
  },
  "permissions": {
    "can_query": ["users", "data_scientists"],
    "can_manage": ["ml_engineers"]
  }
}
```

**MCP Tool**: `mcp__databricks__get_serving_endpoint_config`

**Key Fields for Checks**:
- `ai_gateway.guardrails.input.pii`: PII input detection (AI-1)
- `ai_gateway.guardrails.output.pii`: PII output redaction (AI-1)
- `ai_gateway.guardrails.output.safety`: Safety filters (AI-1)
- `ai_gateway.rate_limits`: Rate limiting (AI-4)
- `auto_capture_config`: Inference logging (AI-3)
- `permissions`: Authentication (AI-2)

---

### Vector Search API (2.0)

**Base Endpoint**: `/api/2.0/vector-search/endpoints`

#### List Vector Search Endpoints
```http
GET /api/2.0/vector-search/endpoints
```

**Response**:
```json
{
  "endpoints": [
    {
      "name": "rag-vector-search",
      "id": "vs-abc123",
      "endpoint_type": "STANDARD",
      "endpoint_status": {
        "state": "ONLINE"
      },
      "creator": "user@company.com",
      "creation_timestamp": 1640000000000
    }
  ]
}
```

**MCP Tool**: `mcp__databricks__list_vector_search_endpoints`

**Key Fields for Checks**:
- Need to query network security separately
- Check IP access lists or Private Link configuration

---

### MLflow APIs

#### List Experiments
```http
GET /api/2.0/mlflow/experiments/list
```

#### Get Experiment Permissions
```http
GET /api/2.0/permissions/experiments/{experiment_id}
```

**Response**:
```json
{
  "object_id": "experiments/123456",
  "object_type": "mlflow-experiment",
  "access_control_list": [
    {
      "user_name": "user@company.com",
      "all_permissions": [
        {"permission_level": "CAN_MANAGE", "inherited": false}
      ]
    },
    {
      "group_name": "users",
      "all_permissions": [
        {"permission_level": "CAN_READ", "inherited": false}
      ]
    }
  ]
}
```

**MCP Tool**: `mcp__databricks__get_permissions` with `object_type=experiments`

**Key Fields for Checks**:
- Check for "users" or "all" groups with broad permissions (AI-7)

---

## Serverless Network APIs

### Network Policies API (Account-Level)

**Base Endpoint**: `/api/2.0/accounts/{account_id}/network-policies`

**Status**: ⚠️ API not yet available in Databricks MCP tools - needs verification

#### List Network Policies
```http
GET /api/2.0/accounts/{account_id}/network-policies
```

**Expected Response**:
```json
{
  "network_policies": [
    {
      "network_policy_id": "np-abc123",
      "name": "production-egress-policy",
      "creation_time": 1640000000000,
      "update_time": 1640000000000,
      "egress_rules": [
        {
          "rule_id": "rule-001",
          "destination": "s3.amazonaws.com",
          "destination_type": "FQDN",
          "protocol": "HTTPS",
          "port": 443,
          "action": "ALLOW"
        },
        {
          "rule_id": "rule-002",
          "destination": "pypi.org",
          "destination_type": "FQDN",
          "protocol": "HTTPS",
          "port": 443,
          "action": "ALLOW"
        },
        {
          "rule_id": "rule-999",
          "destination": "*",
          "destination_type": "WILDCARD",
          "protocol": "*",
          "port": "*",
          "action": "DENY"
        }
      ],
      "description": "Restrictive egress policy for production"
    }
  ],
  "default_network_policy_id": "np-default"
}
```

**Key Fields for Checks**:
- `default_network_policy_id`: Check if custom policy exists (SLS-1)
- `egress_rules`: Parse for wildcard ALLOW rules (SLS-3)
- `egress_rules[].action`: Should have explicit DENY rule

---

#### List Workspace Network Policy Assignments
```http
GET /api/2.0/accounts/{account_id}/network-policies/workspace-assignments
```

**Expected Response**:
```json
{
  "workspace_assignments": [
    {
      "workspace_id": "123456789",
      "network_policy_id": "np-abc123",
      "assignment_time": 1640000000000
    }
  ]
}
```

**Key Fields for Checks**:
- Join with workspaces to find production workspaces without assignments (SLS-2)

**Action Required**: Verify API availability in Sprint 3 week 1

---

## Workspace Settings APIs

### Settings v2 API

**Base Endpoint**: `/api/2.0/settings`

#### List Available Settings
```http
GET /api/2.0/settings/types
```

**Response**:
```json
{
  "settings": [
    "compliance_security_profile",
    "esm_enablement_workspace",
    "automatic_cluster_update",
    "restrict_workspace_admins",
    "personal_compute",
    ...
  ]
}
```

**MCP Tool**: `mcp__databricks__list_settings_metadata`

---

#### Get Specific Setting
```http
GET /api/2.0/settings/types/{setting_name}/names/default
```

**Example: Compliance Security Profile**:
```http
GET /api/2.0/settings/types/compliance_security_profile/names/default
```

**Response**:
```json
{
  "setting_name": "compliance_security_profile",
  "etag": "...",
  "setting_value": {
    "enableComplianceSecurityProfile": true,
    "complianceStandards": ["HIPAA", "PCI-DSS"],
    "enforcementLevel": "strict"
  }
}
```

**MCP Tool**: `mcp__databricks__get_setting`

---

#### Get Enhanced Security Monitoring
```http
GET /api/2.0/settings/types/esm_enablement_workspace/names/default
```

**Response**:
```json
{
  "setting_name": "esm_enablement_workspace",
  "setting_value": {
    "enableEnhancedSecurityMonitoring": true,
    "enableExNetworkLogging": true,
    "features": ["network_logging", "anomaly_detection"]
  }
}
```

**Key Fields for Checks**:
- `complianceStandards`: Which standards enabled (Modify-4)
- `enforcementLevel`: Enforcement strictness
- `features`: ESM feature set

---

### Workspace-Conf API (Legacy)

**Base Endpoint**: `/api/2.0/workspace-conf`

**Note**: Legacy API, prefer Settings v2 when available

#### Get Git URL Allowlist
```http
GET /api/2.0/workspace-conf
?keys=enableGitUrlAllowlist,projectsAllowList
```

**Response**:
```json
{
  "enableGitUrlAllowlist": "true",
  "projectsAllowList": "github.com/company-org,gitlab.company.com"
}
```

**MCP Tool**: `mcp__databricks__get_workspace_config`

**Key Fields for Checks**:
- `enableGitUrlAllowlist`: Must be "true" (GIT-1)
- `projectsAllowList`: CSV of allowed URLs (GIT-1)

---

## Apps & Git APIs

### Databricks Apps API (2.0)

**Base Endpoint**: `/api/2.0/apps`

#### List Apps
```http
GET /api/2.0/apps
```

**Response**:
```json
{
  "apps": [
    {
      "name": "customer-analytics",
      "id": "app-abc123",
      "status": "RUNNING",
      "service_principal_id": "sp-xyz789",
      "service_principal_name": "customer-analytics-sp",
      "created_by": "user@company.com",
      "created_at": 1640000000000,
      "updated_at": 1640000000000
    }
  ]
}
```

**MCP Tool**: `mcp__databricks__list_apps` (if available)

**Key Fields for Checks**:
- `service_principal_id`: Must not be NULL (APP-1)
- Need to query permissions separately

---

#### Get App Permissions
```http
GET /api/2.0/apps/{name}/permissions
```

**Response**:
```json
{
  "object_id": "apps/customer-analytics",
  "object_type": "app",
  "access_control_list": [
    {
      "service_principal_name": "customer-analytics-sp",
      "all_permissions": [
        {"permission_level": "CAN_MANAGE"}
      ]
    },
    {
      "group_name": "business_analysts",
      "all_permissions": [
        {"permission_level": "CAN_USE"}
      ]
    }
  ]
}
```

**Key Fields for Checks**:
- Check for "anonymous" or "users" group (APP-3)
- Validate permission levels (APP-4)

---

### Git Repos API

**Base Endpoint**: `/api/2.0/repos`

#### List Repos
```http
GET /api/2.0/repos
```

**Response**:
```json
{
  "repos": [
    {
      "id": 123456,
      "path": "/Repos/user@company.com/project",
      "url": "https://github.com/company/project.git",
      "provider": "gitHub",
      "head_commit_id": "abc123...",
      "credential_id": "cred-xyz789"
    },
    {
      "id": 123457,
      "path": "/Repos/user@company.com/bitbucket-project",
      "url": "https://bitbucket.org/company/project.git",
      "provider": "bitbucketCloud",
      "credential_id": "cred-bitbucket-789"
    }
  ]
}
```

**MCP Tool**: `mcp__databricks__list_repos`

**Key Fields for Checks**:
- `provider`: Filter for "bitbucket*" (GIT-3)
- `credential_id`: Reference to credential (check type separately)

**Note**: Need additional API to query credential type (app password vs token)

---

## Monitoring APIs

### Notification Destinations API

**Base Endpoint**: `/api/2.0/notification-destinations`

#### List Notification Destinations
```http
GET /api/2.0/notification-destinations
```

**Response**:
```json
{
  "notification_destinations": [
    {
      "id": "nd-abc123",
      "display_name": "Security Team Email",
      "config": {
        "type": "email",
        "addresses": ["security@company.com"]
      }
    },
    {
      "id": "nd-xyz789",
      "display_name": "Slack Security Channel",
      "config": {
        "type": "slack",
        "url": "https://hooks.slack.com/..."
      }
    }
  ]
}
```

**MCP Tool**: `mcp__databricks__list_notification_destinations` (if available)

**Key Fields for Checks**:
- Check if security-related destinations exist (SYS-3)
- `config.type`: Email, Slack, PagerDuty, webhook

---

### System Tables

**Unity Catalog Schema**: `system.access`

#### Query Audit Logs
```sql
SELECT
  event_time,
  user_identity.email,
  action_name,
  request_params,
  response
FROM system.access.audit
WHERE event_date >= current_date() - 7
  AND action_name IN ('createToken', 'deleteToken', 'updatePermissions')
ORDER BY event_time DESC
LIMIT 1000
```

**MCP Tool**: `mcp__databricks__query_audit_logs`

**Key Fields**:
- `event_time`: Timestamp of event
- `user_identity`: Who performed action
- `action_name`: What action was performed
- `request_params`: Action details

---

## Authentication

### Service Principal OAuth (AWS/GCP)

**Token Endpoint**: `https://accounts.cloud.databricks.com/oidc/v1/token`

**Request**:
```http
POST /oidc/v1/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&client_id=<service_principal_id>
&client_secret=<service_principal_secret>
&scope=all-apis
```

**Response**:
```json
{
  "access_token": "eyJhbGc...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

**Usage**:
```http
GET /api/2.0/clusters/list
Authorization: Bearer eyJhbGc...
```

---

### Azure MSAL Authentication

**Token Endpoints**:
1. **Databricks Accounts API**: `https://accounts.azuredatabricks.net/oidc/v1/token`
2. **Azure Management API**: `https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token`

**Databricks Token Request**:
```http
POST /oidc/v1/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&client_id=<application_id>
&client_secret=<application_secret>
&scope=2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default
```

**Azure Management Token Request**:
```http
POST /oauth2/v2.0/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&client_id=<application_id>
&client_secret=<application_secret>
&scope=https://management.azure.com/.default
```

---

## Rate Limits & Pagination

### Rate Limits

**Databricks API Rate Limits**:
- **Workspace APIs**: 30 requests/second (burst: 60)
- **Account APIs**: 10 requests/second (burst: 20)
- **Unity Catalog APIs**: 100 requests/second (burst: 200)

**Headers**:
- `X-RateLimit-Limit`: Max requests per window
- `X-RateLimit-Remaining`: Remaining requests
- `X-RateLimit-Reset`: Unix timestamp when limit resets

**Retry Logic**:
- HTTP 429: Too Many Requests
- Wait `Retry-After` seconds (or exponential backoff)
- Max retries: 3

---

### Pagination

**Standard Pagination**:
```http
GET /api/2.1/unity-catalog/tables
?max_results=100
&page_token=<token_from_previous_response>
```

**Response**:
```json
{
  "tables": [...],
  "next_page_token": "eyJvZmZzZXQ..."
}
```

**Iteration Pattern**:
```python
def get_all_tables():
    tables = []
    params = {"max_results": 100}

    while True:
        response = client.get("/api/2.1/unity-catalog/tables", params=params)
        tables.extend(response.get('tables', []))

        if 'next_page_token' not in response:
            break

        params['page_token'] = response['next_page_token']

    return tables
```

---

## MCP Tool Mapping

### Unity Catalog

| API Endpoint | MCP Tool | Status |
|--------------|----------|--------|
| `/api/2.1/unity-catalog/tables` | `mcp__databricks__list_tables` | ✅ Available |
| `/api/2.1/unity-catalog/tables/{name}` | `mcp__databricks__get_table_details` | ✅ Available |
| `/api/2.1/unity-catalog/external-locations` | `mcp__databricks__list_external_locations` | ✅ Available |
| `/api/2.1/unity-catalog/storage-credentials` | `mcp__databricks__list_storage_credentials` | ✅ Available |
| `/api/2.1/unity-catalog/volumes` | `mcp__databricks__list_volumes` | ✅ Available |
| `/api/2.1/unity-catalog/lineage/table/{name}` | `mcp__databricks__get_table_lineage` | ✅ Available |
| `/api/2.1/unity-catalog/policies` | N/A | ❓ Needs verification |

### AI/ML

| API Endpoint | MCP Tool | Status |
|--------------|----------|--------|
| `/api/2.0/serving-endpoints` | `mcp__databricks__list_model_serving_endpoints` | ✅ Available |
| `/api/2.0/serving-endpoints/{name}` | `mcp__databricks__get_serving_endpoint_config` | ✅ Available |
| `/api/2.0/vector-search/endpoints` | `mcp__databricks__list_vector_search_endpoints` | ✅ Available |
| `/api/2.0/mlflow/experiments/list` | `mcp__databricks__list_experiments` | ✅ Available |
| `/api/2.0/permissions/experiments/{id}` | `mcp__databricks__get_permissions` | ✅ Available |

### Serverless Network

| API Endpoint | MCP Tool | Status |
|--------------|----------|--------|
| `/api/2.0/accounts/{id}/network-policies` | N/A | ❓ Needs verification |
| `/api/2.0/network-policies/workspace-assignments` | N/A | ❓ Needs verification |

### Settings

| API Endpoint | MCP Tool | Status |
|--------------|----------|--------|
| `/api/2.0/settings/types` | `mcp__databricks__list_settings_metadata` | ✅ Available |
| `/api/2.0/settings/types/{name}/names/default` | `mcp__databricks__get_setting` | ✅ Available |
| `/api/2.0/workspace-conf` | `mcp__databricks__get_workspace_config` | ✅ Available |

### Apps & Git

| API Endpoint | MCP Tool | Status |
|--------------|----------|--------|
| `/api/2.0/apps` | N/A | ⚠️ May need custom implementation |
| `/api/2.0/apps/{name}/permissions` | `mcp__databricks__get_permissions` | ✅ Available (generic) |
| `/api/2.0/repos` | `mcp__databricks__list_repos` | ✅ Available |

### Monitoring

| API Endpoint | MCP Tool | Status |
|--------------|----------|--------|
| `/api/2.0/notification-destinations` | N/A | ⚠️ May need custom implementation |
| `system.access.audit` (SQL) | `mcp__databricks__query_audit_logs` | ✅ Available |

---

## API Availability Summary

### ✅ Confirmed Available (Ready to Use)

- Unity Catalog tables, external locations, storage credentials, volumes, lineage
- Model serving endpoints, vector search
- MLflow experiments, models
- Settings v2 API
- Git repos
- Permissions API (generic)
- System tables (SQL queries)

### ❓ Needs Verification

- **Network policies API** (SLS-1, SLS-2, SLS-3, SLS-4)
  - Action: Research in Sprint 1 week 1
  - Fallback: Defer to later sprint if preview

- **ABAC policies API** (UC-3)
  - Action: Research in Sprint 1 week 1
  - Fallback: Mark as preview feature

- **Apps API** (APP-1, APP-2, APP-3, APP-4)
  - Action: Test MCP tool availability
  - Fallback: Custom client implementation

- **Notification destinations API** (SYS-3)
  - Action: Test MCP tool availability
  - Fallback: Custom client implementation

---

## Next Steps

### Sprint 1 Week 1 Research

1. ✅ **Verify Network Policies API**
   - Test API endpoint on account
   - Document response format
   - Create MCP tool mapping or custom implementation

2. ✅ **Verify ABAC API**
   - Search Databricks documentation
   - Test preview API if available
   - Document alternative approaches (tags API)

3. ✅ **Test Apps & Notification APIs**
   - Validate MCP tool coverage
   - Test API responses
   - Document any custom implementation needs

---

**End of API Reference**
