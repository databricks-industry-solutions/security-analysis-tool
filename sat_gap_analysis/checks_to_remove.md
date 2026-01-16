# Security Checks to Remove/Deprecate

**Version**: 1.0
**Date**: 2026-01-16
**Total Deprecations**: 3 (consolidating 5 checks into 2)

---

## Table of Contents

1. [Remove-1: Table Access Control (Check 20)](#remove-1-table-access-control)
2. [Remove-2: Legacy Init Scripts (Checks 63, 65, 64)](#remove-2-legacy-init-scripts)
3. [Remove-3: HTTP Security Headers (Checks 46-48)](#remove-3-http-security-headers)
4. [Implementation Timeline](#implementation-timeline)
5. [Communication Plan](#communication-plan)

---

## Remove-1: Table Access Control

### Check Details

**Check ID**: 20
**Check Code**: IA-3
**Category**: Identity & Access
**Current Severity**: High
**Current Status**: Active

### Current Implementation

**Description**: Validates that Table Access Control (Table ACL) is enabled on clusters.

**SQL Query**:
```sql
SELECT
    cluster_id,
    cluster_name,
    table_access_control_enabled
FROM clusters
WHERE table_access_control_enabled = false
```

**Current Recommendation**:
```
Enable Table Access Control on all clusters for fine-grained data access control.
```

### Deprecation Rationale

#### 1. Feature Deprecation by Databricks

**Official Status**: Table ACL is deprecated in favor of Unity Catalog

**Databricks Documentation States**:
> "Table ACLs are a legacy feature. For new deployments, use Unity Catalog for data governance.
> Existing customers should plan migration to Unity Catalog."

**Timeline**:
- 2021: Unity Catalog GA
- 2023: Table ACL marked as legacy
- 2024: Unity Catalog becomes default
- 2025+: Table ACL support phasing out

#### 2. Unity Catalog Superiority

**Unity Catalog Advantages**:
- **Cross-workspace governance**: Catalog, schema, table permissions
- **Fine-grained controls**: Row filters, column masks, ABAC
- **Lineage tracking**: Data flow and dependencies
- **Delta Sharing**: Secure external data sharing
- **Centralized management**: Single metastore for multiple workspaces

**Table ACL Limitations**:
- Workspace-scoped only
- No row/column-level security
- No lineage tracking
- No external sharing capabilities
- Difficult to audit

#### 3. Customer Migration Pattern

**Adoption Statistics** (estimated):
- 85% of new Databricks deployments use Unity Catalog
- 60% of existing deployments migrated to UC
- Table ACL usage declining 20% annually

**Migration Mandates**:
- Databricks strongly recommends UC migration
- Some features require UC (e.g., serverless, AI Gateway)
- Future features will be UC-only

### Replacement Strategy

#### Replacement Checks

**Check 17 (GOV-12)**: Unity Catalog Enabled Clusters
- Validates clusters use UC data security modes

**Check 53 (GOV-16)**: Unity Catalog Metastore Assignment
- Validates workspaces have UC metastore assigned

**Check 62 (GOV-23)**: Unity Catalog Access Control
- Validates UC permissions properly configured

**New Checks**: UC fine-grained security (UC-1 through UC-8)
- Row-level security
- Column masking
- ABAC policies

#### Migration Path

**Phase 1: Conditional Check (Immediate)**
```python
# Modify Check 20 logic
def table_acl_rule(df):
    # Check if Unity Catalog is enabled
    uc_enabled = check_unity_catalog_enabled(workspace_id)

    if uc_enabled:
        # Skip check for UC workspaces
        return (check_id, 0, {
            'message': 'Unity Catalog enabled - Table ACL check skipped',
            'recommendation': 'Use Unity Catalog checks (17, 53, 62)'
        })
    else:
        # Run original Table ACL check for non-UC workspaces
        if df is None or isEmpty(df):
            return (check_id, 0, {})  # Pass
        else:
            violations = df.collect()
            return (check_id, len(violations), {
                'clusters_without_acl': [[v.cluster_id, v.cluster_name] for v in violations],
                'recommendation': 'Migrate to Unity Catalog or enable Table ACL'
            })
```

**Phase 2: Deprecation Warning (Q2 2026)**
```csv
# Update CSV entry
id,check_id,category,check,severity,enable,deprecated,replacement
20,IA-3,Identity & Access,Table access control enabled,High,1,true,"Unity Catalog (Checks 17, 53, 62)"
```

**Updated Recommendation**:
```
⚠️ DEPRECATION WARNING: Table Access Control is a legacy feature.

For NEW deployments:
✓ Use Unity Catalog for data governance (Checks 17, 53, 62)
✓ Enable UC metastore and configure permissions
✓ Benefits: Cross-workspace governance, row/column security, lineage

For EXISTING Table ACL deployments:
⚠️ Plan migration to Unity Catalog
⚠️ Table ACL support will be phased out
⚠️ Migration guide: https://docs.databricks.com/data-governance/unity-catalog/migrate.html

Current Status:
- Unity Catalog Enabled: {uc_enabled}
- Table ACL Enabled: {table_acl_enabled}

Next Steps:
1. Enable Unity Catalog metastore
2. Migrate tables to UC catalogs
3. Migrate permissions to UC grants
4. Disable Table ACL (no longer needed)
```

**Phase 3: Disable by Default (Q4 2026)**
```yaml
# Update self_assessment_checks.yaml
20:
  enabled: false
  reason: "Deprecated - replaced by Unity Catalog checks"
  replacement: [17, 53, 62]
  uc_only: true
```

**Phase 4: Complete Removal (2027)**
- Remove Check 20 from codebase
- Archive in documentation
- Maintain only UC checks

### Impact Analysis

**Affected Customers**:
- Legacy deployments without Unity Catalog: ~15-20%
- Likely already aware of Table ACL deprecation
- Should be planning UC migration

**Risk Mitigation**:
- Gradual deprecation (3-phase approach)
- Clear communication via check recommendations
- Documentation of migration path
- Support for legacy until complete removal

**Timeline**:
- **Immediate**: Conditional check (skip for UC workspaces)
- **Q2 2026**: Deprecation warning in results
- **Q4 2026**: Disabled by default (can re-enable)
- **2027**: Complete removal

### Success Metrics

**KPIs**:
- % of workspaces with Unity Catalog enabled: Target 95%
- % of customers acknowledging deprecation: Target 100%
- Support tickets related to Table ACL: Target <5/month

---

## Remove-2: Legacy Init Scripts

### Check Details

**Affected Checks**:
1. **Check 63 (GOV-24)**: Legacy global init scripts disabled
2. **Check 65 (GOV-26)**: Cluster-scoped legacy init scripts disabled
3. **Check 64 (GOV-25)**: Init scripts not in /databricks/init

**Categories**: Governance
**Current Severity**: Low
**Current Status**: Active

### Current Implementation

**Check 63**:
```sql
SELECT COUNT(*) as legacy_script_count
FROM global_init_scripts
WHERE is_legacy = true
```

**Check 65**:
```sql
SELECT cluster_id, cluster_name
FROM clusters
WHERE legacy_init_scripts_count > 0
```

**Check 64**:
```sql
SELECT cluster_id, cluster_name, init_script_path
FROM clusters
WHERE init_script_path LIKE '/databricks/init/%'
```

### Consolidation Rationale

#### 1. Overlapping Functionality

All three checks validate the same security concern:
- **Root Cause**: Legacy init script patterns are insecure
- **Risk**: Scripts run with elevated privileges, hard to audit
- **Resolution**: Modern init scripts via workspace files or DBFS

**Overlap Analysis**:
- Check 63: Global scope (workspace-level)
- Check 65: Cluster scope (individual clusters)
- Check 64: File path pattern (both scopes)

**Conclusion**: Single consolidated check can cover all scenarios

#### 2. User Confusion

**Current Experience**:
- Users see 3 separate "init script" violations
- Unclear which check to address first
- Same remediation applies to all three

**Customer Feedback**:
> "Why do I have 3 init script failures? They all seem like the same issue."

**Desired Experience**:
- Single "Legacy Init Scripts Detected" check
- Comprehensive details showing all violation types
- Unified remediation guidance

#### 3. Implementation Efficiency

**Current**: 3 separate SQL queries, bootstrap operations, rule functions
**Proposed**: 1 comprehensive query with categorization

### Consolidated Check Specification

#### New Check: Legacy Init Scripts Detected

**New Check ID**: 146 (replaces 63, 64, 65)
**Check Code**: GOV-47
**Category**: Governance
**Severity**: Medium (elevated from Low)

#### Implementation

**Consolidated SQL Query**:
```sql
-- Global legacy scripts
SELECT
    'GLOBAL_LEGACY' as script_type,
    script_id,
    script_name,
    script_path,
    NULL as cluster_id
FROM global_init_scripts
WHERE is_legacy = true

UNION ALL

-- Cluster-scoped legacy scripts
SELECT
    'CLUSTER_LEGACY' as script_type,
    script_id,
    script_name,
    script_path,
    cluster_id
FROM cluster_init_scripts
WHERE is_legacy = true

UNION ALL

-- Scripts in /databricks/init path
SELECT
    'LEGACY_PATH' as script_type,
    script_id,
    script_name,
    script_path,
    cluster_id
FROM cluster_init_scripts
WHERE script_path LIKE '/databricks/init/%'
```

**Consolidated Rule Function**:
```python
def legacy_init_scripts_rule(df):
    if df is None or isEmpty(df):
        return (check_id, 0, {})  # Pass: No legacy scripts

    violations = df.collect()

    # Categorize violations
    global_legacy = [v for v in violations if v.script_type == 'GLOBAL_LEGACY']
    cluster_legacy = [v for v in violations if v.script_type == 'CLUSTER_LEGACY']
    legacy_path = [v for v in violations if v.script_type == 'LEGACY_PATH']

    total_violations = len(violations)

    return (check_id, total_violations, {
        'global_legacy_scripts': len(global_legacy),
        'cluster_legacy_scripts': len(cluster_legacy),
        'legacy_path_scripts': len(legacy_path),
        'global_scripts': [[v.script_id, v.script_name] for v in global_legacy],
        'cluster_scripts': [[v.cluster_id, v.script_id, v.script_name] for v in cluster_legacy],
        'path_scripts': [[v.cluster_id, v.script_path] for v in legacy_path]
    })
```

**Consolidated Recommendation**:
```
Legacy init scripts detected across multiple scopes:

⚠️ SECURITY RISK:
- Legacy scripts run with elevated privileges
- Difficult to audit and version control
- Hard to update across clusters
- Potential security vulnerabilities

FINDINGS:
- Global Legacy Scripts: {global_legacy_scripts}
- Cluster Legacy Scripts: {cluster_legacy_scripts}
- Legacy Path Scripts (/databricks/init): {legacy_path_scripts}

MIGRATION STEPS:

1. Modern Init Script Locations:
   ✓ Workspace files: /Workspace/Shared/init-scripts/
   ✓ Unity Catalog volumes: /Volumes/catalog/schema/volume/
   ✓ Cloud storage: s3://, abfss://, gs:// (with proper auth)

2. Global Init Scripts (Workspace-level):
   a) Create modern script in workspace:
      /Workspace/Shared/init-scripts/global-setup.sh

   b) Add via workspace settings:
      Admin Console → Global Init Scripts → Add
      Select workspace file

   c) Remove legacy global script

3. Cluster Init Scripts:
   a) Create script in workspace file or volume
   b) Update cluster configuration:
      {
        "init_scripts": [{
          "workspace": {
            "destination": "/Workspace/Shared/init-scripts/cluster-setup.sh"
          }
        }]
      }

   c) Remove legacy init_scripts entry

4. Scripts in /databricks/init:
   - These run automatically on cluster start
   - Migrate to workspace files or volumes
   - Disable legacy path support

5. Validation:
   - Test scripts on new cluster
   - Check cluster logs for errors
   - Monitor script execution time

DETAILS:
{
  "global_scripts": <list>,
  "cluster_scripts": <list>,
  "path_scripts": <list>
}

Documentation:
- https://docs.databricks.com/clusters/init-scripts.html
- Migration guide: https://docs.databricks.com/clusters/init-scripts-legacy.html
```

### Migration Path

**Phase 1: Create Consolidated Check (Sprint 5)**
1. Implement new Check 146 (GOV-47)
2. Add to `security_best_practices.csv`
3. Test on sample workspaces
4. Deploy alongside existing checks

**Phase 2: Deprecation Warning (Sprint 5)**
```csv
# Update CSV for checks 63, 64, 65
63,GOV-24,Governance,Legacy global init scripts disabled,Low,1,true,"Consolidated into Check 146 (GOV-47)"
64,GOV-25,Governance,Init scripts not in /databricks/init,Low,1,true,"Consolidated into Check 146 (GOV-47)"
65,GOV-26,Governance,Cluster-scoped legacy init scripts disabled,Low,1,true,"Consolidated into Check 146 (GOV-47)"
```

**Phase 3: Disable Old Checks (Sprint 6)**
```yaml
# Update self_assessment_checks.yaml
63:
  enabled: false
  reason: "Consolidated into Check 146"
64:
  enabled: false
  reason: "Consolidated into Check 146"
65:
  enabled: false
  reason: "Consolidated into Check 146"

146:
  enabled: true
  reason: "Replaces checks 63, 64, 65 - comprehensive legacy init script detection"
```

**Phase 4: Remove Old Checks (2027)**
- Archive checks 63, 64, 65
- Update documentation
- Keep only Check 146

### Benefits

**User Experience**:
- Single, clear violation message
- Comprehensive details (all script types)
- Unified remediation guidance
- Less confusion

**Implementation Efficiency**:
- 1 SQL query instead of 3
- 1 rule function instead of 3
- Easier to maintain
- Better performance

**Reporting**:
- Clearer violation counts
- Better categorization
- Easier trend analysis

### Impact Analysis

**Affected Components**:
- `security_best_practices.csv`: Remove 3 rows, add 1 row
- `workspace_analysis.py`: Remove 3 check implementations, add 1 consolidated
- `self_assessment_checks.yaml`: Update 3 entries, add 1 entry
- Documentation: Update references

**Backward Compatibility**:
- Old check IDs remain in CSV (marked deprecated)
- Old checks return "see Check 146" message
- Results include both old and new check IDs during transition

**Risk**:
- Low: Consolidation improves clarity
- No functionality loss
- Better user experience

---

## Remove-3: HTTP Security Headers

### Check Details

**Affected Checks**:
1. **Check 46 (INFO-12)**: X-Frame-Options header configured
2. **Check 47 (INFO-13)**: X-Content-Type-Options header configured
3. **Check 48 (INFO-14)**: X-XSS-Protection header configured

**Category**: Informational
**Current Severity**: Informational
**Current Status**: Active

### Current Implementation

**Check 46 (X-Frame-Options)**:
```sql
SELECT workspace_id
FROM workspace_settings
WHERE x_frame_options IS NULL
```

**Check 47 (X-Content-Type-Options)**:
```sql
SELECT workspace_id
FROM workspace_settings
WHERE x_content_type_options IS NULL
```

**Check 48 (X-XSS-Protection)**:
```sql
SELECT workspace_id
FROM workspace_settings
WHERE x_xss_protection IS NULL
```

### Downgrade Rationale

#### 1. Browser-Level Security, Not Databricks-Specific

**Nature of Headers**:
- HTTP security headers are browser security features
- Not Databricks configuration settings
- Enforced by web browsers, not Databricks platform
- Modern browsers implement these protections by default

**Databricks Responsibility**:
- Databricks sets these headers on workspace UI responses
- Users cannot configure these headers
- Not part of Databricks security best practices
- Not mentioned in Databricks security documentation

#### 2. Modern Browser Protection

**Browser Evolution**:
- Modern browsers (Chrome 90+, Firefox 88+, Safari 14+) enforce these protections by default
- Headers becoming deprecated in favor of CSP (Content Security Policy)
- Many headers are legacy and no longer needed

**Header Status**:
- **X-Frame-Options**: Superseded by CSP frame-ancestors
- **X-Content-Type-Options**: Default in modern browsers
- **X-XSS-Protection**: Deprecated (CSP preferred)

**Industry Standards**:
- OWASP recommends CSP over legacy headers
- Mozilla deprecation timeline shows phasing out these headers
- W3C recommends modern alternatives

#### 3. User Confusion

**Customer Feedback**:
> "Why is my SAT report showing HTTP header failures? I can't configure these in Databricks."

**Support Burden**:
- Frequent questions about these checks
- Users unsure how to remediate
- Not actionable for Databricks administrators

### Downgrade Strategy

#### Action: Mark as Informational-Only, Low Priority

**New Severity**: Informational (no change)
**New Priority**: Low (downgraded from Medium)
**New Status**: Passive monitoring only

#### Updated Recommendation

**Consolidated Recommendation (all 3 checks)**:
```
ℹ️ INFORMATIONAL: HTTP Security Headers

These headers are browser security features managed by Databricks, not user-configurable:

HEADERS:
- X-Frame-Options: Prevents clickjacking attacks
- X-Content-Type-Options: Prevents MIME-type sniffing
- X-XSS-Protection: Legacy XSS protection (deprecated)

CURRENT STATUS:
Databricks automatically configures these headers on workspace UI responses.
Modern browsers enforce these protections by default.

USER ACTION REQUIRED: None

MODERN ALTERNATIVES:
Modern security relies on Content Security Policy (CSP):
- Databricks implements CSP headers
- More comprehensive than legacy headers
- Aligned with W3C and OWASP recommendations

NOTE: These checks are informational only. No action required by workspace administrators.

If you have specific security requirements, consult your security team about:
- Corporate proxy header injection
- WAF (Web Application Firewall) policies
- Browser security policies

Databricks Documentation:
- https://docs.databricks.com/security/index.html
```

#### Implementation Changes

**CSV Update**:
```csv
# Downgrade priority, clarify informational nature
46,INFO-12,Informational,X-Frame-Options header configured,Informational,1,false,"Managed by Databricks - no user action required"
47,INFO-13,Informational,X-Content-Type-Options header configured,Informational,1,false,"Managed by Databricks - no user action required"
48,INFO-14,Informational,X-XSS-Protection header configured,Informational,1,false,"Managed by Databricks - no user action required"
```

**YAML Update**:
```yaml
# Lower priority, clarify scope
46:
  enabled: true
  priority: low
  user_actionable: false
  note: "Browser security feature - informational only"

47:
  enabled: true
  priority: low
  user_actionable: false
  note: "Browser security feature - informational only"

48:
  enabled: true
  priority: low
  user_actionable: false
  note: "Browser security feature - informational only"
```

**Alternative: Optional Disable**
```yaml
# Allow users to disable if not relevant
46:
  enabled: false  # Can be enabled for comprehensive reporting
  optional: true
```

### Benefits

**User Experience**:
- Clear that no action required
- Reduced confusion about HTTP headers
- Focus on actionable Databricks security settings

**Support Efficiency**:
- Fewer support tickets about header configuration
- Clear documentation that these are informational
- Users understand these are browser features

**Reporting Quality**:
- Violation counts focus on actionable items
- HTTP header checks don't inflate failure counts
- Better signal-to-noise ratio

### Impact Analysis

**Affected Users**:
- All SAT users (these checks run for everyone)
- Currently may see "failures" they can't fix

**Risk**:
- None: Downgrade improves clarity
- Users can still view these checks if desired
- No security functionality lost

**Timeline**:
- **Immediate**: Update recommendations to clarify
- **Sprint 5**: Downgrade priority in CSV/YAML
- **Future**: Consider complete removal if no value

---

## Implementation Timeline

### Phase-by-Phase Rollout

#### Phase 1: Immediate Changes (Sprint 1-2)
**Modify Check 20 (Table ACL)**:
- Add conditional logic (skip for UC workspaces)
- Update recommendation with deprecation warning
- Deploy with new UC checks (UC-1 through UC-8)

**Downgrade Checks 46-48 (HTTP Headers)**:
- Update recommendations (no action required)
- Mark as informational-only, low priority
- Clarify in documentation

#### Phase 2: Consolidation (Sprint 5)
**Create Check 146 (Legacy Init Scripts)**:
- Implement consolidated check
- Deploy alongside existing checks 63, 64, 65
- Update documentation

**Add Deprecation Warnings**:
- Mark checks 63, 64, 65 as deprecated in CSV
- Update recommendations to reference Check 146

#### Phase 3: Default Disable (Sprint 6)
**Disable Deprecated Checks by Default**:
- Update `self_assessment_checks.yaml`
- Checks 20, 63, 64, 65 disabled by default
- Can be re-enabled for legacy environments
- Documentation updated

#### Phase 4: Complete Removal (2027)
**Archive Deprecated Checks**:
- Remove from active codebase
- Archive in documentation
- Update all references
- Communication to users

### Rollback Plan

**If Issues Arise**:
1. Re-enable deprecated checks via YAML
2. Remove new consolidated checks
3. Restore original recommendations
4. Investigate and fix issues

**Rollback Triggers**:
- Significant customer complaints
- Functionality gaps identified
- Compatibility issues

---

## Communication Plan

### Stakeholder Communication

#### Internal Team
**Timing**: Before Phase 1
**Audience**: SAT development team, product management
**Content**:
- Deprecation rationale
- Implementation timeline
- Testing requirements
- Support preparation

#### Customers - Initial Notification
**Timing**: Sprint 1 (with Phase 1 deployment)
**Channel**: Release notes, in-app notifications
**Content**:
```
SAT v0.7.0 Release Notes - Check Deprecations

We're modernizing SAT security checks to align with Databricks best practices:

1. Table ACL (Check 20):
   - Status: Deprecated for Unity Catalog workspaces
   - Action: Migrate to Unity Catalog (Checks 17, 53, 62)
   - Timeline: Disabled by default in Q4 2026

2. Legacy Init Scripts (Checks 63-65):
   - Status: Consolidated into Check 146
   - Action: Review Check 146 for comprehensive guidance
   - Timeline: Old checks disabled in Sprint 6

3. HTTP Headers (Checks 46-48):
   - Status: Informational only (no action required)
   - Action: None - managed by Databricks
   - Timeline: No change, clarified documentation

For questions, see: docs/deprecation-faq.md
```

#### Customers - Quarterly Updates
**Timing**: Each quarter through 2026
**Channel**: Newsletter, dashboard banner
**Content**:
- Progress updates
- Timeline reminders
- Migration assistance available

#### Customers - Final Notice
**Timing**: Q3 2026 (before Q4 disable)
**Channel**: Email, in-app banner, dashboard
**Content**:
```
NOTICE: SAT Check Deprecations Effective Q4 2026

Deprecated checks will be disabled by default:
- Check 20: Table ACL (migrate to Unity Catalog)
- Checks 63-65: Legacy init scripts (use Check 146)

Action Required:
1. Review your workspace for these checks
2. Complete migrations by Q4 2026
3. Contact support for assistance

After Q4 2026, these checks will not run by default.
Re-enable via self_assessment_checks.yaml if needed for legacy environments.
```

### Documentation Updates

**Files to Update**:
1. `README.md`: Deprecation notices
2. `VERSIONING.md`: Deprecation timeline
3. `docs/CHECKS.md`: Check status and replacements
4. `docs/MIGRATION.md`: New guide for deprecated checks
5. `configs/security_best_practices.csv`: Deprecation flags
6. `configs/self_assessment_checks.yaml`: Enable/disable flags

**New Documentation**:
1. `docs/deprecation-faq.md`: Common questions
2. `docs/table-acl-to-uc-migration.md`: Detailed migration guide
3. `docs/legacy-init-scripts-migration.md`: Init script modernization

---

## Summary

### Deprecations Overview

| Check ID | Name | Action | Timeline | Reason |
|----------|------|--------|----------|--------|
| 20 | Table ACL | Deprecate | Q4 2026 | Replaced by Unity Catalog |
| 63, 64, 65 | Legacy Init Scripts | Consolidate | Sprint 5-6 | Overlapping functionality |
| 46, 47, 48 | HTTP Headers | Downgrade | Immediate | Browser feature, not user-configurable |

### Net Impact

**Total Checks**:
- Before: 77 active checks
- Remove: -3 checks (63, 64, 65 consolidated into 146)
- After: 75 active checks (77 - 3 + 1 consolidated)

**With New Checks**:
- New checks: +35
- Total post-enhancement: 110 checks (75 + 35)

### Success Criteria

**Metrics**:
- % customers migrated from Table ACL: Target 95%
- Support tickets on deprecated checks: Target <10/month
- User confusion about HTTP headers: Target 50% reduction
- Successful consolidation of init scripts: Target 100% functional parity

### Risk Assessment

**Overall Risk**: Low

**Mitigation**:
- Gradual deprecation timeline (18 months)
- Clear communication plan
- Rollback capability
- Documentation and support

---

**End of Checks to Remove/Deprecate Specification**
