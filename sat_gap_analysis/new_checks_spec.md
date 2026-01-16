# New Security Checks Specifications

**Version**: 1.0
**Date**: 2026-01-16
**Total New Checks**: 35

---

## Table of Contents

1. [Unity Catalog Fine-Grained Security (8 checks)](#unity-catalog-fine-grained-security)
2. [AI/ML Security (7 checks)](#aiml-security)
3. [Serverless Network Security (4 checks)](#serverless-network-security)
4. [Git Security (3 checks)](#git-security)
5. [Databricks Apps Security (4 checks)](#databricks-apps-security)
6. [Secrets Management (3 checks)](#secrets-management)
7. [System Tables & Monitoring (3 checks)](#system-tables--monitoring)
8. [Additional Enhancements (3 checks)](#additional-enhancements)

---

## Unity Catalog Fine-Grained Security

### UC-1: Row-Level Security Filters Applied

**Check ID**: 111
**Category**: Data Protection (DP-10)
**Severity**: High
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Description
Validates that sensitive tables in Unity Catalog have row-level security (RLS) filters configured to restrict data access based on user attributes.

#### Business Justification
Row-level security is critical for:
- HIPAA compliance (patient data filtered by provider)
- GDPR compliance (customer data filtered by region)
- Multi-tenant applications (tenant ID filtering)
- Classified data (security clearance level filtering)

#### Technical Specification

**API Endpoint**: `/api/2.1/unity-catalog/tables/{full_name}`

**API Request Example**:
```bash
curl -n GET "https://<workspace>/api/2.1/unity-catalog/tables/main.finance.transactions"
```

**API Response Fields**:
```json
{
  "catalog_name": "main",
  "schema_name": "finance",
  "name": "transactions",
  "table_type": "MANAGED",
  "row_filter": {
    "name": "tenant_filter",
    "function_name": "filter_by_tenant"
  }
}
```

**Rule Logic**:
- Query all tables in Unity Catalog
- Filter for tables marked as sensitive (naming convention or tags)
- Check if `row_filter` field is NULL
- Return list of sensitive tables without row filters

**SQL Query Pattern**:
```sql
SELECT
    catalog_name,
    schema_name,
    name,
    table_type,
    comment
FROM uc_tables_{workspace_id}
WHERE row_filter IS NULL
  AND table_type IN ('MANAGED', 'EXTERNAL')
  AND (
    comment LIKE '%sensitive%' OR
    comment LIKE '%pii%' OR
    name LIKE '%customer%' OR
    name LIKE '%patient%' OR
    name LIKE '%transaction%'
  )
```

**Rule Function**:
```python
def uc_row_filter_rule(df):
    if df is None or isEmpty(df):
        return (check_id, 0, {})  # Pass: All sensitive tables have filters
    else:
        tables_without_filters = df.collect()
        table_list = [
            [t.catalog_name, t.schema_name, t.name]
            for t in tables_without_filters
        ]
        return (check_id, len(table_list), {
            'tables_without_row_filters': table_list,
            'count': len(table_list)
        })
```

**Client Method**:
```python
# File: src/securityanalysistoolproject/clientpkgs/unity_catalog_client.py

def get_table_details_with_filters(self, full_name):
    """Get table details including row filters and column masks"""
    endpoint = f"/api/2.1/unity-catalog/tables/{full_name}"
    return self.get(endpoint)

def get_all_tables_with_filters(self):
    """Get all tables with their row filter configurations"""
    endpoint = "/api/2.1/unity-catalog/tables"
    tables = []
    params = {"max_results": 100}

    while True:
        response = self.get(endpoint, params=params)
        tables.extend(response.get('tables', []))

        if 'next_page_token' not in response:
            break
        params['page_token'] = response['next_page_token']

    return tables
```

**Bootstrap Integration**:
```python
# File: notebooks/Utils/accounts_bootstrap.py

def bootstrap_uc_tables(acct_client, workspace_id):
    """Bootstrap UC tables with row filter information"""
    viewname = f"uc_tables_{workspace_id}"
    func = acct_client.get_all_tables_with_filters
    bootstrap(viewname, func)
```

**Recommendation**:
```
Configure row-level security filters on sensitive tables to restrict data access:
1. Identify tables containing PII or sensitive data
2. Create row filter functions in Unity Catalog
3. Apply filters using: ALTER TABLE <table> SET ROW FILTER <function>
4. Test filter with different user contexts

Example:
CREATE FUNCTION main.security.filter_by_department(dept STRING)
  RETURN dept = current_user_department();

ALTER TABLE main.hr.employees
  SET ROW FILTER main.security.filter_by_department ON (department);
```

**Implementation Complexity**: Medium
**Estimated Effort**: 3 days
**Dependencies**: Unity Catalog enabled, table metadata collection

---

### UC-2: Column Masking Policies Configured

**Check ID**: 112
**Category**: Data Protection (DP-11)
**Severity**: High
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Description
Validates that columns containing PII or sensitive data have masking functions applied to prevent unauthorized data exposure.

#### Business Justification
Column masking is essential for:
- PII protection (SSN, credit cards, email addresses)
- GDPR "right to pseudonymization"
- PCI-DSS requirement 3.4 (render PAN unreadable)
- Test/dev data security (mask production data copies)

#### Technical Specification

**API Endpoint**: `/api/2.1/unity-catalog/tables/{full_name}`

**API Response Fields**:
```json
{
  "columns": [
    {
      "name": "ssn",
      "type_text": "STRING",
      "mask": {
        "function_name": "mask_ssn"
      }
    },
    {
      "name": "credit_card",
      "type_text": "STRING",
      "mask": {
        "function_name": "mask_credit_card"
      }
    }
  ]
}
```

**Rule Logic**:
- Query all tables in Unity Catalog
- Extract columns with names suggesting PII (ssn, email, phone, credit_card, etc.)
- Check if `mask` property is NULL for these columns
- Return list of unmasked PII columns

**SQL Query Pattern**:
```sql
SELECT
    catalog_name,
    schema_name,
    table_name,
    column_name,
    column_type
FROM uc_table_columns_{workspace_id}
WHERE mask IS NULL
  AND (
    column_name LIKE '%ssn%' OR
    column_name LIKE '%email%' OR
    column_name LIKE '%phone%' OR
    column_name LIKE '%credit%card%' OR
    column_name LIKE '%address%' OR
    column_name LIKE '%dob%' OR
    column_name LIKE '%birth%date%'
  )
```

**Recommendation**:
```
Apply column masking functions to PII columns:
1. Create masking functions for different data types
2. Apply masks using: ALTER TABLE <table> ALTER COLUMN <col> SET MASK <function>
3. Grant UNMASK permission to authorized users only

Example masking functions:
- Email: CONCAT(LEFT(email, 3), '***@', SPLIT(email, '@')[1])
- SSN: CONCAT('XXX-XX-', RIGHT(ssn, 4))
- Credit Card: CONCAT('XXXX-XXXX-XXXX-', RIGHT(cc, 4))
```

**Implementation Complexity**: Medium
**Estimated Effort**: 3 days

---

### UC-3: ABAC Policies Deployed

**Check ID**: 113
**Category**: Governance (GOV-37)
**Severity**: Medium
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Description
Validates that Attribute-Based Access Control (ABAC) policies using tags are configured for dynamic access control.

#### Business Justification
ABAC provides:
- Dynamic access control based on user/resource attributes
- Simplified permission management (tag-based, not individual grants)
- Compliance with zero-trust security models
- Scalable governance for large organizations

#### Technical Specification

**API Endpoint**: `/api/2.1/unity-catalog/attribute-based-access-control`

**API Response Fields**:
```json
{
  "policies": [
    {
      "name": "sensitive_data_policy",
      "tag_key": "sensitivity",
      "tag_value": "high",
      "permissions": ["SELECT"],
      "principals": ["data_analysts"]
    }
  ]
}
```

**Rule Logic**:
- Query ABAC policies configured in Unity Catalog
- Check if any policies exist
- Return count of policies and coverage

**Recommendation**:
```
Configure ABAC policies for tag-based access control:
1. Define tag taxonomy (e.g., sensitivity: low/medium/high)
2. Apply tags to catalogs, schemas, tables
3. Create ABAC policies linking tags to permissions
4. Monitor policy effectiveness via audit logs
```

**Implementation Complexity**: High (API may be preview)
**Estimated Effort**: 5 days
**Note**: API endpoint needs verification - may be part of UC governance API

---

### UC-4: External Location Security

**Check ID**: 114
**Category**: Data Protection (DP-12)
**Severity**: High
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Description
Validates that external locations use storage credentials instead of direct access, ensuring proper IAM control.

#### Technical Specification

**API Endpoint**: `/api/2.1/unity-catalog/external-locations`

**Rule Logic**:
- Query all external locations
- Check if `credential_name` is NULL
- Flag locations with direct access

**SQL Query Pattern**:
```sql
SELECT
    name,
    url,
    credential_name,
    owner
FROM uc_external_locations_{workspace_id}
WHERE credential_name IS NULL
```

**Recommendation**:
```
Configure storage credentials for external locations:
1. Create storage credential with least-privilege IAM role/principal
2. Associate credential with external location
3. Remove direct access grants

AWS Example:
CREATE STORAGE CREDENTIAL s3_readonly
  WITH (AWS_IAM_ROLE = 'arn:aws:iam::123456:role/uc-readonly');

CREATE EXTERNAL LOCATION my_bucket
  URL 's3://my-bucket/data'
  WITH (STORAGE CREDENTIAL s3_readonly);
```

**Implementation Complexity**: Low
**Estimated Effort**: 2 days

---

### UC-5: Storage Credential Scope

**Check ID**: 115
**Category**: Data Protection (DP-13)
**Severity**: Medium
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Description
Validates that storage credentials are scoped to specific paths or buckets, not root-level access.

#### Technical Specification

**API Endpoint**: `/api/2.1/unity-catalog/storage-credentials`

**Rule Logic**:
- Query all storage credentials
- Check IAM policy scope (AWS), service principal permissions (Azure), or service account roles (GCP)
- Flag credentials with wildcard (*) or root-level access

**Recommendation**:
```
Scope storage credentials to specific paths:
- AWS: IAM role with Resource scoped to "arn:aws:s3:::bucket/prefix/*"
- Azure: Service principal with role assignment on container, not storage account
- GCP: Service account with bucket-level permissions, not project-level
```

**Implementation Complexity**: Medium (requires IAM policy parsing)
**Estimated Effort**: 4 days

---

### UC-6: Catalog/Schema Ownership Delegation

**Check ID**: 116
**Category**: Governance (GOV-38)
**Severity**: Low
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Description
Validates that catalogs and schemas are owned by groups or service principals, not individual users.

#### Technical Specification

**API Endpoint**:
- `/api/2.1/unity-catalog/catalogs`
- `/api/2.1/unity-catalog/schemas`

**Rule Logic**:
- Query all catalogs and schemas
- Check if `owner` field contains email address (user) vs group name or SP
- Flag individual user ownership

**SQL Query Pattern**:
```sql
SELECT
    name,
    owner,
    created_by
FROM uc_catalogs_{workspace_id}
WHERE owner LIKE '%@%'  -- Email address indicates user ownership

UNION ALL

SELECT
    CONCAT(catalog_name, '.', name) as name,
    owner,
    created_by
FROM uc_schemas_{workspace_id}
WHERE owner LIKE '%@%'
```

**Recommendation**:
```
Transfer ownership to groups or service principals:
1. Create data governance groups (e.g., data_stewards, catalog_admins)
2. Transfer ownership: ALTER CATALOG <catalog> SET OWNER TO `data_stewards`
3. Document ownership responsibilities

Benefits:
- Continuity when individuals leave organization
- Shared responsibility model
- Easier permission auditing
```

**Implementation Complexity**: Low
**Estimated Effort**: 2 days

---

### UC-7: Table/View Lineage Tracking

**Check ID**: 117
**Category**: Governance (GOV-39)
**Severity**: Informational
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Description
Validates that production tables have lineage information captured for impact analysis and compliance.

#### Technical Specification

**API Endpoint**: `/api/2.1/unity-catalog/lineage`

**Rule Logic**:
- Query lineage data for production tables
- Check if lineage information exists (upstream/downstream dependencies)
- Flag tables without lineage data

**Recommendation**:
```
Enable and validate lineage tracking:
1. Lineage is automatically captured for SQL operations
2. For external ETL tools, use Lineage API to register dependencies
3. Use lineage for impact analysis before schema changes
4. Document data flow for compliance (GDPR Article 30)
```

**Implementation Complexity**: Low
**Estimated Effort**: 2 days

---

### UC-8: Volume Security Configuration

**Check ID**: 118
**Category**: Data Protection (DP-15)
**Severity**: Medium
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Description
Validates that Unity Catalog volumes have proper access controls and are not world-readable.

#### Technical Specification

**API Endpoint**: `/api/2.1/unity-catalog/volumes`

**Rule Logic**:
- Query all volumes
- Check volume type (MANAGED vs EXTERNAL)
- For EXTERNAL volumes, validate storage credential is configured
- Query permissions to ensure not world-readable

**SQL Query Pattern**:
```sql
SELECT
    v.catalog_name,
    v.schema_name,
    v.name,
    v.volume_type,
    v.storage_location,
    p.principal,
    p.privileges
FROM uc_volumes_{workspace_id} v
LEFT JOIN uc_volume_permissions_{workspace_id} p
  ON v.full_name = p.volume_name
WHERE p.principal = 'account users'  -- World-readable
   OR (v.volume_type = 'EXTERNAL' AND v.credential_name IS NULL)
```

**Recommendation**:
```
Secure Unity Catalog volumes:
1. Use MANAGED volumes for structured file storage
2. For EXTERNAL volumes, always use storage credentials
3. Grant permissions explicitly, never to "account users"
4. Regularly audit volume permissions

Example:
CREATE VOLUME main.ml_models.artifacts
  COMMENT 'Model artifacts for production';

GRANT READ FILES ON VOLUME main.ml_models.artifacts TO `ml_engineers`;
```

**Implementation Complexity**: Medium
**Estimated Effort**: 3 days

---

## AI/ML Security

### AI-1: Model Serving Guardrails Configured

**Check ID**: 119
**Category**: Data Protection (DP-16)
**Severity**: High
**Cloud Support**: AWS ✓, Azure ✓, GCP ✗ (AI Gateway not available in GCP)

#### Description
Validates that model serving endpoints have AI Gateway guardrails configured to prevent unsafe outputs, PII leakage, and policy violations.

#### Business Justification
AI Gateway guardrails protect against:
- PII leakage in model responses
- Toxic/harmful content generation
- Prompt injection attacks
- Regulatory violations (AI Act, GDPR)
- Brand reputation damage

#### Technical Specification

**API Endpoint**: `/api/2.0/serving-endpoints/{name}`

**API Response Fields**:
```json
{
  "name": "chatbot-endpoint",
  "config": {
    "served_models": [{
      "model_name": "gpt-4",
      "model_version": "1"
    }],
    "auto_capture_config": {
      "catalog_name": "main",
      "schema_name": "ai_logs",
      "table_name_prefix": "chatbot"
    },
    "route_optimized": true,
    "ai_gateway": {
      "guardrails": {
        "input": {
          "pii": {
            "enabled": true,
            "behavior": "BLOCK"
          },
          "malicious_urls": true
        },
        "output": {
          "pii": {
            "enabled": true,
            "behavior": "REDACT"
          },
          "safety": {
            "enabled": true,
            "threshold": 0.8
          },
          "keywords": ["confidential", "internal-only"]
        }
      },
      "rate_limits": [{
        "key": "user",
        "renewal_period": "minute",
        "calls": 100
      }]
    }
  }
}
```

**Rule Logic**:
- Query all serving endpoints
- Check if `ai_gateway.guardrails` configuration exists
- Flag endpoints without PII, safety, or keyword filters
- Categorize by endpoint criticality (public-facing vs internal)

**SQL Query Pattern**:
```sql
SELECT
    name,
    model_name,
    guardrails_enabled,
    pii_filter_enabled,
    safety_filter_enabled,
    endpoint_type
FROM serving_endpoints_{workspace_id}
WHERE guardrails_enabled = false
   OR pii_filter_enabled = false
   OR safety_filter_enabled = false
```

**Rule Function**:
```python
def ai_guardrails_rule(df):
    if df is None or isEmpty(df):
        return (check_id, 0, {})  # Pass: All endpoints have guardrails
    else:
        endpoints_without_guardrails = df.collect()
        endpoint_list = [
            [e.name, e.model_name, e.endpoint_type]
            for e in endpoints_without_guardrails
        ]
        return (check_id, len(endpoint_list), {
            'endpoints_without_guardrails': endpoint_list,
            'count': len(endpoint_list)
        })
```

**Client Method**:
```python
# File: src/securityanalysistoolproject/clientpkgs/serving_endpoints.py

def get_endpoint_guardrails(self, endpoint_name):
    """Get AI Gateway guardrails configuration for a serving endpoint"""
    endpoint = f"/api/2.0/serving-endpoints/{endpoint_name}"
    response = self.get(endpoint)

    config = response.get('config', {})
    ai_gateway = config.get('ai_gateway', {})
    guardrails = ai_gateway.get('guardrails', {})

    return {
        'name': endpoint_name,
        'guardrails_enabled': len(guardrails) > 0,
        'input_pii': guardrails.get('input', {}).get('pii', {}).get('enabled', False),
        'output_pii': guardrails.get('output', {}).get('pii', {}).get('enabled', False),
        'output_safety': guardrails.get('output', {}).get('safety', {}).get('enabled', False),
        'keywords': guardrails.get('output', {}).get('keywords', [])
    }

def list_endpoints_with_guardrails(self):
    """List all serving endpoints with their guardrail configurations"""
    endpoint = "/api/2.0/serving-endpoints"
    response = self.get(endpoint)

    endpoints = []
    for ep in response.get('endpoints', []):
        ep_name = ep.get('name')
        guardrails_info = self.get_endpoint_guardrails(ep_name)
        endpoints.append(guardrails_info)

    return endpoints
```

**Bootstrap Integration**:
```python
# File: notebooks/Utils/workspace_bootstrap.py

def bootstrap_serving_endpoints(ws_client, workspace_id):
    """Bootstrap serving endpoints with guardrail information"""
    viewname = f"serving_endpoints_{workspace_id}"
    func = ws_client.list_endpoints_with_guardrails
    bootstrap(viewname, func)
```

**Recommendation**:
```
Configure AI Gateway guardrails for model serving endpoints:

1. Enable PII Detection:
   - Input: Block requests containing SSN, credit cards, phone numbers
   - Output: Redact PII in model responses

2. Enable Safety Filters:
   - Block toxic, hateful, violent content
   - Set threshold based on risk tolerance (0.6-0.9)

3. Configure Keyword Filters:
   - Block prompts containing "confidential", "internal-only"
   - Prevent data exfiltration attempts

4. Enable Rate Limits:
   - Per-user: 100 requests/minute
   - Per-endpoint: 1000 requests/minute

Example Configuration:
{
  "ai_gateway": {
    "guardrails": {
      "input": {
        "pii": {"enabled": true, "behavior": "BLOCK"},
        "malicious_urls": true
      },
      "output": {
        "pii": {"enabled": true, "behavior": "REDACT"},
        "safety": {"enabled": true, "threshold": 0.8},
        "keywords": ["confidential", "internal-only"]
      }
    }
  }
}

Documentation: https://docs.databricks.com/aws/en/ai-gateway/
```

**Implementation Complexity**: Medium
**Estimated Effort**: 4 days
**Dependencies**: AI Gateway feature (GA Q4 2024), serving endpoints deployed

---

### AI-2: Model Serving Authentication

**Check ID**: 120
**Category**: Identity & Access (IA-8)
**Severity**: High
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Description
Validates that model serving endpoints require authentication and are not publicly accessible.

#### Technical Specification

**API Endpoint**: `/api/2.0/serving-endpoints/{name}`

**Rule Logic**:
- Query all serving endpoints
- Check `config.served_models[].workload_type` for public exposure
- Query permissions via `/api/2.0/permissions/serving-endpoints/{id}`
- Flag endpoints with "anonymous" or "all users" permissions

**Recommendation**:
```
Secure model serving endpoints:
1. Require authentication for all endpoints
2. Use service principal tokens for API access
3. Grant CAN_QUERY permission explicitly
4. Enable IP access lists for additional security
5. Use Private Link for sensitive models
```

**Implementation Complexity**: Low
**Estimated Effort**: 2 days

---

### AI-3: Inference Table Logging Enabled

**Check ID**: 121
**Category**: Governance (GOV-40)
**Severity**: Medium
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Description
Validates that model serving endpoints log requests and responses to inference tables for audit and monitoring.

#### Technical Specification

**API Endpoint**: `/api/2.0/serving-endpoints/{name}/config`

**Rule Logic**:
- Query all serving endpoints
- Check if `auto_capture_config.table_name_prefix` is configured
- Flag endpoints without inference logging

**SQL Query Pattern**:
```sql
SELECT
    name,
    model_name,
    inference_logging_enabled,
    inference_table_name
FROM serving_endpoints_{workspace_id}
WHERE inference_logging_enabled = false
   OR inference_table_name IS NULL
```

**Recommendation**:
```
Enable inference table logging:
1. Configure auto_capture_config when creating endpoint
2. Specify catalog, schema, and table prefix
3. Grant SELECT permission to security team for audit
4. Set up alerts for anomalous patterns

Example:
{
  "auto_capture_config": {
    "catalog_name": "main",
    "schema_name": "ai_logs",
    "table_name_prefix": "chatbot",
    "enabled": true
  }
}

Logged data includes:
- Request timestamp, user, input tokens
- Model response, output tokens
- Latency, cost
- Guardrail actions (PII redacted, safety blocked)
```

**Implementation Complexity**: Low
**Estimated Effort**: 2 days

---

### AI-4: Foundation Model API Rate Limits

**Check ID**: 122
**Category**: Governance (GOV-41)
**Severity**: Medium
**Cloud Support**: AWS ✓, Azure ✓, GCP ✗

#### Description
Validates that rate limits are configured for external LLM providers to prevent cost overruns and abuse.

#### Technical Specification

**API Endpoint**: `/api/2.0/serving-endpoints` (filter for external models)

**Rule Logic**:
- Query serving endpoints with external models (OpenAI, Anthropic, etc.)
- Check if `ai_gateway.rate_limits` is configured
- Flag endpoints without rate limits

**Recommendation**:
```
Configure rate limits for foundation model APIs:
1. Per-user limits: Prevent individual abuse (e.g., 100 req/min)
2. Per-endpoint limits: Protect budget (e.g., 1000 req/min)
3. Token-based limits: Control costs (e.g., 1M tokens/day)
4. Alert on threshold approach (80% of limit)

Example:
{
  "ai_gateway": {
    "rate_limits": [
      {"key": "user", "renewal_period": "minute", "calls": 100},
      {"key": "endpoint", "renewal_period": "minute", "calls": 1000}
    ]
  }
}
```

**Implementation Complexity**: Low
**Estimated Effort**: 2 days

---

### AI-5: Vector Search Endpoint Security

**Check ID**: 123
**Category**: Network Security (NS-9)
**Severity**: High
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Description
Validates that vector search endpoints are secured with IP access lists or Private Link.

#### Technical Specification

**API Endpoint**: `/api/2.0/vector-search/endpoints`

**Rule Logic**:
- Query all vector search endpoints
- Check if IP access list is associated or Private Link enabled
- Flag publicly accessible endpoints

**Recommendation**:
```
Secure vector search endpoints:
1. Associate IP access list with allowed corporate networks
2. Enable Private Link for production endpoints
3. Require authentication via service principals
4. Monitor access via audit logs
```

**Implementation Complexity**: Low
**Estimated Effort**: 2 days

---

### AI-6: Model Registry UC Migration

**Check ID**: 124
**Category**: Governance (GOV-42)
**Severity**: Medium
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Description
Validates that production models are registered in Unity Catalog Models, not the legacy workspace-level MLflow model registry.

#### Technical Specification

**API Endpoints**:
- `/api/2.1/unity-catalog/models` (UC models)
- `/api/2.0/mlflow/registered-models` (workspace models)

**Rule Logic**:
- Query both UC and workspace model registries
- Flag production models still in workspace registry
- Recommend migration path

**Recommendation**:
```
Migrate models to Unity Catalog:
1. Benefits: Cross-workspace sharing, fine-grained permissions, lineage
2. Migration: Use MLflow API to re-register models in UC
3. Update serving endpoints to reference UC models
4. Retire workspace-level models

Migration command:
mlflow.register_model(
    model_uri="runs:/<run_id>/model",
    name="main.ml_models.fraud_detector"
)
```

**Implementation Complexity**: Low
**Estimated Effort**: 2 days

---

### AI-7: MLflow Experiment Permissions

**Check ID**: 125
**Category**: Identity & Access (IA-9)
**Severity**: Low
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Description
Validates that MLflow experiments have proper ACLs and are not world-readable.

#### Technical Specification

**API Endpoint**: `/api/2.0/permissions/experiments/{id}`

**Rule Logic**:
- Query all MLflow experiments
- Check permissions for "all users" or overly broad access
- Flag experiments without explicit ACLs

**Recommendation**:
```
Configure MLflow experiment permissions:
1. Grant CAN_MANAGE to experiment owners/leads
2. Grant CAN_READ to team members
3. Remove "all users" permissions
4. Use groups instead of individual users
```

**Implementation Complexity**: Low
**Estimated Effort**: 2 days

---

## Serverless Network Security

### SLS-1: Serverless Network Policies Configured

**Check ID**: 126
**Category**: Network Security (NS-10)
**Severity**: High
**Cloud Support**: AWS ✓, Azure ✓, GCP ✗

#### Description
Validates that account has custom serverless network policies configured, not relying on the default "allow all" policy.

#### Business Justification
Serverless network policies are critical for:
- Data exfiltration prevention
- Compliance (PCI-DSS network segmentation)
- Zero-trust network architecture
- Shadow IT prevention

#### Technical Specification

**API Endpoint**: `/api/2.0/accounts/{account_id}/network-policies`

**API Response Fields**:
```json
{
  "network_policies": [
    {
      "network_policy_id": "np-abc123",
      "name": "production-policy",
      "egress_rules": [
        {
          "destination": "s3.amazonaws.com",
          "protocol": "https",
          "action": "ALLOW"
        },
        {
          "destination": "*",
          "protocol": "*",
          "action": "DENY"
        }
      ]
    }
  ],
  "default_network_policy_id": "np-default"
}
```

**Rule Logic**:
- Query account-level network policies
- Check if only default policy exists
- Validate custom policies have restrictive egress rules
- Flag accounts using default allow-all policy

**SQL Query Pattern**:
```sql
SELECT
    policy_id,
    policy_name,
    is_default,
    egress_rule_count,
    has_deny_all_rule
FROM network_policies
WHERE is_default = true
   OR egress_rule_count = 0
   OR has_deny_all_rule = false
```

**Client Method**:
```python
# File: src/securityanalysistoolproject/clientpkgs/network_policies_client.py

class NetworkPoliciesClient(SatDBClient):
    def __init__(self, configs):
        super().__init__(configs)

    def get_network_policies(self):
        """Get all serverless network policies at account level"""
        endpoint = "/api/2.0/network-policies"
        return self.get(endpoint)

    def get_network_policy_details(self, policy_id):
        """Get detailed configuration for a network policy"""
        endpoint = f"/api/2.0/network-policies/{policy_id}"
        return self.get(endpoint)

    def list_workspace_policy_assignments(self):
        """Get network policy assignments for all workspaces"""
        endpoint = "/api/2.0/network-policies/workspace-assignments"
        return self.get(endpoint)
```

**Bootstrap Integration**:
```python
# File: notebooks/Utils/accounts_bootstrap.py

def bootstrap_network_policies(acct_client):
    """Bootstrap network policies and workspace assignments"""
    # Network policies
    viewname = "network_policies"
    func = acct_client.get_network_policies
    bootstrap(viewname, func)

    # Workspace assignments
    viewname = "network_policy_assignments"
    func = acct_client.list_workspace_policy_assignments
    bootstrap(viewname, func)
```

**Recommendation**:
```
Configure custom serverless network policies:

1. Create Restrictive Policy:
   - Default DENY all egress
   - Explicitly ALLOW required destinations:
     - Cloud storage (S3, ADLS, GCS)
     - UC metastore endpoints
     - Package repositories (PyPI, Maven)
     - Internal APIs

2. Assign to Production Workspaces:
   - High-security workspaces: Most restrictive policy
   - Development workspaces: Moderate policy
   - Sandbox workspaces: Default policy (least restrictive)

3. Example Policy:
{
  "name": "production-egress-policy",
  "egress_rules": [
    {"destination": "s3.amazonaws.com", "protocol": "https", "action": "ALLOW"},
    {"destination": "pypi.org", "protocol": "https", "action": "ALLOW"},
    {"destination": "internal-api.company.com", "protocol": "https", "action": "ALLOW"},
    {"destination": "*", "protocol": "*", "action": "DENY"}
  ]
}

4. Monitoring:
   - Enable audit logs for network policy changes
   - Alert on policy violations
   - Review allowed destinations quarterly

Documentation: https://docs.databricks.com/aws/en/security/network/serverless-network-security/network-policies
```

**Implementation Complexity**: High (new API, requires account-level access)
**Estimated Effort**: 5 days
**Dependencies**: Serverless network policies feature (GA January 2025)

**Note**: This API may not yet be available in Databricks MCP tools. Requires investigation and potential custom implementation.

---

### SLS-2: Workspace Network Policy Assignment

**Check ID**: 127
**Category**: Network Security (NS-11)
**Severity**: High
**Cloud Support**: AWS ✓, Azure ✓, GCP ✗

#### Description
Validates that production workspaces have specific network policies attached, not using the default policy.

#### Technical Specification

**API Endpoint**: `/api/2.0/network-policies/workspace-assignments`

**Rule Logic**:
- Query workspace network policy assignments
- Identify production workspaces (naming convention or tag)
- Check if assigned policy is default or custom
- Flag production workspaces without custom policies

**SQL Query Pattern**:
```sql
SELECT
    w.workspace_id,
    w.workspace_name,
    w.environment_type,
    np.policy_name,
    np.is_default
FROM workspaces w
LEFT JOIN network_policy_assignments npa
  ON w.workspace_id = npa.workspace_id
LEFT JOIN network_policies np
  ON npa.policy_id = np.policy_id
WHERE w.environment_type = 'PRODUCTION'
  AND (np.is_default = true OR np.policy_id IS NULL)
```

**Recommendation**:
```
Assign custom network policies to production workspaces:
1. Identify workspace environment types (prod, dev, test)
2. Create tiered network policies (prod-policy, dev-policy)
3. Assign policies via Databricks Console or API
4. Document policy rationale and approved destinations

Assignment command:
POST /api/2.0/network-policies/workspace-assignments
{
  "workspace_id": "123456789",
  "network_policy_id": "np-production"
}
```

**Implementation Complexity**: Medium
**Estimated Effort**: 3 days

---

### SLS-3: Serverless Egress Restrictions

**Check ID**: 128
**Category**: Network Security (NS-12)
**Severity**: Medium
**Cloud Support**: AWS ✓, Azure ✓, GCP ✗

#### Description
Validates that serverless network policies have explicit egress restrictions, not allowing unrestricted outbound connections.

#### Technical Specification

**Rule Logic**:
- Query network policies
- Parse egress rules
- Flag policies with:
  - "*" destination with ALLOW action
  - No explicit DENY rule
  - Overly broad CIDR blocks (0.0.0.0/0)

**Recommendation**:
```
Configure restrictive egress rules:
1. Start with DENY all egress
2. Add ALLOW rules for specific destinations:
   - FQDN: "s3.amazonaws.com"
   - CIDR: "10.0.0.0/8" (internal network)
   - Protocol: HTTPS only
3. Order rules from specific to general
4. Log blocked connections for tuning
```

**Implementation Complexity**: Medium
**Estimated Effort**: 3 days

---

### SLS-4: Serverless SQL Warehouse Security

**Check ID**: 129
**Category**: Network Security (NS-13)
**Severity**: Medium
**Cloud Support**: AWS ✓, Azure ✓, GCP ✗

#### Description
Validates that serverless SQL warehouses are deployed in workspaces with network policies enforced.

#### Technical Specification

**API Endpoints**:
- `/api/2.0/sql/warehouses` (list serverless warehouses)
- `/api/2.0/network-policies/workspace-assignments` (workspace policies)

**Rule Logic**:
- Query all SQL warehouses
- Filter for serverless type (`warehouse_type = 'PRO'` or `enable_serverless_compute = true`)
- Join with workspace network policy assignments
- Flag serverless warehouses in workspaces without custom policies

**SQL Query Pattern**:
```sql
SELECT
    w.id as warehouse_id,
    w.name as warehouse_name,
    w.warehouse_type,
    ws.workspace_id,
    ws.workspace_name,
    np.policy_name,
    np.is_default
FROM sql_warehouses_{workspace_id} w
JOIN workspaces ws ON w.workspace_id = ws.workspace_id
LEFT JOIN network_policy_assignments npa ON ws.workspace_id = npa.workspace_id
LEFT JOIN network_policies np ON npa.policy_id = np.policy_id
WHERE w.enable_serverless_compute = true
  AND (np.is_default = true OR np.policy_id IS NULL)
```

**Recommendation**:
```
Secure serverless SQL warehouses:
1. Deploy serverless warehouses only in workspaces with custom network policies
2. For existing warehouses:
   - Migrate to secured workspaces
   - Or assign network policy to current workspace
3. Monitor warehouse network activity via audit logs
4. Use Private Link for additional isolation
```

**Implementation Complexity**: Low
**Estimated Effort**: 2 days

---

## Git Security

### GIT-1: Git URL Allowlist Enforcement

**Check ID**: 130
**Category**: Data Protection (DP-17)
**Severity**: Medium
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Description
Validates that Git URL allowlist is configured and enforced to prevent cloning from untrusted repositories.

#### Business Justification
Git URL allowlists prevent:
- Malicious code injection via untrusted repos
- Data exfiltration via unauthorized Git push
- Supply chain attacks
- Intellectual property theft

#### Technical Specification

**API Endpoint**: `/api/2.0/workspace-conf?keys=enableGitUrlAllowlist,projectsAllowList`

**API Response Fields**:
```json
{
  "enableGitUrlAllowlist": "true",
  "projectsAllowList": "github.com/company-org,gitlab.company.com"
}
```

**Rule Logic**:
- Query workspace-conf for Git settings
- Check if `enableGitUrlAllowlist` is "true"
- Validate `projectsAllowList` is not empty
- Flag workspaces without allowlist enforcement

**SQL Query Pattern**:
```sql
SELECT
    workspace_id,
    workspace_name,
    git_allowlist_enabled,
    git_allowed_urls
FROM workspace_settings_{workspace_id}
WHERE git_allowlist_enabled = false
   OR git_allowed_urls IS NULL
   OR git_allowed_urls = ''
```

**Client Method**:
```python
# File: src/securityanalysistoolproject/clientpkgs/ws_settings_client.py

def get_git_url_allowlist(self):
    """Get Git URL allowlist configuration"""
    endpoint = "/api/2.0/workspace-conf"
    params = {"keys": "enableGitUrlAllowlist,projectsAllowList"}
    response = self.get(endpoint, params=params)

    return {
        'allowlist_enabled': response.get('enableGitUrlAllowlist') == 'true',
        'allowed_urls': response.get('projectsAllowList', '').split(',')
    }
```

**Recommendation**:
```
Configure Git URL allowlist:

1. Enable Enforcement:
   - Workspace Admin Console → Settings → Git URL Allowlist
   - Enable "Restrict Git URLs"

2. Configure Allowed URLs:
   - Add approved Git providers:
     - github.com/your-org
     - gitlab.company.com
     - bitbucket.org/your-team
   - Use specific org/team paths, not wildcard domains

3. Test Configuration:
   - Attempt to clone from allowed URL (should succeed)
   - Attempt to clone from blocked URL (should fail)

4. Communication:
   - Notify users of allowlist before enforcement
   - Provide process for requesting new URLs
   - Document approved Git providers

Example Configuration:
{
  "enableGitUrlAllowlist": true,
  "projectsAllowList": "github.com/company-org,gitlab.company.com"
}

Changes take up to 15 minutes to propagate.

Documentation: https://docs.databricks.com/repos/repos-setup.html
```

**Implementation Complexity**: Low
**Estimated Effort**: 2 days
**Dependencies**: Git folders feature enabled

---

### GIT-2: Git Restriction Mode

**Check ID**: 131
**Category**: Data Protection (DP-18)
**Severity**: Low
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Description
Validates that Git operations have appropriate restrictions configured (clone-only, commit restrictions, push restrictions).

#### Technical Specification

**API Endpoint**: `/api/2.0/workspace-conf?keys=gitRestrictionMode`

**Rule Logic**:
- Query workspace-conf for Git restriction settings
- Check restriction mode: UNRESTRICTED, CLONE_ONLY, NO_PUSH
- Recommend appropriate mode based on workspace type

**Recommendation**:
```
Configure Git restriction modes by workspace:
- Production: CLONE_ONLY (read-only repos)
- Development: NO_PUSH (prevent accidental pushes to main)
- Sandbox: UNRESTRICTED (allow all operations)

Benefits:
- Prevent accidental changes to production code
- Enforce pull request workflows
- Reduce security incidents
```

**Implementation Complexity**: Low
**Estimated Effort**: 1 day

---

### GIT-3: Bitbucket Authentication Migration

**Check ID**: 132
**Category**: Identity & Access (IA-10)
**Severity**: Medium
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Description
Validates that Bitbucket Git repos are not using deprecated app passwords (deprecated June 2026), migrated to API tokens or OAuth.

#### Business Justification
Bitbucket app passwords deprecated June 2026:
- Existing app passwords will stop working
- Must migrate to OAuth or API tokens
- Prevent service disruption

#### Technical Specification

**API Endpoint**: `/api/2.0/repos`

**Rule Logic**:
- Query all Git repos
- Filter for Bitbucket provider
- Check authentication method (app password vs OAuth/token)
- Flag repos using deprecated app passwords

**SQL Query Pattern**:
```sql
SELECT
    id,
    url,
    provider,
    credential_type
FROM git_repos_{workspace_id}
WHERE provider LIKE '%bitbucket%'
  AND credential_type = 'app_password'
```

**Recommendation**:
```
Migrate Bitbucket authentication:

1. Create Bitbucket API Token:
   - Bitbucket Settings → Personal access tokens
   - Create token with 'repository:read' scope

2. Update Databricks Repo:
   - Edit repo → Change credentials
   - Select "API Token" authentication
   - Enter new token

3. Timeline:
   - NOW: Medium severity (advance warning)
   - June 2026: High severity (breaking change imminent)
   - Post-June 2026: Critical (service disruption)

4. Bulk Migration:
   - Use Repos API to update all repos
   - Test each repo after migration
   - Document new authentication method

Documentation: https://support.atlassian.com/bitbucket-cloud/docs/app-passwords/
```

**Implementation Complexity**: Low
**Estimated Effort**: 2 days
**Priority**: Medium now, will escalate to High in Q2 2026

---

## Databricks Apps Security

### APP-1: Apps Use Service Principal Identity

**Check ID**: 133
**Category**: Identity & Access (IA-11)
**Severity**: High
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Description
Validates that Databricks Apps have dedicated service principals assigned, not running as user identities.

#### Business Justification
Service principal identities for apps ensure:
- Consistent permissions (not tied to individual users)
- Audit trail (app actions distinct from user actions)
- Security (apps can't perform actions as admin)
- Operational continuity (works when creator leaves)

#### Technical Specification

**API Endpoint**: `/api/2.0/apps`

**API Response Fields**:
```json
{
  "apps": [
    {
      "name": "sales-dashboard",
      "service_principal_id": "sp-abc123",
      "service_principal_name": "sales-dashboard-sp",
      "created_by": "user@company.com"
    }
  ]
}
```

**Rule Logic**:
- Query all Databricks Apps
- Check if `service_principal_id` is configured
- Flag apps without dedicated service principals
- Distinguish between dev/test and production apps

**SQL Query Pattern**:
```sql
SELECT
    name,
    app_id,
    service_principal_id,
    created_by,
    status
FROM databricks_apps_{workspace_id}
WHERE service_principal_id IS NULL
   OR service_principal_id = ''
```

**Client Method**:
```python
# File: src/securityanalysistoolproject/clientpkgs/apps_client.py

class AppsClient(SatDBClient):
    def __init__(self, configs):
        super().__init__(configs)

    def list_apps(self):
        """List all Databricks Apps in workspace"""
        endpoint = "/api/2.0/apps"
        return self.get(endpoint)

    def get_app_details(self, app_name):
        """Get detailed configuration for an app"""
        endpoint = f"/api/2.0/apps/{app_name}"
        return self.get(endpoint)

    def get_app_permissions(self, app_name):
        """Get permissions configured for an app"""
        endpoint = f"/api/2.0/apps/{app_name}/permissions"
        return self.get(endpoint)

    def list_apps_with_service_principals(self):
        """List apps with their service principal assignments"""
        apps = self.list_apps()

        result = []
        for app in apps.get('apps', []):
            app_name = app.get('name')
            details = self.get_app_details(app_name)

            result.append({
                'name': app_name,
                'app_id': app.get('id'),
                'service_principal_id': details.get('service_principal_id'),
                'service_principal_name': details.get('service_principal_name'),
                'created_by': app.get('created_by'),
                'status': app.get('status')
            })

        return result
```

**Bootstrap Integration**:
```python
# File: notebooks/Utils/workspace_bootstrap.py

def bootstrap_databricks_apps(ws_client, workspace_id):
    """Bootstrap Databricks Apps with service principal info"""
    viewname = f"databricks_apps_{workspace_id}"
    func = ws_client.list_apps_with_service_principals
    bootstrap(viewname, func)
```

**Recommendation**:
```
Configure service principals for Databricks Apps:

1. Create Service Principal:
   - Admin Console → Service Principals → Add
   - Name: <app-name>-sp
   - Grant necessary permissions (read tables, query SQL, etc.)

2. Assign to App:
   - App settings → Identity
   - Select service principal
   - App will run as this identity

3. Best Practices:
   - One service principal per app
   - Name: <app-name>-sp (consistent naming)
   - Minimal permissions (principle of least privilege)
   - Rotate credentials annually
   - Document app-to-SP mapping

4. Permissions to Grant:
   - Unity Catalog: USE CATALOG, USE SCHEMA, SELECT on tables
   - SQL Warehouses: CAN_USE on specific warehouse
   - Other resources: As needed per app functionality

Example:
App Name: customer-analytics-dashboard
Service Principal: customer-analytics-dashboard-sp
Permissions:
  - USE CATALOG main
  - USE SCHEMA main.analytics
  - SELECT ON main.analytics.customers
  - CAN_USE SQL Warehouse "Shared Warehouse"

Documentation: https://docs.databricks.com/dev-tools/databricks-apps/
```

**Implementation Complexity**: Medium
**Estimated Effort**: 3 days
**Dependencies**: Service principals configured, Apps feature GA

---

### APP-2: Apps Enforce SSO Authentication

**Check ID**: 134
**Category**: Identity & Access (IA-12)
**Severity**: Medium
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Description
Validates that Databricks Apps require SSO authentication, not one-time passcodes (OTP).

#### Technical Specification

**API Endpoint**: `/api/2.0/apps/{name}/config`

**Rule Logic**:
- Query app configuration
- Check authentication method: SSO vs OTP
- Flag apps allowing OTP authentication

**Recommendation**:
```
Enforce SSO authentication for apps:
1. App settings → Authentication
2. Select "Require SSO" (disable OTP fallback)
3. Benefits:
   - Consistent authentication (SAML/OIDC)
   - MFA enforcement
   - Centralized user management
   - Audit trail
```

**Implementation Complexity**: Low
**Estimated Effort**: 2 days

---

### APP-3: Apps Not Publicly Accessible

**Check ID**: 135
**Category**: Network Security (NS-14)
**Severity**: High
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Description
Validates that Databricks Apps require authentication and are not accessible anonymously.

#### Technical Specification

**API Endpoint**: `/api/2.0/apps/{name}/permissions`

**Rule Logic**:
- Query app permissions
- Check for "anonymous" or "all users" access
- Flag apps without authentication requirement

**Recommendation**:
```
Secure app access:
1. Remove anonymous access
2. Grant permissions explicitly:
   - CAN_USE: End users
   - CAN_MANAGE: App owners
3. For internal apps: Grant to AD groups
4. For external apps: Use SSO with external IdP
```

**Implementation Complexity**: Low
**Estimated Effort**: 2 days

---

### APP-4: App Permission Boundaries

**Check ID**: 136
**Category**: Identity & Access (IA-13)
**Severity**: Medium
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Description
Validates that apps have properly scoped permissions (CAN_MANAGE limited to owners, CAN_USE to end users).

#### Technical Specification

**API Endpoint**: `/api/2.0/apps/{name}/permissions`

**Rule Logic**:
- Query app permissions
- Check CAN_MANAGE is limited (< 5 users/groups)
- Check CAN_USE is appropriate for app audience
- Flag over-permissioned apps

**Recommendation**:
```
Configure app permission boundaries:
1. CAN_MANAGE: App owners only (2-3 people)
2. CAN_USE: Specific groups, not "all users"
3. Review permissions quarterly
4. Audit app access via system tables
```

**Implementation Complexity**: Low
**Estimated Effort**: 2 days

---

## Secrets Management

### SEC-1: External Secret Stores Configured

**Check ID**: 137
**Category**: Data Protection (DP-19)
**Severity**: Medium
**Cloud Support**: AWS ✓ (Secrets Manager), Azure ✓ (Key Vault), GCP ✓ (Secret Manager)

#### Description
Validates that production secret scopes use external secret stores (Azure Key Vault, AWS Secrets Manager, GCP Secret Manager) instead of Databricks-backed storage.

#### Business Justification
External secret stores provide:
- Centralized secret management across cloud services
- Hardware Security Module (HSM) backing
- Automated rotation capabilities
- Fine-grained IAM permissions
- Compliance (SOC 2, ISO 27001)

#### Technical Specification

**API Endpoint**: `/api/2.0/secrets/scopes/list`

**API Response Fields**:
```json
{
  "scopes": [
    {
      "name": "production-secrets",
      "backend_type": "AZURE_KEYVAULT",
      "keyvault_metadata": {
        "resource_id": "/subscriptions/.../vaults/prod-kv",
        "dns_name": "https://prod-kv.vault.azure.net/"
      }
    },
    {
      "name": "dev-secrets",
      "backend_type": "DATABRICKS"
    }
  ]
}
```

**Rule Logic**:
- Query all secret scopes
- Check `backend_type` field
- Flag production scopes with `backend_type = "DATABRICKS"`
- Categorize by scope name (prod, dev, test)

**SQL Query Pattern**:
```sql
SELECT
    name,
    backend_type,
    scope_type
FROM secret_scopes_{workspace_id}
WHERE backend_type = 'DATABRICKS'
  AND (
    name LIKE '%prod%' OR
    name LIKE '%production%' OR
    name LIKE '%prd%'
  )
```

**Recommendation**:
```
Configure external secret stores for production:

AWS:
1. Create AWS Secrets Manager secret
2. Create IAM policy for Databricks access
3. Create secret scope:
   databricks secrets create-scope --scope production-secrets \
     --backend aws-secrets-manager \
     --region us-east-1

Azure:
1. Create Azure Key Vault
2. Grant Databricks service principal access
3. Create secret scope:
   databricks secrets create-scope --scope production-secrets \
     --backend azure-keyvault \
     --resource-id <key-vault-resource-id> \
     --dns-name <key-vault-dns>

GCP:
1. Create GCP Secret Manager secret
2. Grant Databricks service account access
3. Create secret scope:
   databricks secrets create-scope --scope production-secrets \
     --backend gcp-secret-manager \
     --project-id <project-id>

Benefits:
- Centralized rotation policies
- HSM-backed encryption
- Cross-service secret sharing
- Cloud-native IAM integration

Note: Dev/test scopes can remain Databricks-backed for simplicity.
```

**Implementation Complexity**: Low
**Estimated Effort**: 2 days

---

### SEC-2: Secrets Not in Notebooks

**Check ID**: 138
**Category**: Data Protection (DP-20)
**Severity**: High
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Description
Validates that notebooks reference secrets via dbutils.secrets.get(), not hardcoding values.

**Note**: This check is already covered by the separate TruffleHog secret scanning notebook. May be redundant.

#### Technical Specification

**API Endpoint**: `/api/2.0/workspace/list` + content scanning

**Rule Logic**:
- Export all notebooks
- Scan cells for hardcoded secrets (regex patterns)
- Flag notebooks with potential secrets

**Recommendation**:
```
Use dbutils.secrets.get() for secrets:
- Good: password = dbutils.secrets.get(scope="prod", key="db-password")
- Bad: password = "MyP@ssw0rd123"

TruffleHog integration already provides this scanning.
Consider this check redundant with existing secret scanner.
```

**Implementation Complexity**: Low (already implemented via TruffleHog)
**Estimated Effort**: 0 days (redundant)
**Action**: Mark as covered by existing TruffleHog notebook

---

### SEC-3: Secrets Not in Init Scripts

**Check ID**: 139
**Category**: Data Protection (DP-21)
**Severity**: High
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Description
Validates that init scripts use dbutils.secrets.get() instead of hardcoding secrets.

#### Technical Specification

**API Endpoint**: `/api/2.0/global-init-scripts`

**Rule Logic**:
- Query all init scripts
- Parse script content for hardcoded secrets
- Flag scripts without dbutils.secrets.get() calls

**Recommendation**:
```
Use secrets in init scripts:
#!/bin/bash
# Good:
API_KEY=$(databricks secrets get --scope prod --key api-key)

# Bad:
API_KEY="abc123-secret-key"

Init scripts have access to dbutils via:
- databricks CLI
- Environment variables (set via secrets)
```

**Implementation Complexity**: Medium
**Estimated Effort**: 3 days

---

## System Tables & Monitoring

### SYS-1: Automated Security Monitoring Configured

**Check ID**: 140
**Category**: Governance (GOV-43)
**Severity**: Low
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Description
Validates that SQL queries are scheduled to monitor security events from system tables (audit logs).

#### Technical Specification

**API Endpoint**: `/api/2.0/jobs/list`

**Rule Logic**:
- Query all jobs
- Filter for jobs with SQL tasks querying system.access.audit
- Check if security monitoring queries exist
- Flag workspaces without automated monitoring

**Recommendation**:
```
Configure automated security monitoring:
1. Create SQL queries for security events:
   - Failed login attempts
   - Permission changes
   - Secret access
   - Data exfiltration patterns

2. Schedule jobs to run queries:
   - Frequency: Hourly or daily
   - Destination: Alert destination or dashboard

3. Example Query:
SELECT
  event_time,
  user_identity,
  action_name,
  request_params
FROM system.access.audit
WHERE action_name IN ('createToken', 'deleteToken', 'updatePermissions')
  AND event_time > CURRENT_TIMESTAMP - INTERVAL 1 HOUR

4. Alert on Anomalies:
   - Unusual access patterns
   - Off-hours activity
   - Bulk permission changes
```

**Implementation Complexity**: Low
**Estimated Effort**: 2 days

---

### SYS-2: Audit Log Retention Policies

**Check ID**: 141
**Category**: Governance (GOV-44)
**Severity**: Medium
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Description
Validates that system tables have appropriate retention configured for compliance requirements.

#### Technical Specification

**API Endpoint**: `/api/2.0/unity-catalog/metastores/{id}/systemschemas`

**Rule Logic**:
- Query metastore system schema configuration
- Check retention policies for audit log tables
- Validate retention meets compliance requirements (typically 90 days to 7 years)

**Recommendation**:
```
Configure audit log retention:
1. Compliance requirements vary:
   - HIPAA: 6 years
   - SOX: 7 years
   - GDPR: Varies by purpose
   - PCI-DSS: 1 year (3 months immediately available)

2. System tables default retention: 1 year
3. For longer retention:
   - Export to external storage (S3, ADLS)
   - Use Delta table time travel
   - Configure archival jobs

4. Example Retention Job:
CREATE TABLE audit_archive AS
SELECT * FROM system.access.audit
WHERE event_date < CURRENT_DATE - INTERVAL 90 DAYS;

-- Delete from system table (if needed for performance)
DELETE FROM system.access.audit
WHERE event_date < CURRENT_DATE - INTERVAL 90 DAYS;
```

**Implementation Complexity**: Medium
**Estimated Effort**: 3 days

---

### SYS-3: Alert Destinations Configured

**Check ID**: 142
**Category**: Governance (GOV-45)
**Severity**: Low
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Description
Validates that notification destinations are configured for security alerts.

#### Technical Specification

**API Endpoint**: `/api/2.0/notification-destinations`

**Rule Logic**:
- Query notification destinations
- Check if security-related destinations exist
- Flag workspaces without alert configurations

**Recommendation**:
```
Configure alert destinations:
1. Create notification destinations:
   - Email: security-team@company.com
   - Slack: #security-alerts
   - PagerDuty: For critical alerts
   - Webhook: Custom SIEM integration

2. Associate with SQL alerts:
   - Failed login threshold
   - Permission changes
   - Secret access patterns
   - Data exfiltration

3. Example:
POST /api/2.0/notification-destinations
{
  "name": "Security Team Email",
  "config": {
    "type": "email",
    "addresses": ["security@company.com"]
  }
}
```

**Implementation Complexity**: Low
**Estimated Effort**: 2 days

---

## Additional Enhancements

### ENH-1: Workspace Encryption Status

**Check ID**: 143
**Category**: Data Protection (DP-22)
**Severity**: Medium
**Cloud Support**: AWS ✓ (CMK), Azure ✓ (CMK), GCP ✓ (CMEK)

#### Description
Validates that workspace storage encryption is enabled with customer-managed keys (CMK) or platform-managed keys.

#### Technical Specification

**API Endpoint**: `/api/2.0/accounts/{account_id}/workspaces/{workspace_id}`

**Rule Logic**:
- Query workspace configuration
- Check encryption settings for:
  - DBFS root bucket
  - Notebook storage
  - System data
- Flag workspaces without encryption

**Recommendation**:
```
Configure workspace encryption:
1. AWS: Enable CMK for S3 root bucket
2. Azure: Enable CMK for ADLS Gen2
3. GCP: Enable CMEK for GCS bucket

Benefits:
- Data sovereignty
- Key rotation control
- Compliance (FIPS 140-2)
- Encryption at rest validation
```

**Implementation Complexity**: Low
**Estimated Effort**: 2 days

---

### ENH-2: Cluster Policy Inheritance

**Check ID**: 144
**Category**: Governance (GOV-46)
**Severity**: Medium
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Description
Validates that all clusters inherit from cluster policies, no policy-free clusters exist.

#### Technical Specification

**API Endpoint**: `/api/2.0/clusters/list`

**Rule Logic**:
- Query all clusters
- Check if `policy_id` is configured
- Flag clusters without policies

**SQL Query Pattern**:
```sql
SELECT
    cluster_id,
    cluster_name,
    policy_id,
    creator_user_name
FROM clusters_{workspace_id}
WHERE policy_id IS NULL
  AND cluster_source != 'JOB'  -- Job clusters inherit from job policy
```

**Recommendation**:
```
Enforce cluster policy inheritance:
1. Create default policy for all clusters
2. Disable policy-free cluster creation:
   - Workspace settings → Cluster Policies
   - Require policy for all clusters
3. Migrate existing clusters to policies
4. Document policy categories (dev, prod, ML, etc.)
```

**Implementation Complexity**: Low
**Estimated Effort**: 2 days

---

### ENH-3: Job Owner is Service Principal

**Check ID**: 145
**Category**: Identity & Access (IA-14)
**Severity**: Medium
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Description
Validates that production jobs are owned by service principals, not individual users.

#### Technical Specification

**API Endpoint**: `/api/2.0/jobs/list`

**Rule Logic**:
- Query all jobs
- Check if `creator_user_name` is email (user) vs SP name
- Flag production jobs owned by users

**SQL Query Pattern**:
```sql
SELECT
    job_id,
    job_name,
    creator_user_name,
    run_as_user_name
FROM jobs_{workspace_id}
WHERE (job_name LIKE '%prod%' OR job_name LIKE '%production%')
  AND (creator_user_name LIKE '%@%' OR run_as_user_name LIKE '%@%')
```

**Recommendation**:
```
Transfer job ownership to service principals:
1. Create service principal per application
2. Transfer ownership:
   - Edit job → Permissions
   - Change owner to service principal
3. Update run_as to service principal
4. Benefits:
   - Jobs continue when creator leaves
   - Consistent permissions
   - Better audit trail
```

**Implementation Complexity**: Low
**Estimated Effort**: 2 days

---

## Summary Statistics

**Total New Checks**: 35

**By Category**:
- Unity Catalog Fine-Grained Security: 8 checks
- AI/ML Security: 7 checks
- Serverless Network Security: 4 checks
- Git Security: 3 checks
- Databricks Apps Security: 4 checks
- Secrets Management: 3 checks (1 redundant)
- System Tables & Monitoring: 3 checks
- Additional Enhancements: 3 checks

**By Severity**:
- High: 14 checks (40%)
- Medium: 16 checks (46%)
- Low: 4 checks (11%)
- Informational: 1 check (3%)

**By Cloud Support**:
- AWS: 35 checks (100%)
- Azure: 34 checks (97%)
- GCP: 30 checks (86%)

**Implementation Complexity**:
- Low: 18 checks (51%)
- Medium: 14 checks (40%)
- High: 3 checks (9%)

**Total Estimated Effort**: ~90 days (6 sprints, 2-week sprints, 2-3 engineers)

---

**End of New Checks Specifications**
