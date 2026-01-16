# SAT Security Gap Analysis - Implementation Plan

**Version**: 1.0
**Date**: 2026-01-16
**Duration**: 6 sprints (12 weeks)
**Team Size**: 2-3 engineers

---

## Executive Summary

This implementation plan outlines a phased approach to enhance SAT with 35+ new security checks, 12 check modifications, and 3 deprecations, increasing coverage from 77 to 112+ checks over 6 two-week sprints.

### Key Milestones

| Sprint | Focus Area | New Checks | Modifications | Effort (days) |
|--------|------------|------------|---------------|---------------|
| 1-2 | UC & AI Security | 15 checks | 2 mods | 35 days |
| 3-4 | Serverless & Apps | 11 checks | 5 mods | 30 days |
| 5 | System Tables & Cleanup | 6 checks | 5 mods | 15 days |
| 6 | Final Enhancements | 3 checks | 0 mods | 10 days |
| **Total** | **All Categories** | **35 checks** | **12 mods** | **90 days** |

---

## Sprint 1-2: High-Priority Security (Weeks 1-4)

### Focus: Unity Catalog Fine-Grained Security & AI/ML Security

**Objective**: Address the most critical gaps in UC and AI security

#### Sprint 1 (Week 1-2)

**Unity Catalog Checks (8 checks, 18 days)**

1. **UC-1: Row-Level Security Filters** (3 days)
   - Client method: `get_table_details_with_filters()`
   - Bootstrap: UC tables with filter metadata
   - SQL query: Filter tables without row filters
   - Test: Validate on tables with/without filters

2. **UC-2: Column Masking Policies** (3 days)
   - Client method: `get_table_column_masks()`
   - Bootstrap: Table columns with mask metadata
   - SQL query: Filter PII columns without masks
   - Test: Validate SSN, email, credit card columns

3. **UC-3: ABAC Policies Deployed** (5 days - HIGH COMPLEXITY)
   - **BLOCKER**: API endpoint needs verification
   - Client method: `get_abac_policies()`
   - Bootstrap: ABAC policy configurations
   - SQL query: Count policies by tag
   - **Risk**: API may be preview, needs investigation

4. **UC-4: External Location Security** (2 days)
   - Client method: `get_external_locations_with_credentials()`
   - Bootstrap: External locations
   - SQL query: Filter locations without storage credentials
   - Test: Validate S3/ADLS/GCS locations

5. **UC-5: Storage Credential Scope** (4 days)
   - Client method: `get_storage_credentials_with_scope()`
   - Bootstrap: Storage credentials with IAM policies
   - SQL query: Parse IAM policies for wildcard access
   - Test: Validate AWS IAM, Azure RBAC, GCP IAM scoping
   - **Complexity**: IAM policy parsing logic

#### Sprint 2 (Week 3-4)

**Remaining UC + AI Security Checks (11 checks, 17 days)**

6. **UC-6: Catalog/Schema Ownership** (2 days)
   - SQL query: Filter user-owned vs group-owned

7. **UC-7: Table Lineage Tracking** (2 days)
   - Client method: `get_table_lineage()`
   - SQL query: Tables without lineage data

8. **UC-8: Volume Security Configuration** (3 days)
   - Client method: `get_volumes_with_permissions()`
   - SQL query: Volumes with world-readable permissions

**AI/ML Security (7 checks, 12 days)**

9. **AI-1: Model Serving Guardrails** (4 days)
   - Client method: `get_endpoint_guardrails()`
   - Bootstrap: Serving endpoints with guardrail config
   - SQL query: Endpoints without PII/safety filters
   - Test: Validate AI Gateway configuration

10. **AI-2: Model Serving Authentication** (2 days)
    - SQL query: Endpoints with anonymous access

11. **AI-3: Inference Table Logging** (2 days)
    - SQL query: Endpoints without auto_capture_config

12. **AI-4: Foundation Model Rate Limits** (2 days)
    - SQL query: External model endpoints without rate limits

13. **AI-5: Vector Search Endpoint Security** (2 days)
    - Client method: `list_vector_search_endpoints()`
    - SQL query: Endpoints without IP ACLs/Private Link

**Modifications (2 modifications, 2 days)**

- **Modify-2**: UC SHARED mode acceptance (1 day)
  - Update Check 17 SQL query
  - Test on SHARED mode clusters

- **Modify-11**: Token expiration severity levels (1 day)
  - Update Check 7 rule function
  - Add tiered severity logic

#### Sprint 1-2 Deliverables

- **8 UC checks** implemented and tested
- **5 AI checks** implemented and tested (AI-6, AI-7 in Sprint 3)
- **2 check modifications** deployed
- **Unit tests** for new client methods
- **Integration tests** on test workspace
- **Updated CSV**: 15 new rows in `security_best_practices.csv`
- **Documentation**: Check specifications, API usage

#### Sprint 1-2 Risks

| Risk | Mitigation |
|------|------------|
| ABAC API unavailable | Defer to Sprint 3, investigate alternatives |
| IAM policy parsing complexity | Use JSON libraries, test on all clouds |
| AI Gateway config varies by model type | Comprehensive testing, flexible validation |

---

## Sprint 3-4: Serverless & Modern Features (Weeks 5-8)

### Focus: Serverless Network Security, Git, Apps, Secrets

#### Sprint 3 (Week 5-6)

**Serverless Network Security (4 checks, 11 days)**

1. **SLS-1: Network Policies Configured** (5 days - HIGH COMPLEXITY)
   - **BLOCKER**: Network policies API not in MCP tools
   - New client: `NetworkPoliciesClient`
   - Client method: `get_network_policies()`
   - Bootstrap: Account-level network policies
   - SQL query: Check for default policy only
   - **Risk**: API may be preview or unavailable
   - **Action**: Research API availability first week of sprint

2. **SLS-2: Workspace Policy Assignment** (3 days)
   - Client method: `list_workspace_policy_assignments()`
   - SQL query: Production workspaces without custom policies
   - Test: Validate workspace-policy mapping

3. **SLS-3: Egress Restrictions** (2 days)
   - SQL query: Parse network policy rules for wildcards
   - Test: Validate allow/deny rule logic

4. **SLS-4: Serverless SQL Warehouse Security** (1 day)
   - SQL query: Join serverless warehouses with workspace policies
   - Test: Validate on serverless vs classic warehouses

**Git Security (3 checks, 5 days)**

5. **GIT-1: Git URL Allowlist** (2 days)
   - Client method: `get_git_url_allowlist()`
   - SQL query: Workspaces without allowlist enforcement

6. **GIT-2: Git Restriction Mode** (1 day)
   - SQL query: Query workspace-conf for restriction settings

7. **GIT-3: Bitbucket Auth Migration** (2 days)
   - Bootstrap: Git repos with credential types
   - SQL query: Bitbucket repos with app passwords

**AI Security Remaining (2 checks, 4 days)**

8. **AI-6: Model Registry UC Migration** (2 days)
   - Client methods: UC models API + workspace models API
   - SQL query: Production models in workspace registry

9. **AI-7: MLflow Experiment Permissions** (2 days)
   - SQL query: Experiments with "all users" permissions

#### Sprint 4 (Week 7-8)

**Databricks Apps Security (4 checks, 9 days)**

10. **APP-1: Apps Use Service Principals** (3 days)
    - New client: `AppsClient` (or enhance existing)
    - Client method: `list_apps_with_service_principals()`
    - Bootstrap: Apps with SP assignments
    - SQL query: Apps without service_principal_id

11. **APP-2: Apps Enforce SSO** (2 days)
    - SQL query: Apps allowing OTP authentication

12. **APP-3: Apps Not Publicly Accessible** (2 days)
    - Client method: `get_app_permissions()`
    - SQL query: Apps with anonymous access

13. **APP-4: App Permission Boundaries** (2 days)
    - SQL query: Apps with overly broad permissions

**Secrets Management (2 checks, 5 days)**
- **Note**: SEC-2 (Secrets Not in Notebooks) is redundant with TruffleHog

14. **SEC-1: External Secret Stores** (2 days)
    - SQL query: Production scopes with backend_type='DATABRICKS'

15. **SEC-3: Secrets Not in Init Scripts** (3 days)
    - Bootstrap: Init scripts with content scanning
    - SQL query: Scripts without dbutils.secrets.get()

**Modifications (5 modifications, 7 days)**

- **Modify-1**: UC metastore region validation (2 days)
- **Modify-3**: SP usage validation (3 days)
- **Modify-5**: Serverless recommendation (1 day)
- **Modify-12**: Legacy script consolidation (1 day)

#### Sprint 3-4 Deliverables

- **11 new checks** implemented (serverless, Git, Apps, secrets)
- **5 check modifications** deployed
- **Network policies client** created (if API available)
- **Apps client** created or enhanced
- **Unit tests** for all new checks
- **Updated CSV**: 11 new rows
- **Documentation**: Serverless security guide, Apps security guide

#### Sprint 3-4 Risks

| Risk | Mitigation |
|------|------------|
| Network policies API unavailable | Mark checks as "preview", implement when GA |
| Apps API inconsistent | Flexible validation, handle missing fields |
| Secret scanning performance impact | Limit to global init scripts, not all notebooks |

---

## Sprint 5: System Tables & Cleanup (Weeks 9-10)

### Focus: Monitoring, Deprecations, Remaining Modifications

#### System Tables & Monitoring (3 checks, 6 days)

1. **SYS-1: Automated Security Monitoring** (2 days)
   - SQL query: Jobs querying system.access.audit

2. **SYS-2: Audit Log Retention** (2 days)
   - Client method: `get_metastore_system_schema_config()`
   - SQL query: Retention policies

3. **SYS-3: Alert Destinations** (2 days)
   - Client method: `list_notification_destinations()`
   - SQL query: Security-related destinations

#### Check Deprecations (3 days)

1. **Remove-1: Table ACL (Check 20)** (1 day)
   - Add conditional logic (skip for UC workspaces)
   - Update recommendation with deprecation warning

2. **Remove-2: Legacy Init Scripts (Checks 63-65)** (2 days)
   - Create consolidated Check 146
   - Mark 63, 64, 65 as deprecated in CSV
   - Update YAML with deprecation flags

3. **Remove-3: HTTP Headers (Checks 46-48)** (0.5 day)
   - Update recommendations (informational only)
   - Downgrade priority in YAML

#### Remaining Modifications (5 modifications, 6 days)

- **Modify-4**: CSP/ESM standard validation (3 days)
- **Modify-6**: AI Gateway guardrails (2 days)
- **Modify-7**: Artifact policy validation (2 days)
- **Modify-8**: System tables alternative (2 days)
- **Modify-9**: Network peering detection (1 day)
- **Modify-10**: IP ACL validation (2 days)
  - **Note**: Some overlap, can be parallelized

#### Sprint 5 Deliverables

- **3 new checks** (system tables monitoring)
- **1 consolidated check** (Check 146)
- **5 check modifications** deployed
- **3 deprecations** implemented
- **Updated CSV**: Deprecation flags, consolidated check
- **Updated YAML**: Enable/disable flags
- **Documentation**: Deprecation FAQ, migration guides

---

## Sprint 6: Final Enhancements & Polish (Weeks 11-12)

### Focus: Additional Enhancements, Testing, Documentation

#### Additional Enhancements (3 checks, 6 days)

1. **ENH-1: Workspace Encryption Status** (2 days)
   - Client method: `get_workspace_encryption_config()`
   - SQL query: Workspaces without CMK

2. **ENH-2: Cluster Policy Inheritance** (2 days)
   - SQL query: Clusters without policy_id

3. **ENH-3: Job Owner is Service Principal** (2 days)
   - SQL query: Production jobs owned by users

#### Comprehensive Testing (4 days)

1. **Integration Testing** (2 days)
   - Run full SAT analysis on test workspace
   - Validate all 112+ checks execute
   - Compare results before/after enhancements

2. **Performance Testing** (1 day)
   - Measure execution time impact
   - Optimize slow queries
   - Test on large workspaces (1000+ clusters, 10000+ tables)

3. **Regression Testing** (1 day)
   - Ensure existing checks still pass
   - Validate backward compatibility
   - Test on AWS, Azure, GCP

#### Documentation & Release Prep (4 days)

1. **User Documentation** (2 days)
   - Update README.md with new checks
   - Create check catalog with all 112+ checks
   - Migration guides for deprecated checks

2. **Developer Documentation** (1 day)
   - API integration guide
   - Client package patterns
   - Testing guide

3. **Release Notes** (1 day)
   - Comprehensive change log
   - Breaking changes (deprecations)
   - Migration instructions

#### Sprint 6 Deliverables

- **3 enhancement checks** implemented
- **Comprehensive test suite** passing
- **Performance optimizations** applied
- **Complete documentation** updated
- **Release candidate** ready for deployment
- **Rollback plan** documented

---

## Dependencies & Prerequisites

### External Dependencies

1. **Databricks APIs**
   - Unity Catalog API (2.1) ✅ Available
   - Serving Endpoints API (2.0) ✅ Available
   - Vector Search API (2.0) ✅ Available
   - Apps API (2.0) ✅ Available
   - Settings v2 API (2.0) ✅ Available
   - **Network Policies API** ❓ Needs verification

2. **Feature Availability**
   - Unity Catalog row filters ✅ GA
   - Unity Catalog column masks ✅ GA
   - AI Gateway guardrails ✅ GA (Q4 2024)
   - Serverless network policies ✅ GA (Jan 2025)
   - **ABAC policies** ❓ Preview/GA status unclear

### Internal Dependencies

1. **SDK Updates**
   - New client packages: `NetworkPoliciesClient`, `AppsClient`
   - Enhanced clients: `UnityC atalogClient`, `ServingEndpointsClient`
   - Version bump: 0.0.124 → 0.1.0 (minor version)

2. **Database Schema**
   - New intermediate tables for UC metadata, AI configs
   - No breaking changes to existing tables

3. **Configuration Files**
   - `security_best_practices.csv`: +35 rows
   - `self_assessment_checks.yaml`: +35 entries
   - No breaking changes

---

## Resource Allocation

### Team Structure

**Option 1: 2 Engineers** (Recommended)
- Engineer 1: UC & AI checks (complex logic)
- Engineer 2: Serverless, Apps, modifications (straightforward)
- Pair programming on complex items (ABAC, network policies)

**Option 2: 3 Engineers** (Accelerated)
- Engineer 1: Unity Catalog (8 checks)
- Engineer 2: AI/ML + Serverless (11 checks)
- Engineer 3: Apps, Git, Secrets, Modifications (16 items)
- **Timeline**: 4 sprints instead of 6

### Effort Distribution

| Phase | New Checks | Modifications | Testing | Documentation | Total Days |
|-------|------------|---------------|---------|---------------|------------|
| Sprint 1-2 | 25 days | 2 days | 5 days | 3 days | 35 days |
| Sprint 3-4 | 20 days | 7 days | 3 days | 0 days | 30 days |
| Sprint 5 | 6 days | 6 days | 2 days | 1 day | 15 days |
| Sprint 6 | 6 days | 0 days | 4 days | 4 days | 14 days |
| **Total** | **57 days** | **15 days** | **14 days** | **8 days** | **94 days** |

**With 2 Engineers**: 94 days / 2 = 47 working days = ~10 weeks
**With 3 Engineers**: 94 days / 3 = 31 working days = ~7 weeks

---

## Risk Management

### High-Risk Items

| Risk | Impact | Probability | Mitigation | Owner |
|------|--------|-------------|------------|-------|
| Network policies API unavailable | High | Medium | Defer to later sprint, mark as preview | Eng 2 |
| ABAC API not GA | Medium | Medium | Skip or implement as preview feature | Eng 1 |
| Performance degradation | High | Low | Optimize queries, add caching, pagination | Both |
| Cloud-specific API differences | Medium | Medium | Test on all 3 clouds early | Both |
| IAM policy parsing complexity | Medium | Low | Use existing libraries, limit scope | Eng 1 |

### Mitigation Strategies

1. **API Availability Issues**
   - Research API status in Sprint 1 week 1
   - Have backup plans for preview APIs
   - Document workarounds

2. **Performance Issues**
   - Profile queries early
   - Implement pagination for large datasets
   - Add caching for frequently accessed metadata
   - Parallelize independent checks

3. **Testing Challenges**
   - Create dedicated test workspaces on all clouds
   - Populate with diverse configurations
   - Automate test data setup

4. **Timeline Slippage**
   - Build 20% buffer into estimates
   - Prioritize high-impact checks
   - Defer low-priority items if needed

---

## Success Criteria

### Quantitative Metrics

1. **Coverage**
   - ✅ 112+ total checks (target: 112)
   - ✅ 95%+ cloud parity (AWS/Azure/GCP)
   - ✅ All high-priority checks implemented

2. **Quality**
   - ✅ 100% unit test coverage for new checks
   - ✅ < 5% false positive rate
   - ✅ Zero regression failures

3. **Performance**
   - ✅ < 10% increase in total execution time
   - ✅ < 5 minutes for full workspace analysis (1000 clusters)

4. **Adoption**
   - ✅ 90%+ checks enabled by default
   - ✅ < 5 support tickets per sprint post-deployment

### Qualitative Metrics

1. **User Satisfaction**
   - Clear, actionable recommendations
   - Comprehensive coverage of modern Databricks features
   - Aligned with industry frameworks (NIST, CIS, DASF)

2. **Code Quality**
   - Consistent patterns across checks
   - Well-documented APIs
   - Maintainable test suite

3. **Documentation Quality**
   - Complete API reference
   - Migration guides for deprecated checks
   - Clear remediation instructions

---

## Post-Implementation

### Maintenance Plan

**Quarterly Reviews** (Q2, Q3, Q4 2026):
- Review new Databricks features
- Assess check relevance
- Update for API changes
- Customer feedback integration

**Annual Updates** (2027):
- Complete removal of deprecated checks
- Alignment with updated frameworks (NIST CSF, CIS Benchmark)
- Performance optimization
- Cloud-specific enhancements

### Monitoring

**Check Health Metrics**:
- Execution success rate per check
- False positive rate tracking
- Execution time per check
- Cloud-specific failure patterns

**Customer Metrics**:
- Check adoption rates
- Violation trends over time
- Support ticket analysis
- Feature requests

### Continuous Improvement

**Feedback Loops**:
- Monthly check review meetings
- Customer advisory board input
- Databricks field feedback
- Industry best practice updates

---

## Appendix: Sprint Capacity Planning

### Assumptions

- **Sprint duration**: 2 weeks (10 working days)
- **Engineer capacity**: 8 hours/day (80% dev time = 6.4 hours)
- **Effective days per sprint**: 8 days (accounting for meetings, reviews)

### Sprint 1-2 Breakdown (2 engineers, 4 weeks)

**Total capacity**: 2 engineers × 8 days/sprint × 2 sprints = 32 engineer-days

**Planned work**: 35 days
- UC checks: 18 days
- AI checks: 12 days
- Modifications: 2 days
- Testing/docs: 3 days

**Buffer**: 3 days deficit (acceptable with focused execution)

### Sprint 3-4 Breakdown (2 engineers, 4 weeks)

**Total capacity**: 32 engineer-days

**Planned work**: 30 days
- Serverless: 11 days
- Git/Apps/Secrets: 14 days
- Modifications: 7 days
- Testing: 3 days

**Buffer**: 2 days surplus (use for spillover from Sprint 1-2)

### Sprint 5-6 Breakdown (2 engineers, 4 weeks)

**Total capacity**: 32 engineer-days

**Planned work**: 29 days
- Sprint 5: 15 days
- Sprint 6: 14 days

**Buffer**: 3 days surplus (use for polish, documentation)

**Total Project**: 94 days of work / 2 engineers = 47 working days ≈ 10 weeks ✅

---

**End of Implementation Plan**
