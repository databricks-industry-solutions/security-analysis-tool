# Security Checks to Modify

**Version**: 1.0
**Date**: 2026-01-16
**Total Modifications**: 12

---

## Table of Contents

1. [High Impact Modifications (4)](#high-impact-modifications)
2. [Medium Impact Modifications (4)](#medium-impact-modifications)
3. [Low Impact Modifications (4)](#low-impact-modifications)
4. [Implementation Summary](#implementation-summary)

---

## High Impact Modifications

### Modify-1: Check 53 (GOV-16) - Unity Catalog Metastore Assignment

**Current Check ID**: 53
**Category**: Governance (GOV-16)
**Current Severity**: High
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Current Implementation

**Current Logic**:
- Binary check: Is metastore assigned to workspace? (Yes/No)
- Pass if metastore assigned, fail if not

**Current SQL Query**:
```sql
SELECT
    workspace_id,
    workspace_name,
    metastore_id
FROM workspaces
WHERE metastore_id IS NULL
```

**Current Recommendation**:
```
Assign Unity Catalog metastore to workspace for governed data access.
```

#### Limitations

1. **No Region Validation**: Doesn't check if metastore region matches workspace region
2. **Data Residency Risk**: Cross-region metastore assignments violate data residency requirements
3. **Performance Impact**: Cross-region queries have higher latency
4. **Compliance Gap**: GDPR, CCPA, and industry regulations require data residency

#### Enhanced Implementation

**Enhanced Logic**:
- Check if metastore assigned (existing logic)
- **NEW**: Validate metastore region matches workspace region
- **NEW**: Flag cross-region assignments as violations

**Enhanced SQL Query**:
```sql
SELECT
    w.workspace_id,
    w.workspace_name,
    w.region as workspace_region,
    w.metastore_id,
    m.name as metastore_name,
    m.region as metastore_region,
    CASE
        WHEN w.metastore_id IS NULL THEN 'NO_METASTORE'
        WHEN w.region != m.region THEN 'REGION_MISMATCH'
        ELSE 'OK'
    END as status
FROM workspaces w
LEFT JOIN metastores m ON w.metastore_id = m.metastore_id
WHERE w.metastore_id IS NULL
   OR w.region != m.region
```

**Enhanced Rule Function**:
```python
def uc_metastore_assignment_rule(df):
    if df is None or isEmpty(df):
        return (check_id, 0, {})  # Pass: All workspaces have region-matched metastores

    violations = df.collect()
    no_metastore = [v for v in violations if v.status == 'NO_METASTORE']
    region_mismatch = [v for v in violations if v.status == 'REGION_MISMATCH']

    total_violations = len(violations)

    return (check_id, total_violations, {
        'workspaces_without_metastore': [
            [v.workspace_id, v.workspace_name, v.workspace_region]
            for v in no_metastore
        ],
        'workspaces_with_region_mismatch': [
            [v.workspace_id, v.workspace_name, v.workspace_region, v.metastore_region]
            for v in region_mismatch
        ]
    })
```

**Enhanced Recommendation**:
```
Unity Catalog metastore must be assigned to workspace in the same region:

1. Data Residency Compliance:
   - GDPR: Data must remain in EU (for EU workspaces)
   - CCPA: California data residency
   - Industry regulations: Healthcare (HIPAA), Finance (PCI-DSS)

2. Cross-Region Assignment Issues:
   - Higher latency for queries
   - Increased egress costs
   - Compliance violations
   - Potential data sovereignty issues

3. Resolution:
   a) No Metastore:
      - Assign metastore in same region as workspace
      - Example: us-west-2 workspace → us-west-2 metastore

   b) Region Mismatch:
      - Create new metastore in workspace region
      - Migrate data using Delta sharing or COPY INTO
      - Re-assign workspace to new metastore

4. Example Fix:
   # Create metastore in correct region
   databricks unity-catalog metastores create \
     --name "metastore-us-west-2" \
     --region "us-west-2" \
     --storage-root "s3://metastore-bucket-us-west-2/metastore"

   # Assign to workspace
   databricks workspaces update <workspace-id> \
     --metastore-id <metastore-id>

5. Validation:
   SELECT workspace_name, workspace_region, metastore_region
   FROM workspaces JOIN metastores
   WHERE workspace_region = metastore_region;
```

#### Client Method Changes

```python
# File: src/securityanalysistoolproject/clientpkgs/unity_catalog_client.py

def get_metastores_with_regions(self):
    """Get all metastores with their region information"""
    endpoint = "/api/2.1/unity-catalog/metastores"
    response = self.get(endpoint)

    metastores = []
    for ms in response.get('metastores', []):
        metastores.append({
            'metastore_id': ms.get('metastore_id'),
            'name': ms.get('name'),
            'region': ms.get('region'),
            'storage_root': ms.get('storage_root'),
            'owner': ms.get('owner')
        })

    return metastores
```

**Bootstrap Changes**:
```python
# File: notebooks/Utils/accounts_bootstrap.py

# Add metastore region collection
def bootstrap_metastores_with_regions(acct_client):
    viewname = "metastores_with_regions"
    func = acct_client.get_metastores_with_regions
    bootstrap(viewname, func)
```

#### Migration Path

**Phase 1**: Add region validation without failing checks
- Collect data on region mismatches
- Report as informational

**Phase 2**: Upgrade to warning
- Alert on region mismatches
- Provide 90-day remediation window

**Phase 3**: Enforce
- Fail check on region mismatch
- Require remediation

#### Benefits

- **Compliance**: Ensures data residency requirements met
- **Performance**: Eliminates cross-region query latency
- **Cost**: Reduces egress charges
- **Security**: Proper data sovereignty

**Implementation Complexity**: Low
**Estimated Effort**: 2 days
**Backward Compatibility**: Yes (existing pass/fail logic preserved, adds new validation)

---

### Modify-2: Check 17 (GOV-12) - Unity Catalog Enabled Clusters

**Current Check ID**: 17
**Category**: Governance (GOV-12)
**Current Severity**: High
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Current Implementation

**Current Logic**:
- Checks if clusters have `data_security_mode` set to:
  - `USER_ISOLATION` (UC with user isolation)
  - `SINGLE_USER` (UC with single user)
- Fails if mode is `NONE` or `LEGACY_TABLE_ACL`

**Current SQL Query**:
```sql
SELECT
    cluster_id,
    cluster_name,
    data_security_mode
FROM clusters
WHERE data_security_mode NOT IN ('USER_ISOLATION', 'SINGLE_USER')
```

#### Limitations

1. **False Positives**: Flags `SHARED` mode as non-compliant
2. **UC Shared Mode**: `SHARED` with Unity Catalog is a valid, secure configuration
3. **Confusion**: Users uncertain if SHARED mode is acceptable

#### Enhanced Implementation

**Enhanced Logic**:
- Accept `USER_ISOLATION`, `SINGLE_USER`, **and `SHARED`** as valid UC modes
- Only fail on `NONE` or `LEGACY_TABLE_ACL`

**Enhanced SQL Query**:
```sql
SELECT
    cluster_id,
    cluster_name,
    data_security_mode,
    CASE
        WHEN data_security_mode IN ('USER_ISOLATION', 'SINGLE_USER', 'SHARED') THEN 'UC_ENABLED'
        WHEN data_security_mode = 'LEGACY_TABLE_ACL' THEN 'LEGACY'
        WHEN data_security_mode = 'NONE' THEN 'NO_SECURITY'
        ELSE 'UNKNOWN'
    END as security_status
FROM clusters
WHERE data_security_mode NOT IN ('USER_ISOLATION', 'SINGLE_USER', 'SHARED')
```

**Enhanced Recommendation**:
```
Enable Unity Catalog on all clusters:

Valid UC Modes:
1. USER_ISOLATION:
   - Multi-user clusters
   - Process and credential isolation per user
   - Recommended for interactive analytics

2. SINGLE_USER:
   - Dedicated to one user
   - Maximum isolation
   - Recommended for sensitive workloads

3. SHARED (NEW):
   - Multi-user with shared UC access
   - Less isolation than USER_ISOLATION
   - Valid for trusted user groups
   - Recommended for cost efficiency

Invalid Modes:
- NONE: No access control (non-compliant)
- LEGACY_TABLE_ACL: Deprecated (migrate to UC)

Configuration:
{
  "data_security_mode": "SHARED",  // Now accepted
  "spark_conf": {
    "spark.databricks.unityCatalog.enabled": "true"
  }
}
```

**Benefits**:
- Eliminates false positives
- Aligns with Databricks best practices
- Reduces confusion about SHARED mode

**Implementation Complexity**: Low
**Estimated Effort**: 1 day
**Backward Compatibility**: Yes (only adds valid mode, doesn't remove checks)

---

### Modify-3: Check 42 (IA-7) - Service Principals

**Current Check ID**: 42
**Category**: Identity & Access (IA-7)
**Current Severity**: Medium
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Current Implementation

**Current Logic**:
- Binary check: Do service principals exist? (Yes/No)
- Pass if at least one SP exists

**Current SQL Query**:
```sql
SELECT COUNT(*) as sp_count
FROM service_principals
HAVING sp_count > 0
```

#### Limitations

1. **Shallow Validation**: Only checks existence, not usage
2. **Unused SPs**: SPs may exist but not be used for jobs/apps
3. **Human Identity Risk**: Production jobs may still run as users
4. **No Operational Benefit**: Check doesn't drive security improvement

#### Enhanced Implementation

**Enhanced Logic**:
- Check if service principals exist (existing logic)
- **NEW**: Validate production jobs run as SPs, not users
- **NEW**: Validate production apps use SPs
- **NEW**: Flag user-owned automation

**Enhanced SQL Query**:
```sql
-- Part 1: Service principals exist
SELECT 'service_principals' as check_type, COUNT(*) as count
FROM service_principals

UNION ALL

-- Part 2: Jobs running as users (should be SPs)
SELECT 'jobs_as_users' as check_type, COUNT(*) as count
FROM jobs
WHERE (job_name LIKE '%prod%' OR job_name LIKE '%production%')
  AND run_as_user_name LIKE '%@%'  -- Email indicates user

UNION ALL

-- Part 3: Apps without service principals
SELECT 'apps_without_sp' as check_type, COUNT(*) as count
FROM databricks_apps
WHERE service_principal_id IS NULL
```

**Enhanced Rule Function**:
```python
def service_principals_rule(df):
    if df is None or isEmpty(df):
        return (check_id, 1, {'message': 'No data collected'})

    results = df.collect()

    sp_count = next((r.count for r in results if r.check_type == 'service_principals'), 0)
    jobs_as_users = next((r.count for r in results if r.check_type == 'jobs_as_users'), 0)
    apps_without_sp = next((r.count for r in results if r.check_type == 'apps_without_sp'), 0)

    violations = []

    if sp_count == 0:
        violations.append('No service principals configured')

    if jobs_as_users > 0:
        violations.append(f'{jobs_as_users} production jobs running as users')

    if apps_without_sp > 0:
        violations.append(f'{apps_without_sp} apps without service principals')

    violation_count = len(violations)

    return (check_id, violation_count, {
        'sp_count': sp_count,
        'jobs_as_users': jobs_as_users,
        'apps_without_sp': apps_without_sp,
        'violations': violations
    })
```

**Enhanced Recommendation**:
```
Service principals should be used for all automation:

1. Create Service Principals:
   - One SP per application/service
   - Name: <app-name>-sp
   - Minimal permissions

2. Production Jobs:
   - Run as service principal, not user
   - Transfer ownership: Edit job → Owner → <sp-name>
   - Set run_as: Edit job → Advanced → Run as → <sp-name>

3. Databricks Apps:
   - Assign SP identity: App settings → Identity → <sp-name>
   - Apps should never run as user

4. Benefits:
   - Continuity when users leave organization
   - Consistent permissions
   - Better audit trail
   - No personal credential exposure

5. Example:
   # Create SP
   databricks service-principals create --display-name "etl-pipeline-sp"

   # Grant permissions
   databricks workspace-access grant \
     --principal "etl-pipeline-sp" \
     --permission CAN_USE \
     --resource SQL_WAREHOUSE

   # Update job
   databricks jobs update <job-id> --run-as-service-principal "etl-pipeline-sp"

Current Status:
- Service Principals: {sp_count}
- Jobs as Users: {jobs_as_users} (should be 0)
- Apps without SP: {apps_without_sp} (should be 0)
```

**Benefits**:
- Operational security improvement
- Drives actual SP usage, not just existence
- Aligns with principle of least privilege

**Implementation Complexity**: Medium
**Estimated Effort**: 3 days
**Backward Compatibility**: Yes (existing SP check preserved, adds usage validation)

---

### Modify-4: Checks 103, 109 (INFO-37, INFO-40) - CSP/ESM

**Current Check IDs**: 103 (INFO-37), 109 (INFO-40)
**Categories**: Informational
**Current Severity**: Informational
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Current Implementation

**Check 103 (CSP - Compliance Security Profile)**:
```sql
SELECT
    workspace_id,
    setting_name,
    setting_value
FROM workspace_settings
WHERE setting_name = 'compliance-security-profile'
  AND setting_value = 'enabled'
```

**Check 109 (ESM - Enhanced Security Monitoring)**:
```sql
SELECT
    workspace_id,
    setting_name,
    setting_value
FROM workspace_settings
WHERE setting_name = 'enhanced-security-monitoring'
  AND setting_value = 'enabled'
```

#### Limitations

1. **Binary Check**: Only validates if enabled/disabled
2. **No Standard Validation**: Doesn't check which compliance standards are configured
3. **No Enforcement Validation**: Doesn't verify standards are actively enforced
4. **Compliance Gap**: Can't report on HIPAA, PCI-DSS, FIPS compliance status

#### Enhanced Implementation

**Enhanced Logic**:
- Check if CSP/ESM enabled (existing logic)
- **NEW**: Query which compliance standards are configured
- **NEW**: Validate standards are appropriate for workspace type
- **NEW**: Report enforcement status

**Enhanced SQL Query**:
```sql
SELECT
    w.workspace_id,
    w.workspace_name,
    w.environment_type,
    csp.setting_value as csp_enabled,
    csp.compliance_standards,
    esm.setting_value as esm_enabled,
    esm.monitoring_level
FROM workspaces w
LEFT JOIN (
    SELECT
        workspace_id,
        setting_value,
        JSON_EXTRACT(setting_value, '$.compliance_standards') as compliance_standards
    FROM workspace_settings
    WHERE setting_name = 'compliance-security-profile'
) csp ON w.workspace_id = csp.workspace_id
LEFT JOIN (
    SELECT
        workspace_id,
        setting_value,
        JSON_EXTRACT(setting_value, '$.monitoring_level') as monitoring_level
    FROM workspace_settings
    WHERE setting_name = 'enhanced-security-monitoring'
) esm ON w.workspace_id = esm.workspace_id
WHERE w.environment_type = 'PRODUCTION'
  AND (csp.setting_value IS NULL OR esm.setting_value IS NULL)
```

**Enhanced API Calls**:
```python
# File: src/securityanalysistoolproject/clientpkgs/ws_settings_client.py

def get_compliance_security_profile_details(self):
    """Get detailed CSP configuration including standards"""
    endpoint = "/api/2.0/settings/types/compliance_security_profile/names/default"
    response = self.get(endpoint)

    return {
        'enabled': response.get('setting_value', {}).get('enableComplianceSecurityProfile') == 'true',
        'compliance_standards': response.get('setting_value', {}).get('complianceStandards', []),
        'enforcement_level': response.get('setting_value', {}).get('enforcementLevel', 'none')
    }

def get_enhanced_security_monitoring_details(self):
    """Get detailed ESM configuration including monitoring level"""
    endpoint = "/api/2.0/settings/types/esm_enablement_workspace/names/default"
    response = self.get(endpoint)

    return {
        'enabled': response.get('setting_value', {}).get('enableEnhancedSecurityMonitoring') == 'true',
        'monitoring_level': response.get('setting_value', {}).get('enableExNetworkLogging', False),
        'features': response.get('setting_value', {}).get('features', [])
    }
```

**Enhanced Recommendation**:
```
Configure Compliance Security Profile and Enhanced Security Monitoring:

1. Compliance Security Profile (CSP):
   Enable with appropriate standards for your industry:

   - HIPAA (Healthcare):
     - Encryption at rest and in transit
     - Access logging and monitoring
     - BAA (Business Associate Agreement) compliance

   - PCI-DSS (Payment Card Industry):
     - Network segmentation
     - Encrypted storage
     - Access control requirements
     - Quarterly security scans

   - FIPS 140-2 (Government):
     - FIPS-validated cryptographic modules
     - Hardened cluster images
     - Strict access controls

   Configuration:
   {
     "enableComplianceSecurityProfile": true,
     "complianceStandards": ["HIPAA", "PCI-DSS"],
     "enforcementLevel": "strict"
   }

2. Enhanced Security Monitoring (ESM):
   Enable for additional security telemetry:
   - Enhanced network logging
   - Suspicious activity detection
   - Anomaly alerts
   - Extended audit logs

   Configuration:
   {
     "enableEnhancedSecurityMonitoring": true,
     "enableExNetworkLogging": true,
     "features": ["network_logging", "anomaly_detection"]
   }

3. Validation:
   - Verify standards are actively enforced
   - Check audit logs for compliance events
   - Review ESM alerts regularly

Current Status:
- CSP Enabled: {csp_enabled}
- Compliance Standards: {compliance_standards}
- ESM Enabled: {esm_enabled}
- Monitoring Level: {monitoring_level}

Documentation:
- https://docs.databricks.com/security/privacy/enhanced-security-compliance
- https://docs.databricks.com/security/privacy/enhanced-security-monitoring
```

**Benefits**:
- Compliance framework visibility
- Standard-specific validation
- Enforcement verification
- Better compliance reporting

**Implementation Complexity**: Medium
**Estimated Effort**: 3 days
**Backward Compatibility**: Yes (enhances existing checks)

---

## Medium Impact Modifications

### Modify-5: Check 61 (INFO-17) - Serverless Compute

**Current Check ID**: 61
**Category**: Informational (INFO-17)
**Current Severity**: Informational
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Current Implementation

**Current Logic**:
- Informational check: Is serverless enabled?
- No pass/fail criteria
- Simply reports status

**Current Recommendation**:
```
Serverless compute is available and can be enabled for SQL warehouses.
```

#### Enhancement

**Change from**: Informational observation
**Change to**: Positive recommendation (serverless preferred)

**Rationale**:
- Serverless is Databricks strategic direction
- Security benefits: Managed compute, automated patching, network policies
- Cost benefits: Auto-scaling, pay-per-use
- Operational benefits: No cluster management

**Enhanced Severity**: Low (recommendation, not requirement)

**Enhanced Recommendation**:
```
Serverless compute is recommended for security and operational benefits:

Security Advantages:
1. Managed Compute:
   - Databricks manages infrastructure
   - Automatic security patches
   - No cluster configuration vulnerabilities

2. Network Policies:
   - Serverless-specific egress controls
   - Built-in network isolation
   - Account-level policy enforcement

3. Reduced Attack Surface:
   - No direct cluster access
   - Automatic credential rotation
   - Hardened runtime environment

Operational Benefits:
- Auto-scaling (no capacity planning)
- Instant start (no cluster warmup)
- Pay-per-use (cost efficiency)

When to Use:
- SQL Analytics: Serverless SQL warehouses
- Notebooks: Serverless compute (preview)
- Apps: Serverless runtime
- Jobs: Migrating to serverless support

Migration Path:
1. Create serverless SQL warehouse
2. Test workloads for compatibility
3. Migrate users from classic warehouses
4. Configure network policies for production

Current Serverless Usage:
- SQL Warehouses: {serverless_warehouse_count}
- Total Warehouses: {total_warehouse_count}
- Adoption Rate: {adoption_percentage}%

Recommendation: Target 80%+ serverless adoption for security and efficiency.
```

**Benefits**:
- Aligns with Databricks strategy
- Drives security improvement (network policies)
- Reduces operational burden

**Implementation Complexity**: Low
**Estimated Effort**: 1 day

---

### Modify-6: Check 89 (NS-7) - Model Serving Endpoint Security

**Current Check ID**: 89
**Category**: Network Security (NS-7)
**Current Severity**: High
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Current Implementation

**Current Logic**:
- Checks if model serving endpoints have IP access lists OR Private Link
- Fails if neither configured

**Current SQL Query**:
```sql
SELECT
    endpoint_name,
    has_ip_access_list,
    has_private_link
FROM serving_endpoints
WHERE has_ip_access_list = false
  AND has_private_link = false
```

#### Enhancement

**Enhanced Logic**:
- Check IP access lists / Private Link (existing logic)
- **NEW**: Check AI Gateway guardrails configured
- **NEW**: Prioritize guardrails > network security

**Enhanced SQL Query**:
```sql
SELECT
    endpoint_name,
    has_ip_access_list,
    has_private_link,
    has_guardrails,
    guardrail_types,
    CASE
        WHEN has_guardrails AND (has_ip_access_list OR has_private_link) THEN 'FULLY_SECURED'
        WHEN has_guardrails THEN 'GUARDRAILS_ONLY'
        WHEN has_ip_access_list OR has_private_link THEN 'NETWORK_ONLY'
        ELSE 'UNSECURED'
    END as security_status
FROM serving_endpoints
WHERE security_status IN ('NETWORK_ONLY', 'UNSECURED')
```

**Enhanced Recommendation**:
```
Model serving endpoints require multiple layers of security:

1. AI Gateway Guardrails (HIGHEST PRIORITY):
   - PII detection and redaction
   - Safety filters (toxicity, hate speech)
   - Keyword blocking
   - Rate limiting

2. Network Security:
   - IP access lists (restrict to corporate network)
   - Private Link (private connectivity)

3. Authentication:
   - Token-based authentication
   - Service principal access
   - No anonymous access

Best Practice Security Layers:
✓ Guardrails + Private Link (maximum security)
✓ Guardrails + IP ACL (high security)
✓ Guardrails only (medium security, acceptable for internal)
✗ Network only (insufficient - no content protection)
✗ No security (unacceptable)

Current Status:
- Endpoint: {endpoint_name}
- Network Security: {has_ip_access_list or has_private_link}
- AI Guardrails: {has_guardrails}
- Recommendation: Add AI Gateway guardrails for content protection

Configuration:
{
  "ai_gateway": {
    "guardrails": {
      "input": {"pii": {"enabled": true, "behavior": "BLOCK"}},
      "output": {
        "pii": {"enabled": true, "behavior": "REDACT"},
        "safety": {"enabled": true, "threshold": 0.8}
      }
    }
  }
}
```

**Benefits**:
- Comprehensive AI security
- Aligns with AI Gateway features
- Addresses content security, not just network

**Implementation Complexity**: Low
**Estimated Effort**: 2 days

---

### Modify-7: Check 104 (INFO-38) - Third-Party Library Control

**Current Check ID**: 104
**Category**: Informational (INFO-38)
**Current Severity**: Informational
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Current Implementation

**Current Logic**:
- Binary check: Is artifact allowlist configured?
- Pass if allowlist exists

#### Enhancement

**Enhanced Logic**:
- Check allowlist configured (existing logic)
- **NEW**: Validate specific artifacts are allowed/blocked per policy
- **NEW**: Flag overly permissive allowlists

**Enhanced Recommendation**:
```
Third-party library control should enforce security policies:

1. Configure Artifact Allowlist:
   - Approved repositories: Maven Central, PyPI (curated)
   - Blocked repositories: Untrusted, deprecated
   - Internal repositories: Nexus, Artifactory

2. Validate Policy Enforcement:
   - Libraries from unapproved sources blocked
   - Known vulnerable packages blocked
   - Security scan results enforced

3. Example Policies:
   - Allow: org.apache.spark:*, com.company:*
   - Block: log4j:log4j:* (CVE-2021-44228)
   - Block: com.sun.*, sun.* (internal Java APIs)

Current Configuration:
- Allowlist Enabled: {enabled}
- Allowed Repositories: {allowed_repos}
- Blocked Artifacts: {blocked_artifacts}
```

**Implementation Complexity**: Low
**Estimated Effort**: 2 days

---

### Modify-8: Check 8 (GOV-3) - Log Delivery Configurations

**Current Check ID**: 8
**Category**: Governance (GOV-3)
**Current Severity**: High
**Cloud Support**: AWS ✓, Azure ✓, GCP ✓

#### Current Implementation

**Current Logic**:
- Checks if audit log delivery configured
- Fails if no log delivery

#### Enhancement

**Enhanced Logic**:
- Check audit log delivery (existing logic)
- **NEW**: Accept system tables (Check 105) as alternative
- **NEW**: Recommend system tables as modern approach

**Enhanced SQL Query**:
```sql
SELECT
    workspace_id,
    has_log_delivery,
    has_system_tables_enabled,
    CASE
        WHEN has_log_delivery OR has_system_tables_enabled THEN 'OK'
        ELSE 'NO_AUDIT_LOGS'
    END as status
FROM workspaces
WHERE status = 'NO_AUDIT_LOGS'
```

**Enhanced Recommendation**:
```
Audit logging can be configured via:

1. System Tables (RECOMMENDED - Modern):
   - Unity Catalog schema: system.access.audit
   - Real-time audit data
   - SQL queryable
   - No storage configuration needed
   - Enable: Workspace settings → System tables

2. Log Delivery (Legacy):
   - S3/ADLS/GCS bucket delivery
   - Batch export (hourly)
   - Requires storage configuration
   - Consider migrating to system tables

Best Practice: Enable both for redundancy
- System tables: Real-time monitoring
- Log delivery: Long-term archival

Current Status:
- Log Delivery: {has_log_delivery}
- System Tables: {has_system_tables_enabled}
- Recommendation: {recommendation}
```

**Implementation Complexity**: Low
**Estimated Effort**: 2 days

---

## Low Impact Modifications

### Modify-9: Check 28 (INFO-7) - Network Peering Detection

**Current Check ID**: 28
**Category**: Informational (INFO-7)
**Current Severity**: Informational

#### Enhancement

**Change from**: Manual documentation check
**Change to**: Automated detection via private_access_settings API

**Enhanced Logic**:
- Query private_access_settings
- Detect PrivateLink vs VPC/VNet peering
- Report connectivity method

**Implementation Complexity**: Low
**Estimated Effort**: 1 day

---

### Modify-10: Check 110 (NS-8) - Account Console IP Access Lists

**Current Check ID**: 110
**Category**: Network Security (NS-8)
**Current Severity**: Medium

#### Enhancement

**Enhanced Logic**:
- Check if IP ACL configured (existing logic)
- **NEW**: Validate lists are not overly permissive (0.0.0.0/0)
- **NEW**: Flag wildcard entries

**Implementation Complexity**: Low
**Estimated Effort**: 2 days

---

### Modify-11: Check 7 (GOV-2) - PAT Token Expiration

**Current Check ID**: 7
**Category**: Governance (GOV-2)
**Current Severity**: Medium

#### Enhancement

**Enhanced Logic**:
- Alert on tokens expiring within 7 days (existing logic)
- **NEW**: Add severity levels:
  - > 30 days: OK
  - 8-30 days: Warning
  - 1-7 days: High
  - Expired: Critical

**Implementation Complexity**: Low
**Estimated Effort**: 1 day

---

### Modify-12: Check 63 (GOV-24) - Legacy Global Init Scripts

**Current Check ID**: 63
**Category**: Governance (GOV-24)
**Current Severity**: Low

#### Enhancement

**Enhanced Logic**:
- Check if legacy scripts disabled (existing logic)
- **NEW**: Also check for scripts in /databricks/init (Check 64)
- **NEW**: Comprehensive legacy script detection

**Implementation Complexity**: Low
**Estimated Effort**: 1 day

---

## Implementation Summary

### By Impact Level

**High Impact** (4 modifications):
- Modify-1: UC metastore region validation (2 days)
- Modify-2: UC SHARED mode acceptance (1 day)
- Modify-3: SP usage validation (3 days)
- Modify-4: CSP/ESM standard validation (3 days)
- **Subtotal**: 9 days

**Medium Impact** (4 modifications):
- Modify-5: Serverless recommendation (1 day)
- Modify-6: AI Gateway guardrails (2 days)
- Modify-7: Artifact policy validation (2 days)
- Modify-8: System tables alternative (2 days)
- **Subtotal**: 7 days

**Low Impact** (4 modifications):
- Modify-9: Network peering detection (1 day)
- Modify-10: IP ACL validation (2 days)
- Modify-11: Token expiration severity (1 day)
- Modify-12: Legacy script consolidation (1 day)
- **Subtotal**: 5 days

**Total Estimated Effort**: 21 days (~4 weeks, 1 engineer)

### By Priority

**Priority 1 (Must Have)**:
- Modify-1, Modify-2, Modify-3, Modify-4
- Critical for compliance and security

**Priority 2 (Should Have)**:
- Modify-5, Modify-6, Modify-7, Modify-8
- Important for operational security

**Priority 3 (Nice to Have)**:
- Modify-9, Modify-10, Modify-11, Modify-12
- Incremental improvements

### Implementation Sequence

**Sprint 3** (with Medium Priority new checks):
1. Modify-2 (UC SHARED mode) - Low complexity, immediate value
2. Modify-11 (Token severity levels) - Low complexity
3. Modify-12 (Legacy script consolidation) - Low complexity

**Sprint 4** (with remaining Medium Priority checks):
4. Modify-1 (UC region validation) - High impact, data residency
5. Modify-3 (SP usage validation) - High impact, operational security
6. Modify-5 (Serverless recommendation) - Aligns with strategy

**Sprint 5** (with Cleanup phase):
7. Modify-4 (CSP/ESM standards) - Compliance reporting
8. Modify-6 (AI Gateway guardrails) - AI security
9. Modify-7 (Artifact policy validation) - Supply chain security
10. Modify-8 (System tables alternative) - Modern audit logging
11. Modify-9 (Network peering detection) - Automation
12. Modify-10 (IP ACL validation) - Network security

### Backward Compatibility

**All modifications maintain backward compatibility**:
- Existing pass/fail logic preserved
- Enhancements add validation layers
- No breaking changes to check IDs or categories
- CSV updates append new logic, don't replace

### Testing Strategy

1. **Unit Tests**: Add tests for new validation logic
2. **Integration Tests**: Run against test workspaces
3. **Regression Tests**: Ensure existing checks still pass
4. **Validation**: Compare results before/after modification

---

**End of Checks to Modify Specification**
