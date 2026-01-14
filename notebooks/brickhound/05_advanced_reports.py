# Databricks notebook source
# MAGIC %md
# MAGIC #Advanced Security Reports
# MAGIC *Comprehensive security analysis for Databricks environments*
# MAGIC
# MAGIC This notebook generates detailed security reports that don't require user input. These reports provide comprehensive views of your security posture:
# MAGIC
# MAGIC ## Reports Included
# MAGIC
# MAGIC ### 1. High Privilege Principals
# MAGIC Principals with minimal connections in the security graph. May be:
# MAGIC - Orphaned accounts that should be deprovisioned
# MAGIC - New users that need proper group assignments
# MAGIC - Service principals without proper access setup
# MAGIC
# MAGIC ### 2. Isolated Principals
# MAGIC Resources with no explicit permission grants - only accessible via ownership or inheritance. May indicate:
# MAGIC - Unused or forgotten resources
# MAGIC - Resources that need explicit access controls
# MAGIC - Potential security gaps
# MAGIC
# MAGIC ### 3. Orphaned Resources
# MAGIC Users with excessive permissions across the environment:
# MAGIC - ALL PRIVILEGES on multiple catalogs
# MAGIC - MANAGE permissions on many resources
# MAGIC - Broad access patterns that may indicate over-provisioning
# MAGIC
# MAGIC ### 4. Over-Privileged Principals
# MAGIC Principals with admin-level privileges (Account Admin, Metastore Admin, Workspace Admin, Catalog Owners):
# MAGIC - Direct role assignments
# MAGIC - Group membership (including nested groups)
# MAGIC - Direct permissions on admin resources
# MAGIC - Ownership of privileged resources
# MAGIC
# MAGIC ### 5. Secret Scope Access
# MAGIC Principals with access to secret scopes - who can read, write, or manage secrets
# MAGIC
# MAGIC ### 6. Summary Statistics
# MAGIC Overview of your security graph:
# MAGIC - Vertex and edge counts
# MAGIC - Permission grants by type
# MAGIC
# MAGIC ## Prerequisites
# MAGIC
# MAGIC Run `01_data_collection.py` first to populate the graph data.

# COMMAND ----------

# DBTITLE 1,Run Common Setup
# MAGIC %run ./00_analysis_common

# COMMAND ----------

# DBTITLE 1,Define Helper Constants
# These constants are used by the report queries
USER_SP_TYPES = ["User", "ServicePrincipal", "AccountUser", "AccountServicePrincipal"]

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC # Security Reports
# MAGIC
# MAGIC Run the cells below to generate comprehensive security reports for your environment.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Report 1: High Privilege Principals
# MAGIC
# MAGIC Principals with admin-level privileges via direct or nested group membership.
# MAGIC
# MAGIC **Privileged Roles:**
# MAGIC - **Account Admin**: Full control over the Databricks account
# MAGIC - **Metastore Admin**: Full control over Unity Catalog metastore
# MAGIC - **Workspace Admin**: Full control over a workspace
# MAGIC - **Catalog Owner**: Full control over a catalog and its objects
# MAGIC
# MAGIC This report uses graph traversal to find **effective** privileges through:
# MAGIC - Direct group membership to admin groups
# MAGIC - Nested group membership (up to 2 levels deep)
# MAGIC - Direct permissions (MANAGE on metastores)
# MAGIC - Ownership (catalog owners)

# COMMAND ----------

# DBTITLE 1,Find High Privilege Principals via Graph Traversal
print("=" * 70)
print("HIGH PRIVILEGE PRINCIPALS REPORT")
print("=" * 70)

# Graph traversal query to find effective admin privileges
high_privilege_query = f"""
WITH
-- Account Admins via direct AccountAdmin edge (from roles field in SCIM API)
-- This captures users/SPs with account_admin role directly assigned
account_admins_direct AS (
    SELECT DISTINCT
        v.id as principal_id,
        COALESCE(v.display_name, v.name, v.email) as principal_name,
        v.email as principal_email,
        v.node_type as principal_type,
        'Account Admin' as role,
        'Direct Role Assignment' as via,
        'Direct Role (account_admin)' as access_type
    FROM {EDGES_TABLE} e
    JOIN {VERTICES_TABLE} v ON (e.src = v.id OR e.src = v.email OR e.src = v.name)
    WHERE e.run_id = '{SELECTED_RUN_ID}'
      AND e.relationship = 'AccountAdmin'
      AND v.node_type IN ('User', 'ServicePrincipal', 'AccountUser', 'AccountServicePrincipal')
      AND v.run_id = '{SELECTED_RUN_ID}'
),

-- Level 1: Identify admin groups directly
-- Key distinction: Account-level 'admins' group = Account Admin
--                  Workspace-level 'admins' group = Workspace Admin
-- Use both node_type AND id prefix to identify (id prefix is more reliable)
admin_groups AS (
    SELECT id, name, node_type,
        CASE
            -- Account-level admins group (by node_type OR id prefix) or groups with 'account admin' in name
            WHEN ((node_type = 'AccountGroup' OR id LIKE 'account_group:%') AND LOWER(name) = 'admins')
                 OR LOWER(name) LIKE '%account%admin%' THEN 'Account Admin'
            WHEN LOWER(name) LIKE '%metastore%admin%' THEN 'Metastore Admin'
            -- Workspace-level admins group (not account-level) or groups with 'workspace admin' in name
            WHEN (node_type = 'Group' AND id NOT LIKE 'account_group:%' AND LOWER(name) = 'admins')
                 OR LOWER(name) LIKE '%workspace%admin%'
                 OR LOWER(name) = 'workspace admins' THEN 'Workspace Admin'
        END as admin_role
    FROM {VERTICES_TABLE}
    WHERE run_id = '{SELECTED_RUN_ID}'
      AND node_type IN ('Group', 'AccountGroup')
      AND (LOWER(name) = 'admins'
           OR LOWER(name) LIKE '%account%admin%'
           OR LOWER(name) LIKE '%metastore%admin%'
           OR LOWER(name) LIKE '%workspace%admin%'
           OR LOWER(name) = 'workspace admins')
),

-- Level 2: Groups that are members of admin groups (nested level 1)
nested_groups_l1 AS (
    SELECT g.id, g.name, g.node_type, ag.admin_role, ag.name as admin_group_name
    FROM {EDGES_TABLE} e
    JOIN {VERTICES_TABLE} g ON e.src = g.id
    JOIN admin_groups ag ON e.dst = ag.id
    WHERE e.run_id = '{SELECTED_RUN_ID}'
      AND e.relationship = 'MemberOf'
      AND g.node_type IN ('Group', 'AccountGroup')
      AND g.run_id = '{SELECTED_RUN_ID}'
),

-- Level 3: Groups that are members of nested groups (nested level 2)
nested_groups_l2 AS (
    SELECT g.id, g.name, g.node_type, ng.admin_role, ng.admin_group_name
    FROM {EDGES_TABLE} e
    JOIN {VERTICES_TABLE} g ON e.src = g.id
    JOIN nested_groups_l1 ng ON e.dst = ng.id
    WHERE e.run_id = '{SELECTED_RUN_ID}'
      AND e.relationship = 'MemberOf'
      AND g.node_type IN ('Group', 'AccountGroup')
      AND g.run_id = '{SELECTED_RUN_ID}'
),

-- All admin groups (direct + nested)
all_admin_groups AS (
    SELECT id, name, admin_role, name as via_group, 'Direct' as path_type FROM admin_groups
    UNION ALL
    SELECT id, name, admin_role, admin_group_name as via_group, 'Nested (L1)' as path_type FROM nested_groups_l1
    UNION ALL
    SELECT id, name, admin_role, admin_group_name as via_group, 'Nested (L2)' as path_type FROM nested_groups_l2
),

-- Principals in admin groups (direct or via nested groups)
principals_via_groups AS (
    SELECT DISTINCT
        v.id as principal_id,
        COALESCE(v.display_name, v.name, v.email) as principal_name,
        v.email as principal_email,
        v.node_type as principal_type,
        aag.admin_role as role,
        aag.name as via,
        CASE aag.path_type
            WHEN 'Direct' THEN 'Group Membership'
            ELSE CONCAT('Nested Group (', aag.path_type, ')')
        END as access_type
    FROM {EDGES_TABLE} e
    JOIN {VERTICES_TABLE} v ON (e.src = v.id OR e.src = v.email OR e.src = v.name)
    JOIN all_admin_groups aag ON e.dst = aag.id
    WHERE e.run_id = '{SELECTED_RUN_ID}'
      AND e.relationship = 'MemberOf'
      AND v.node_type IN ('User', 'ServicePrincipal', 'AccountUser', 'AccountServicePrincipal')
      AND v.run_id = '{SELECTED_RUN_ID}'
),

-- Metastore admins via direct permission
metastore_admins_direct AS (
    SELECT DISTINCT
        v.id as principal_id,
        COALESCE(v.display_name, v.name, v.email) as principal_name,
        v.email as principal_email,
        v.node_type as principal_type,
        'Metastore Admin' as role,
        m.name as via,
        'Direct Permission (MANAGE)' as access_type
    FROM {EDGES_TABLE} e
    JOIN {VERTICES_TABLE} v ON (e.src = v.id OR e.src = v.email OR e.src = v.name)
    JOIN {VERTICES_TABLE} m ON e.dst = m.id
    WHERE e.run_id = '{SELECTED_RUN_ID}'
      AND m.node_type = 'Metastore'
      AND e.permission_level IN ('MANAGE', 'ALL PRIVILEGES', 'ALL_PRIVILEGES', 'CAN_MANAGE')
      AND v.node_type IN ('User', 'ServicePrincipal', 'AccountUser', 'AccountServicePrincipal')
      AND v.run_id = '{SELECTED_RUN_ID}'
      AND m.run_id = '{SELECTED_RUN_ID}'
),

-- Catalog owners (have full control)
catalog_owners AS (
    SELECT DISTINCT
        v.id as principal_id,
        COALESCE(v.display_name, v.name, v.email) as principal_name,
        v.email as principal_email,
        v.node_type as principal_type,
        'Catalog Owner' as role,
        c.name as via,
        'Ownership' as access_type
    FROM {VERTICES_TABLE} c
    JOIN {VERTICES_TABLE} v ON (c.owner = v.id OR c.owner = v.email OR c.owner = v.name)
    WHERE c.run_id = '{SELECTED_RUN_ID}'
      AND c.node_type = 'Catalog'
      AND v.node_type IN ('User', 'ServicePrincipal', 'AccountUser', 'AccountServicePrincipal')
      AND v.run_id = '{SELECTED_RUN_ID}'
),

-- Catalog ALL PRIVILEGES holders
catalog_all_privileges AS (
    SELECT DISTINCT
        v.id as principal_id,
        COALESCE(v.display_name, v.name, v.email) as principal_name,
        v.email as principal_email,
        v.node_type as principal_type,
        'Catalog Owner' as role,
        c.name as via,
        'ALL PRIVILEGES' as access_type
    FROM {EDGES_TABLE} e
    JOIN {VERTICES_TABLE} v ON (e.src = v.id OR e.src = v.email OR e.src = v.name)
    JOIN {VERTICES_TABLE} c ON e.dst = c.id
    WHERE e.run_id = '{SELECTED_RUN_ID}'
      AND c.node_type = 'Catalog'
      AND e.permission_level IN ('ALL PRIVILEGES', 'ALL_PRIVILEGES')
      AND v.node_type IN ('User', 'ServicePrincipal', 'AccountUser', 'AccountServicePrincipal')
      AND v.run_id = '{SELECTED_RUN_ID}'
      AND c.run_id = '{SELECTED_RUN_ID}'
)

SELECT principal_id,
       CASE
           WHEN principal_email IS NOT NULL AND principal_email != '' AND LOWER(principal_name) != LOWER(principal_email)
           THEN CONCAT(principal_name, ' (', principal_email, ')')
           ELSE principal_name
       END as principal,
       principal_type, role, via, access_type
FROM (
    SELECT * FROM account_admins_direct
    UNION ALL
    SELECT * FROM principals_via_groups
    UNION ALL
    SELECT * FROM metastore_admins_direct
    UNION ALL
    SELECT * FROM catalog_owners
    UNION ALL
    SELECT * FROM catalog_all_privileges
)
ORDER BY
    CASE role
        WHEN 'Account Admin' THEN 1
        WHEN 'Metastore Admin' THEN 2
        WHEN 'Workspace Admin' THEN 3
        WHEN 'Catalog Owner' THEN 4
        ELSE 5
    END,
    principal
"""

high_privilege_principals = spark.sql(high_privilege_query)

# Summary
total_grants = high_privilege_principals.count()
unique_principals = high_privilege_principals.select("principal_id").distinct().count()
account_admins = high_privilege_principals.filter(F.col("role") == "Account Admin").select("principal_id").distinct().count()
metastore_admins = high_privilege_principals.filter(F.col("role") == "Metastore Admin").select("principal_id").distinct().count()
workspace_admins = high_privilege_principals.filter(F.col("role") == "Workspace Admin").select("principal_id").distinct().count()
catalog_owners = high_privilege_principals.filter(F.col("role") == "Catalog Owner").select("principal_id").distinct().count()

print(f"\n📊 SUMMARY")
print(f"   Unique High Privilege Principals: {unique_principals}")
print(f"   Total Privilege Grants: {total_grants}")
print(f"   👑 Account Admins: {account_admins}")
print(f"   🗄️ Metastore Admins: {metastore_admins}")
print(f"   🏢 Workspace Admins: {workspace_admins}")
print(f"   📚 Catalog Owners: {catalog_owners}")

# By role
print("\n📋 BY ROLE:")
display(high_privilege_principals.groupBy("role").agg(
    F.countDistinct("principal_id").alias("unique_principals"),
    F.count("*").alias("total_grants")
).orderBy(
    F.when(F.col("role") == "Account Admin", 1)
     .when(F.col("role") == "Metastore Admin", 2)
     .when(F.col("role") == "Workspace Admin", 3)
     .otherwise(4)
))

# By access type
print("\n🔗 BY ACCESS TYPE:")
display(high_privilege_principals.groupBy("access_type").count().orderBy(F.desc("count")))

# Account Admins (highest privilege - always show)
if account_admins > 0:
    print(f"\n👑 ACCOUNT ADMINS ({account_admins}):")
    display(high_privilege_principals.filter(F.col("role") == "Account Admin"))

# Metastore Admins
if metastore_admins > 0:
    print(f"\n🗄️ METASTORE ADMINS ({metastore_admins}):")
    display(high_privilege_principals.filter(F.col("role") == "Metastore Admin"))

print("\n🔐 ALL HIGH PRIVILEGE PRINCIPALS:")
display(high_privilege_principals)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Report 2: Isolated Principals
# MAGIC
# MAGIC Principals with minimal connections in the security graph. These may be:
# MAGIC - Orphaned accounts that should be deprovisioned
# MAGIC - New users that need proper group assignments
# MAGIC - Service principals without proper access setup

# COMMAND ----------

# DBTITLE 1,Find Isolated Principals
print("=" * 70)
print("ISOLATED PRINCIPALS REPORT")
print("=" * 70)

# Use the same SQL query as the app for consistency
isolated_query = f"""
WITH all_principals AS (
    SELECT id, name, email, application_id, node_type, display_name,
        -- Create a canonical key to identify the same logical principal across workspace/account levels
        CASE
            WHEN node_type IN ('User', 'AccountUser')
            THEN LOWER(COALESCE(email, name, id))
            WHEN node_type IN ('ServicePrincipal', 'AccountServicePrincipal')
            THEN LOWER(COALESCE(application_id, name, id))
            ELSE LOWER(COALESCE(name, id))
        END as principal_key
    FROM {VERTICES_TABLE}
    WHERE run_id = '{SELECTED_RUN_ID}'
      AND node_type IN ('User', 'ServicePrincipal', 'AccountUser', 'AccountServicePrincipal')
),
-- Count group memberships across ALL vertices with the same principal_key
group_memberships AS (
    SELECT
        p.principal_key,
        COUNT(DISTINCT e.dst) as group_count
    FROM all_principals p
    LEFT JOIN {EDGES_TABLE} e ON e.run_id = '{SELECTED_RUN_ID}'
        AND e.relationship = 'MemberOf'
        AND (e.src = p.id OR e.src = p.email OR e.src = p.name)
    GROUP BY p.principal_key
),
-- Count direct permissions across ALL vertices with the same principal_key
direct_permissions AS (
    SELECT
        p.principal_key,
        COUNT(DISTINCT e.dst) as permission_count
    FROM all_principals p
    LEFT JOIN {EDGES_TABLE} e ON e.run_id = '{SELECTED_RUN_ID}'
        AND e.permission_level IS NOT NULL
        AND (e.src = p.id OR e.src = p.email OR e.src = p.name)
    GROUP BY p.principal_key
),
-- Count owned resources across ALL vertices with the same principal_key
owned_resources AS (
    SELECT
        p.principal_key,
        COUNT(DISTINCT v.id) as owned_count
    FROM all_principals p
    LEFT JOIN {VERTICES_TABLE} v ON v.run_id = '{SELECTED_RUN_ID}'
        AND v.owner IS NOT NULL
        AND (v.owner = p.id OR v.owner = p.email OR v.owner = p.name)
    GROUP BY p.principal_key
),
-- Deduplicate to get one row per logical principal (prefer account-level)
principals AS (
    SELECT id, name, email, application_id, node_type, display_name, principal_key,
        ROW_NUMBER() OVER (
            PARTITION BY principal_key
            ORDER BY
                CASE node_type
                    WHEN 'AccountUser' THEN 1
                    WHEN 'User' THEN 2
                    WHEN 'AccountServicePrincipal' THEN 1
                    WHEN 'ServicePrincipal' THEN 2
                    ELSE 3
                END
        ) as rn
    FROM all_principals
)
SELECT
    p.id,
    CASE
        -- Users: show "Display Name (email)"
        WHEN p.node_type IN ('User', 'AccountUser') AND p.email IS NOT NULL AND p.email != '' AND COALESCE(p.display_name, p.name) != p.email
        THEN CONCAT(COALESCE(p.display_name, p.name), ' (', p.email, ')')
        -- SPs: show "Display Name (application_id)" if available
        WHEN p.node_type IN ('ServicePrincipal', 'AccountServicePrincipal') AND p.application_id IS NOT NULL AND COALESCE(p.display_name, p.name) != p.application_id
        THEN CONCAT(COALESCE(p.display_name, p.name), ' (', p.application_id, ')')
        ELSE COALESCE(p.display_name, p.name, p.email, p.application_id)
    END as name,
    p.email,
    p.application_id,
    p.node_type,
    COALESCE(gm.group_count, 0) as groups,
    COALESCE(dp.permission_count, 0) as permissions,
    COALESCE(o.owned_count, 0) as owned,
    (COALESCE(gm.group_count, 0) * 5 + COALESCE(dp.permission_count, 0) + COALESCE(o.owned_count, 0) * 2) as connectivity_score,
    CASE
        WHEN COALESCE(gm.group_count, 0) = 0 AND COALESCE(dp.permission_count, 0) = 0 AND COALESCE(o.owned_count, 0) = 0 THEN 'Highly Isolated'
        WHEN (COALESCE(gm.group_count, 0) * 5 + COALESCE(dp.permission_count, 0) + COALESCE(o.owned_count, 0) * 2) < 5 THEN 'Moderately Isolated'
        WHEN (COALESCE(gm.group_count, 0) * 5 + COALESCE(dp.permission_count, 0) + COALESCE(o.owned_count, 0) * 2) < 10 THEN 'Slightly Isolated'
        ELSE 'Well Connected'
    END as isolation_risk
FROM principals p
LEFT JOIN group_memberships gm ON p.principal_key = gm.principal_key
LEFT JOIN direct_permissions dp ON p.principal_key = dp.principal_key
LEFT JOIN owned_resources o ON p.principal_key = o.principal_key
WHERE p.rn = 1
ORDER BY connectivity_score ASC
"""

isolated_principals = spark.sql(isolated_query)

# Summary
print("\nIsolation Risk Summary:")
display(isolated_principals.groupBy("isolation_risk").count().orderBy(
    F.when(F.col("isolation_risk") == "Highly Isolated", 1)
     .when(F.col("isolation_risk") == "Moderately Isolated", 2)
     .when(F.col("isolation_risk") == "Slightly Isolated", 3)
     .otherwise(4)
))

print("\nMost Isolated Principals (investigate these):")
display(isolated_principals.filter(F.col("isolation_risk").isin(["Highly Isolated", "Moderately Isolated"])).limit(20))

print("\nAll Principal Connectivity Metrics:")
display(isolated_principals)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Report 3: Orphaned Resources
# MAGIC
# MAGIC Resources with no explicit permission grants (only accessible via ownership or inheritance).
# MAGIC These may indicate:
# MAGIC - Unused or forgotten resources
# MAGIC - Resources that need explicit access controls
# MAGIC - Potential security gaps

# COMMAND ----------

# DBTITLE 1,Find Orphaned Resources
print("=" * 70)
print("ORPHANED RESOURCES REPORT")
print("=" * 70)

# Use SecurityAnalyzer if available, otherwise use inline query
if analyzer:
    print("Using SecurityAnalyzer.find_orphaned_resources() (shared logic with app)")
    orphaned_resources = analyzer.find_orphaned_resources()
else:
    print("Using notebook-local query")
    orphaned_query = f"""
    WITH granted_resources AS (
        SELECT DISTINCT dst as resource_id
        FROM {EDGES_TABLE}
        WHERE permission_level IS NOT NULL
          AND run_id = '{SELECTED_RUN_ID}'
    )
    SELECT
        v.id,
        v.name,
        v.node_type,
        v.owner
    FROM {VERTICES_TABLE} v
    LEFT JOIN granted_resources gr ON v.id = gr.resource_id
    WHERE gr.resource_id IS NULL
      AND v.node_type IN ('Table', 'View', 'Schema', 'Catalog', 'Volume', 'Function')
      AND v.run_id = '{SELECTED_RUN_ID}'
    ORDER BY v.node_type, v.name
    """
    orphaned_resources = spark.sql(orphaned_query)

orphaned_count = orphaned_resources.count()

print(f"\nFound {orphaned_count} orphaned resources (no explicit grants)")

# Summary by type
print("\nBy Resource Type:")
display(orphaned_resources.groupBy("node_type").count().orderBy(F.desc("count")))

print("\nOrphaned Resources:")
display(orphaned_resources.limit(50))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Report 4: Over-Privileged Principals
# MAGIC
# MAGIC Principals with excessive permissions across the environment. Identifies users with:
# MAGIC - ALL PRIVILEGES on multiple catalogs
# MAGIC - MANAGE permissions on many resources
# MAGIC - Broad access patterns that may indicate over-provisioning

# COMMAND ----------

# DBTITLE 1,Find Over-Privileged Principals
print("=" * 70)
print("OVER-PRIVILEGED PRINCIPALS REPORT")
print("=" * 70)

# Use SecurityAnalyzer if available, otherwise use inline query
if analyzer:
    print("Using SecurityAnalyzer.find_over_privileged_principals() (shared logic with app)")
    over_privileged = analyzer.find_over_privileged_principals()
else:
    print("Using notebook-local query")
    over_privileged_query = f"""
    WITH all_principals AS (
        -- Get all user/SP principals with canonical key for deduplication
        SELECT
            id,
            name,
            email,
            application_id,
            node_type,
            display_name,
            CASE
                WHEN node_type IN ('User', 'AccountUser') THEN LOWER(COALESCE(email, name, id))
                WHEN node_type IN ('ServicePrincipal', 'AccountServicePrincipal') THEN LOWER(COALESCE(application_id, name, id))
                ELSE LOWER(COALESCE(name, id))
            END as principal_key
        FROM {VERTICES_TABLE}
        WHERE node_type IN ('User', 'ServicePrincipal', 'AccountUser', 'AccountServicePrincipal')
          AND run_id = '{SELECTED_RUN_ID}'
    ),
    permission_counts AS (
        -- Count permissions across ALL node variants with same principal_key
        SELECT
            p.principal_key,
            COUNT(DISTINCT e.dst) as total_resources,
            COUNT(DISTINCT CASE WHEN r.node_type = 'Catalog' THEN r.id END) as catalog_count,
            COUNT(DISTINCT CASE WHEN r.node_type = 'Schema' THEN r.id END) as schema_count,
            COUNT(DISTINCT CASE WHEN r.node_type = 'Table' THEN r.id END) as table_count,
            COUNT(DISTINCT CASE WHEN e.permission_level IN ('ALL PRIVILEGES', 'ALL_PRIVILEGES', 'MANAGE', 'CAN_MANAGE') THEN r.id END) as admin_grants,
            COLLECT_SET(DISTINCT e.permission_level) as permission_types
        FROM {EDGES_TABLE} e
        JOIN all_principals p ON (e.src = p.id OR e.src = p.email OR e.src = p.name)
        JOIN {VERTICES_TABLE} r ON e.dst = r.id AND r.run_id = '{SELECTED_RUN_ID}'
        WHERE e.permission_level IS NOT NULL
          AND e.run_id = '{SELECTED_RUN_ID}'
        GROUP BY p.principal_key
    ),
    deduplicated_principals AS (
        -- Keep one row per principal_key (prefer account-level nodes)
        SELECT
            id as principal_id,
            COALESCE(display_name, name) as principal_name,
            email as principal_email,
            node_type as principal_type,
            principal_key,
            ROW_NUMBER() OVER (
                PARTITION BY principal_key
                ORDER BY
                    CASE
                        WHEN node_type = 'AccountUser' THEN 1
                        WHEN node_type = 'User' THEN 2
                        WHEN node_type = 'AccountServicePrincipal' THEN 1
                        WHEN node_type = 'ServicePrincipal' THEN 2
                        ELSE 3
                    END
            ) as rn
        FROM all_principals
    )
    SELECT
        d.principal_id,
        CASE
            WHEN d.principal_email IS NOT NULL AND d.principal_email != '' AND LOWER(d.principal_name) != LOWER(d.principal_email)
            THEN CONCAT(d.principal_name, ' (', d.principal_email, ')')
            ELSE d.principal_name
        END as principal,
        d.principal_type,
        p.total_resources,
        p.catalog_count,
        p.schema_count,
        p.table_count,
        p.admin_grants,
        p.permission_types,
        CASE
            WHEN p.catalog_count >= 3 OR p.admin_grants >= 10 THEN 'HIGH'
            WHEN p.catalog_count >= 1 OR p.admin_grants >= 5 THEN 'MEDIUM'
            ELSE 'LOW'
        END as risk_level
    FROM deduplicated_principals d
    JOIN permission_counts p ON d.principal_key = p.principal_key
    WHERE d.rn = 1
      AND (p.admin_grants > 0 OR p.catalog_count > 0)
    ORDER BY p.admin_grants DESC, p.catalog_count DESC, p.total_resources DESC
    """
    over_privileged = spark.sql(over_privileged_query)

over_privileged_count = over_privileged.count()

print(f"\nFound {over_privileged_count} principals with elevated access")

# Summary by risk level
print("\nBy Risk Level:")
display(over_privileged.groupBy("risk_level").count().orderBy(
    F.when(F.col("risk_level") == "HIGH", 1)
     .when(F.col("risk_level") == "MEDIUM", 2)
     .otherwise(3)
))

print("\nHigh Risk Principals (investigate these):")
display(over_privileged.filter(F.col("risk_level") == "HIGH").limit(20))

print("\nAll Over-Privileged Principals:")
display(over_privileged)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Report 5: Secret Scope Access
# MAGIC
# MAGIC Principals with access to secret scopes - who can read, write, or manage secrets.
# MAGIC
# MAGIC **Permission Levels:**
# MAGIC - **MANAGE**: Full control - can read, write, and manage ACLs
# MAGIC - **WRITE**: Can read and write secrets
# MAGIC - **READ**: Can only read secrets

# COMMAND ----------

# DBTITLE 1,Find Secret Scope Access
print("=" * 70)
print("SECRET SCOPE ACCESS REPORT")
print("=" * 70)

secret_scope_query = f"""
WITH all_principals AS (
    SELECT
        id,
        name,
        email,
        application_id,
        node_type,
        display_name,
        CASE
            WHEN node_type IN ('User', 'AccountUser') THEN LOWER(COALESCE(email, name, id))
            WHEN node_type IN ('ServicePrincipal', 'AccountServicePrincipal') THEN LOWER(COALESCE(application_id, name, id))
            WHEN node_type IN ('Group', 'AccountGroup') THEN LOWER(COALESCE(name, id))
            ELSE LOWER(COALESCE(name, id))
        END as principal_key
    FROM {VERTICES_TABLE}
    WHERE run_id = '{SELECTED_RUN_ID}'
      AND node_type IN ('User', 'Group', 'ServicePrincipal', 'AccountUser', 'AccountGroup', 'AccountServicePrincipal')
),
secret_access AS (
    SELECT DISTINCT
        p.principal_key,
        s.name as scope_name,
        s.properties as scope_properties,
        e.permission_level,
        e.relationship
    FROM {EDGES_TABLE} e
    JOIN all_principals p ON (e.src = p.id OR e.src = p.email OR e.src = p.name)
    JOIN {VERTICES_TABLE} s ON e.dst = s.id AND s.run_id = '{SELECTED_RUN_ID}'
    WHERE e.run_id = '{SELECTED_RUN_ID}'
      AND s.node_type = 'SecretScope'
      AND e.permission_level IS NOT NULL
),
deduplicated_principals AS (
    SELECT
        id,
        COALESCE(display_name, name, email, application_id) as principal_name,
        email as principal_email,
        node_type as principal_type,
        principal_key,
        ROW_NUMBER() OVER (
            PARTITION BY principal_key
            ORDER BY
                CASE
                    WHEN node_type = 'AccountUser' THEN 1
                    WHEN node_type = 'User' THEN 2
                    WHEN node_type = 'AccountGroup' THEN 1
                    WHEN node_type = 'Group' THEN 2
                    WHEN node_type = 'AccountServicePrincipal' THEN 1
                    WHEN node_type = 'ServicePrincipal' THEN 2
                    ELSE 3
                END
        ) as rn
    FROM all_principals
)
SELECT
    d.id as principal_id,
    d.principal_name,
    d.principal_email,
    d.principal_type,
    sa.scope_name,
    sa.scope_properties,
    sa.permission_level,
    sa.relationship
FROM secret_access sa
JOIN deduplicated_principals d ON sa.principal_key = d.principal_key AND d.rn = 1
ORDER BY
    CASE d.principal_type
        WHEN 'User' THEN 1
        WHEN 'AccountUser' THEN 1
        WHEN 'Group' THEN 2
        WHEN 'AccountGroup' THEN 2
        WHEN 'ServicePrincipal' THEN 3
        WHEN 'AccountServicePrincipal' THEN 3
        ELSE 4
    END,
    d.principal_name,
    sa.scope_name
"""

secret_scope_access = spark.sql(secret_scope_query)

# Summary
total_grants = secret_scope_access.count()
unique_scopes = secret_scope_access.select("scope_name").distinct().count()
unique_users = secret_scope_access.filter(F.col("principal_type").isin(['User', 'AccountUser'])).select("principal_id").distinct().count()
unique_groups = secret_scope_access.filter(F.col("principal_type").isin(['Group', 'AccountGroup'])).select("principal_id").distinct().count()
unique_sps = secret_scope_access.filter(F.col("principal_type").isin(['ServicePrincipal', 'AccountServicePrincipal'])).select("principal_id").distinct().count()

print(f"\n📊 SUMMARY")
print(f"   Secret Scopes: {unique_scopes}")
print(f"   Total Access Grants: {total_grants}")
print(f"   Users with Access: {unique_users}")
print(f"   Groups with Access: {unique_groups}")
print(f"   Service Principals with Access: {unique_sps}")

# By permission level
print("\n📋 ACCESS BY PERMISSION LEVEL:")
display(secret_scope_access.groupBy("permission_level").count().orderBy(F.desc("count")))

# By principal type
print("\n👥 ACCESS BY PRINCIPAL TYPE:")
display(secret_scope_access.groupBy("principal_type").count().orderBy(F.desc("count")))

# MANAGE permissions (highest risk)
manage_count = secret_scope_access.filter(F.col("permission_level") == "MANAGE").count()
if manage_count > 0:
    print(f"\n🟣 PRINCIPALS WITH MANAGE ACCESS ({manage_count}):")
    display(secret_scope_access.filter(F.col("permission_level") == "MANAGE"))

print("\n🔐 ALL SECRET SCOPE ACCESS:")
display(secret_scope_access)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Report 6: Summary Statistics
# MAGIC
# MAGIC Overview of your security graph data.

# COMMAND ----------

# DBTITLE 1,Graph Statistics Summary
print("=" * 70)
print("BRICKHOUND SECURITY GRAPH SUMMARY")
print("=" * 70)

# Total counts
total_vertices = vertices.count()
total_edges = edges.count()
print(f"\nTotal Vertices: {total_vertices:,}")
print(f"Total Edges: {total_edges:,}")

# Vertex counts by type
print("\n" + "-" * 50)
print("VERTICES BY TYPE")
print("-" * 50)
display(vertices.groupBy("node_type").count().orderBy(F.desc("count")))

# Edge counts by relationship
print("\n" + "-" * 50)
print("EDGES BY RELATIONSHIP")
print("-" * 50)
display(edges.groupBy("relationship").count().orderBy(F.desc("count")))

# Permission grants by type
print("\n" + "-" * 50)
print("PERMISSION GRANTS BY TYPE")
print("-" * 50)
display(edges.filter(F.col("permission_level").isNotNull())
    .groupBy("permission_level")
    .count()
    .orderBy(F.desc("count")))

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC ## Next Steps
# MAGIC
# MAGIC 1. **Review findings** from the reports above
# MAGIC 2. **Investigate** any concerning access patterns
# MAGIC 3. **Remediate** issues like orphaned resources or over-privileged accounts
# MAGIC 4. **Schedule** regular scans using Databricks Jobs
# MAGIC
# MAGIC ## Recommended Actions
# MAGIC
# MAGIC **For Orphaned Resources:**
# MAGIC - Review owner field to determine resource owner
# MAGIC - Grant explicit permissions or archive unused resources
# MAGIC - Consider implementing naming conventions for easier tracking
# MAGIC
# MAGIC **For Isolated Principals:**
# MAGIC - Deprovision highly isolated accounts that are no longer needed
# MAGIC - Assign proper group memberships for new users
# MAGIC - Validate service principal configurations
# MAGIC
# MAGIC **For Over-Privileged Principals:**
# MAGIC - Review business justification for broad access
# MAGIC - Implement least privilege by removing unnecessary permissions
# MAGIC - Consider role-based access control (RBAC) via groups
# MAGIC
# MAGIC **For High Privilege Principals:**
# MAGIC - Validate all admin accounts have business justification
# MAGIC - Enable MFA for all admin users
# MAGIC - Monitor admin activity closely
# MAGIC - Review nested group memberships
# MAGIC - Rotate credentials frequently
# MAGIC
# MAGIC **For Secret Scope Access:**
# MAGIC - Ensure only necessary principals have secret access
# MAGIC - Review MANAGE permissions carefully (highest risk)
# MAGIC - Consider migrating to Unity Catalog external locations
# MAGIC - Implement secret rotation policies
