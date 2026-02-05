# Databricks notebook source
# MAGIC %md
# MAGIC # Principal & Resource Access Analysis
# MAGIC *Interactive security queries for principals and resources*
# MAGIC
# MAGIC <div style="background-color: #fff3e0; border-left: 4px solid #d32f2f; padding: 12px; margin: 16px 0;">
# MAGIC   <p style="margin: 0; font-size: 0.85em; color: #d32f2f; font-weight: bold;">⚠️ DISCLAIMER</p>
# MAGIC   <p style="margin: 8px 0 0 0; font-size: 0.8em; color: #555;">
# MAGIC     This tool may have incomplete data. Outputs are visibility and audit aids, not authoritative compliance determinations.
# MAGIC   </p>
# MAGIC </div>
# MAGIC
# MAGIC This notebook provides two core security analyses:
# MAGIC
# MAGIC ## 1. Principal Access Analysis
# MAGIC **Question:** What resources can a specific user, group, or service principal access?
# MAGIC
# MAGIC Analyzes comprehensive access patterns including:
# MAGIC - **Direct grants**: Explicit permissions assigned to the principal
# MAGIC - **Group membership**: Access inherited from group memberships (including nested groups)
# MAGIC - **Ownership**: Resources owned by the principal (full control)
# MAGIC - **Parent inheritance**: Access to child resources via parent permissions
# MAGIC
# MAGIC **Use cases:**
# MAGIC - User offboarding: What will a user lose access to?
# MAGIC - Access reviews: What can this service principal access?
# MAGIC - Security audits: Is this user over-privileged?
# MAGIC
# MAGIC ## 2. Resource Access Analysis
# MAGIC **Question:** Who has access to a specific resource (catalog, schema, table, etc.)?
# MAGIC
# MAGIC Identifies all principals with access to a resource:
# MAGIC - Direct permission grants
# MAGIC - Group-based access
# MAGIC - Ownership
# MAGIC
# MAGIC **Use cases:**
# MAGIC - Data classification: Who can access sensitive tables?
# MAGIC - Access reviews: Should everyone have access to this catalog?
# MAGIC - Incident response: Who could have accessed this resource?
# MAGIC
# MAGIC ## Prerequisites
# MAGIC
# MAGIC Run `/notebooks/permission_analysis_data_collection.py` first to populate the graph data.

# COMMAND ----------

# DBTITLE 1,Run Common Setup
# MAGIC %run ./00_analysis_common

# COMMAND ----------

# DBTITLE 1,SDK Status Check
if not analyzer:
    print("⚠️  WARNING: Running in FALLBACK mode (simplified analysis)")
    print("   For full-featured analysis, ensure SDK is loaded in 00_analysis_common")
    print("   Results will be incomplete (no group expansion, no parent inheritance)")
    print()

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC # Interactive Analysis
# MAGIC
# MAGIC Use the widgets below to run security queries.

# COMMAND ----------

# DBTITLE 1,Configure Analysis
# Create widgets for interactive analysis
dbutils.widgets.dropdown("analysis_type", "Principal Access", ["Principal Access", "Resource Access"])
dbutils.widgets.text("identifier", "", "Principal or Resource")

# COMMAND ----------

# DBTITLE 1,Helper Functions
# Define helper functions for when SecurityAnalyzer is not available

PRINCIPAL_TYPES = ["User", "Group", "ServicePrincipal", "AccountUser", "AccountGroup", "AccountServicePrincipal"]
USER_SP_TYPES = ["User", "ServicePrincipal", "AccountUser", "AccountServicePrincipal"]
GROUP_TYPES = ["Group", "AccountGroup"]

def find_principal(identifier):
    """Find a principal by ID, email, or name."""
    result = vertices.filter(
        (F.col("id") == identifier) |
        (F.col("email") == identifier) |
        (F.col("name") == identifier) |
        (F.col("display_name") == identifier)
    ).filter(
        F.col("node_type").isin(PRINCIPAL_TYPES)
    ).first()
    return result

def find_resource(identifier):
    """Find a resource by ID or name."""
    result = vertices.filter(
        (F.col("id") == identifier) |
        (F.col("name") == identifier) |
        (F.col("display_name") == identifier)
    ).filter(
        ~F.col("node_type").isin(PRINCIPAL_TYPES)
    ).first()
    return result

def get_principal_groups(principal_id, principal_email=None, principal_name=None):
    """Get all groups a principal belongs to (including nested)."""
    if principal_email is None or principal_name is None:
        principal_info = vertices.filter(F.col("id") == principal_id).first()
        if principal_info:
            principal_email = principal_info.email
            principal_name = principal_info.name

    id_variants = [principal_id]
    if ':' in str(principal_id):
        id_variants.append(principal_id.split(':')[-1])
    else:
        id_variants.extend([f"account_user:{principal_id}", f"account_group:{principal_id}", f"account_sp:{principal_id}"])

    id_conditions = F.col("src") == id_variants[0]
    for vid in id_variants[1:]:
        id_conditions = id_conditions | (F.col("src") == vid)
    if principal_email:
        id_conditions = id_conditions | (F.col("src") == principal_email)
    if principal_name:
        id_conditions = id_conditions | (F.col("src") == principal_name)

    direct = edges.filter(
        id_conditions & (F.col("relationship") == "MemberOf")
    ).alias("e").join(
        vertices.filter(F.col("node_type").isin(GROUP_TYPES))
            .select(F.col("id"), F.col("name").alias("group_name")).alias("g"),
        (F.col("e.dst") == F.col("g.id")) | (F.col("e.dst") == F.col("g.group_name"))
    ).select(
        F.col("g.id").alias("group_id"),
        F.col("g.group_name").alias("group_name"),
        F.col("g.group_name").alias("inheritance_path"),
        F.lit(0).alias("depth")
    ).distinct()

    all_groups = direct
    current_level = direct

    for i in range(10):
        nested = edges.filter(F.col("relationship") == "MemberOf").alias("e2").join(
            current_level.alias("cl"),
            (F.col("e2.src") == F.col("cl.group_id")) | (F.col("e2.src") == F.col("cl.group_name"))
        ).join(
            vertices.filter(F.col("node_type").isin(GROUP_TYPES))
                .select(F.col("id").alias("parent_id"), F.col("name").alias("parent_name")).alias("pg"),
            (F.col("e2.dst") == F.col("pg.parent_id")) | (F.col("e2.dst") == F.col("pg.parent_name"))
        ).select(
            F.col("pg.parent_id").alias("group_id"),
            F.col("pg.parent_name").alias("group_name"),
            F.concat(F.col("cl.inheritance_path"), F.lit(" -> "), F.col("pg.parent_name")).alias("inheritance_path"),
            F.lit(i + 1).alias("depth")
        ).distinct()

        if nested.count() == 0:
            break
        all_groups = all_groups.union(nested)
        current_level = nested

    return all_groups.select("group_id", "group_name", "inheritance_path", "depth").distinct()


def get_principal_access(principal_identifier, resource_type=None):
    """Get all resources a principal can access with effective permissions."""
    principal = find_principal(principal_identifier)
    if not principal:
        print(f"Principal '{principal_identifier}' not found")
        return None

    p_id = principal["id"]
    p_email = principal["email"] or ""
    p_name = principal["name"] or ""

    print(f"Analyzing access for: {format_principal_name(principal['display_name'], principal['email'], principal['name'], p_id)}")
    print(f"  Type: {principal['node_type']}")

    p_id_variants = [p_id]
    if ':' in str(p_id):
        p_id_variants.append(p_id.split(':')[-1])
    else:
        p_id_variants.extend([f"account_user:{p_id}", f"account_group:{p_id}", f"account_sp:{p_id}"])

    all_groups_df = get_principal_groups(p_id, p_email, p_name)
    all_groups = all_groups_df.collect()
    group_paths = {row["group_id"]: row["inheritance_path"] for row in all_groups}
    group_name_paths = {row["group_name"]: row["inheritance_path"] for row in all_groups}
    group_ids = list(group_paths.keys())
    group_names = list(group_name_paths.keys())

    print(f"  Member of {len(group_ids)} groups")

    type_filter = f"AND v.node_type = '{resource_type}'" if resource_type else ""
    id_conditions = ' OR '.join([f"e.src = '{vid}'" for vid in p_id_variants])
    if p_email:
        id_conditions += f" OR e.src = '{p_email}'"
    if p_name:
        id_conditions += f" OR e.src = '{p_name}'"

    owner_conditions = ' OR '.join([f"v.owner = '{vid}'" for vid in p_id_variants])
    if p_email:
        owner_conditions += f" OR v.owner = '{p_email}'"
    if p_name:
        owner_conditions += f" OR v.owner = '{p_name}'"

    group_path_cases_id = " ".join([f"WHEN e.src = '{gid}' THEN '{path.replace(chr(39), chr(39)+chr(39))}'" for gid, path in group_paths.items()]) if group_paths else ""
    group_path_cases_name = " ".join([f"WHEN e.src = '{gname.replace(chr(39), chr(39)+chr(39))}' THEN '{path.replace(chr(39), chr(39)+chr(39))}'" for gname, path in group_name_paths.items()]) if group_name_paths else ""
    group_path_cases = f"{group_path_cases_id} {group_path_cases_name}".strip()

    group_ids_sql = ','.join([f"'{gid}'" for gid in group_ids]) if group_ids else "'__none__'"
    group_names_sql = ','.join([f"'{gname.replace(chr(39), chr(39)+chr(39))}'" for gname in group_names]) if group_names else "'__none__'"
    principal_types_sql = ','.join([f"'{t}'" for t in PRINCIPAL_TYPES])

    query = f"""
    WITH direct_access AS (
        SELECT v.id as resource_id, v.name as resource_name, v.node_type as resource_type,
               e.permission_level, 'DIRECT' as source, CAST(NULL AS STRING) as inheritance_path
        FROM {EDGES_TABLE} e JOIN {VERTICES_TABLE} v ON e.dst = v.id
        WHERE ({id_conditions}) AND e.permission_level IS NOT NULL
          AND v.node_type NOT IN ({principal_types_sql}) {type_filter}
          AND e.run_id = '{SELECTED_RUN_ID}' AND v.run_id = '{SELECTED_RUN_ID}'
    ),
    owned_resources AS (
        SELECT v.id as resource_id, v.name as resource_name, v.node_type as resource_type,
               'ALL PRIVILEGES' as permission_level, 'OWNERSHIP' as source, CAST(NULL AS STRING) as inheritance_path
        FROM {VERTICES_TABLE} v
        WHERE ({owner_conditions}) AND v.node_type NOT IN ({principal_types_sql}) {type_filter}
          AND v.run_id = '{SELECTED_RUN_ID}'
    ),
    group_access AS (
        SELECT v.id as resource_id, v.name as resource_name, v.node_type as resource_type,
               e.permission_level, 'GROUP' as source,
               CASE {group_path_cases} ELSE COALESCE(g.name, e.src) END as inheritance_path
        FROM {EDGES_TABLE} e JOIN {VERTICES_TABLE} v ON e.dst = v.id
        LEFT JOIN {VERTICES_TABLE} g ON (e.src = g.id OR e.src = g.name)
        WHERE (e.src IN ({group_ids_sql}) OR e.src IN ({group_names_sql}))
          AND e.permission_level IS NOT NULL AND v.node_type NOT IN ({principal_types_sql}) {type_filter}
          AND e.run_id = '{SELECTED_RUN_ID}' AND v.run_id = '{SELECTED_RUN_ID}'
    ),
    parent_access AS (
        -- Inherited from parent resources (e.g., Catalog -> Schema -> Table)
        -- If principal has access to a catalog, they can access schemas/tables within it
        SELECT
            child.id as resource_id,
            child.name as resource_name,
            child.node_type as resource_type,
            e.permission_level,
            'PARENT' as source,
            parent.name as inheritance_path
        FROM {EDGES_TABLE} contains
        JOIN {VERTICES_TABLE} parent ON contains.src = parent.id AND parent.run_id = '{SELECTED_RUN_ID}'
        JOIN {VERTICES_TABLE} child ON contains.dst = child.id AND child.run_id = '{SELECTED_RUN_ID}'
        JOIN {EDGES_TABLE} e ON e.dst = parent.id AND e.run_id = '{SELECTED_RUN_ID}'
        WHERE contains.relationship = 'Contains'
          AND contains.run_id = '{SELECTED_RUN_ID}'
          AND (
              -- Direct principal access to parent (with ID variants)
              ({id_conditions})
              -- Group access to parent (by ID or name)
              OR e.src IN ({group_ids_sql})
              OR e.src IN ({group_names_sql})
          )
          AND e.permission_level IS NOT NULL
          AND child.node_type NOT IN ({principal_types_sql})
          {type_filter}
    )
    SELECT DISTINCT resource_id, resource_name, resource_type, permission_level, source, inheritance_path
    FROM (SELECT * FROM direct_access UNION ALL SELECT * FROM owned_resources UNION ALL SELECT * FROM group_access UNION ALL SELECT * FROM parent_access)
    ORDER BY resource_type, resource_name
    """

    result = spark.sql(query)
    source_counts = result.groupBy("source").count().collect()
    source_summary = {row["source"]: row["count"] for row in source_counts}

    print(f"\nFound {result.count()} accessible resources:")
    print(f"  - Direct: {source_summary.get('DIRECT', 0)}")
    print(f"  - Via Groups: {source_summary.get('GROUP', 0)}")
    print(f"  - Via Ownership: {source_summary.get('OWNERSHIP', 0)}")
    print(f"  - Via Parent: {source_summary.get('PARENT', 0) + source_summary.get('PARENT_INHERITANCE', 0)}")

    return result


def get_resource_access(resource_identifier):
    """Get all principals who can access a resource."""
    resource = find_resource(resource_identifier)
    if not resource:
        print(f"Resource '{resource_identifier}' not found")
        return None

    r_id = resource["id"]
    r_owner = resource["owner"] or ""

    print(f"Analyzing access to: {resource['name']}")
    print(f"  Type: {resource['node_type']}")
    print(f"  Owner: {resource['owner']}")

    principal_types_sql = ','.join([f"'{t}'" for t in PRINCIPAL_TYPES])
    user_sp_types_sql = ','.join([f"'{t}'" for t in USER_SP_TYPES])
    group_types_sql = ','.join([f"'{t}'" for t in GROUP_TYPES])

    query = f"""
    WITH direct_grants AS (
        SELECT v.id as principal_id, COALESCE(v.display_name, v.name) as principal_name,
               v.email as principal_email, v.node_type as principal_type, e.permission_level,
               'DIRECT' as source, CAST(NULL AS STRING) as inheritance_path
        FROM {EDGES_TABLE} e JOIN {VERTICES_TABLE} v ON (e.src = v.id OR e.src = v.email OR e.src = v.name)
        WHERE e.dst = '{r_id}' AND e.permission_level IS NOT NULL AND v.node_type IN ({user_sp_types_sql})
          AND e.run_id = '{SELECTED_RUN_ID}' AND v.run_id = '{SELECTED_RUN_ID}'
    ),
    group_grants AS (
        SELECT g.id as principal_id, g.name as principal_name, CAST(NULL AS STRING) as principal_email,
               g.node_type as principal_type, e.permission_level, 'DIRECT' as source, CAST(NULL AS STRING) as inheritance_path
        FROM {EDGES_TABLE} e JOIN {VERTICES_TABLE} g ON (e.src = g.id OR e.src = g.name)
        WHERE e.dst = '{r_id}' AND e.permission_level IS NOT NULL AND g.node_type IN ({group_types_sql})
          AND e.run_id = '{SELECTED_RUN_ID}' AND g.run_id = '{SELECTED_RUN_ID}'
    ),
    ownership AS (
        SELECT v.id as principal_id, COALESCE(v.display_name, v.name) as principal_name,
               v.email as principal_email, v.node_type as principal_type, 'ALL PRIVILEGES' as permission_level,
               'OWNERSHIP' as source, CAST(NULL AS STRING) as inheritance_path
        FROM {VERTICES_TABLE} v
        WHERE (v.id = '{r_owner}' OR v.email = '{r_owner}' OR v.name = '{r_owner}')
          AND v.node_type IN ({principal_types_sql}) AND '{r_owner}' != ''
          AND v.run_id = '{SELECTED_RUN_ID}'
    )
    SELECT DISTINCT principal_id,
           CASE
               WHEN principal_email IS NOT NULL AND principal_email != '' AND LOWER(principal_name) != LOWER(principal_email)
               THEN CONCAT(principal_name, ' (', principal_email, ')')
               ELSE principal_name
           END as principal,
           principal_type, permission_level, source, inheritance_path
    FROM (SELECT * FROM direct_grants UNION ALL SELECT * FROM group_grants UNION ALL SELECT * FROM ownership)
    ORDER BY CASE source WHEN 'DIRECT' THEN 1 WHEN 'OWNERSHIP' THEN 2 ELSE 3 END, principal_type, principal
    """

    result = spark.sql(query)
    source_counts = result.groupBy("source").count().collect()
    source_summary = {row["source"]: row["count"] for row in source_counts}

    print(f"\nFound {result.count()} principals with access:")
    print(f"  - Direct: {source_summary.get('DIRECT', 0)}")
    print(f"  - Via Ownership: {source_summary.get('OWNERSHIP', 0)}")

    return result

# COMMAND ----------

# DBTITLE 1,Run Interactive Analysis
analysis_type = dbutils.widgets.get("analysis_type")
identifier = dbutils.widgets.get("identifier").strip()

if identifier:
    print("=" * 70)
    print(f"Running: {analysis_type}")
    print("=" * 70)

    if analysis_type == "Principal Access":
        # Use SecurityAnalyzer if available, otherwise fallback to standalone function
        if analyzer:
            principal = analyzer.find_principal(identifier)
            if principal:
                print(f"Analyzing access for: {format_principal_name(principal['display_name'], principal['email'], principal['name'], principal['id'])}")
                print(f"  Type: {principal['node_type']}")
                result = analyzer.get_principal_access(identifier, None)

                # Print summary statistics
                if result:
                    # Calculate unique resources count
                    unique_resources = result.select("resource_id").distinct().count()

                    source_counts = result.groupBy("source").count().collect()
                    source_summary = {row["source"]: row["count"] for row in source_counts}
                    total = result.count()

                    print(f"\nAccess Summary:")
                    print(f"  Unique Resources: {unique_resources:,}")
                    print(f"  Total Access Grants: {total:,}")
                    print(f"\nBy Access Source:")
                    print(f"  - Direct: {source_summary.get('DIRECT', 0):,}")
                    print(f"  - Via Groups: {source_summary.get('GROUP', 0):,}")
                    print(f"  - Via Ownership: {source_summary.get('OWNERSHIP', 0):,}")
                    print(f"  - Via Parent: {(source_summary.get('PARENT', 0) + source_summary.get('PARENT_INHERITANCE', 0)):,}")
            else:
                print(f"Principal '{identifier}' not found")
                result = None
        else:
            result = get_principal_access(identifier, None)

            # Calculate unique resources count for standalone function too
            if result:
                unique_resources = result.select("resource_id").distinct().count()
                total = result.count()
                print(f"\nAccess Summary:")
                print(f"  Unique Resources: {unique_resources:,}")
                print(f"  Total Access Grants: {total:,}")

        if result:
            display(result)

    elif analysis_type == "Resource Access":
        # Use SecurityAnalyzer if available (provides full grouping and deduplication),
        # otherwise fallback to standalone function (simplified results without grouping)
        if analyzer:
            resource = analyzer.find_resource(identifier)
            if resource:
                print(f"Analyzing access to: {resource['name']}")
                print(f"  Type: {resource['node_type']}")
                print(f"  Owner: {resource['owner']}")
                result = analyzer.get_resource_access(identifier)

                # Group and summarize results like the app
                if result:
                    # Create temp view for grouping
                    result.createOrReplaceTempView("resource_access_raw")

                    # Group by unique principal (canonical ID + email/name)
                    grouped = spark.sql("""
                        SELECT
                            -- Extract canonical ID for grouping
                            CASE
                                WHEN principal_id LIKE '%:%' THEN SPLIT(principal_id, ':')[1]
                                ELSE principal_id
                            END as canonical_id,
                            FIRST(principal_id) as principal_id,
                            FIRST(principal_name) as principal_name,
                            FIRST(principal_email) as principal_email,
                            FIRST(
                                CASE
                                    WHEN principal_type = 'AccountUser' THEN 'User'
                                    WHEN principal_type = 'AccountGroup' THEN 'Group'
                                    WHEN principal_type LIKE '%ServicePrincipal%' THEN 'Service Principal'
                                    ELSE principal_type
                                END
                            ) as principal_type,
                            COLLECT_SET(permission_level) as permissions,
                            COLLECT_SET(source) as sources,
                            COLLECT_LIST(inheritance_path) as inheritance_paths
                        FROM resource_access_raw
                        GROUP BY canonical_id, COALESCE(principal_email, principal_name)
                        ORDER BY principal_type, principal_name
                    """)

                    # Calculate summary statistics
                    total_unique = grouped.count()

                    # Count by source type (principals can have multiple sources)
                    direct_count = grouped.filter("array_contains(sources, 'DIRECT')").count()
                    group_count = grouped.filter("array_contains(sources, 'GROUP')").count()
                    ownership_count = grouped.filter("array_contains(sources, 'OWNERSHIP')").count()
                    parent_count = grouped.filter("array_contains(sources, 'PARENT_INHERITANCE') OR array_contains(sources, 'PARENT')").count()

                    # Count by type
                    type_counts = grouped.groupBy("principal_type").count().collect()
                    type_summary = {row["principal_type"]: row["count"] for row in type_counts}

                    print(f"\nAccess Summary:")
                    print(f"  Total: {total_unique:,}")
                    print(f"  Direct: {direct_count:,}")
                    print(f"  Via Groups: {group_count:,}")
                    print(f"  Ownership: {ownership_count:,}")
                    print(f"  Via Parent: {parent_count:,}")
                    print(f"\nFound {total_unique:,} unique principal(s) with access:")
                    if "User" in type_summary:
                        print(f"  - Users: {type_summary.get('User', 0):,}")
                    if "Group" in type_summary:
                        print(f"  - Groups: {type_summary.get('Group', 0):,}")
                    if "Service Principal" in type_summary:
                        print(f"  - Service Principals: {type_summary.get('Service Principal', 0):,}")

                    # Display grouped results
                    result = grouped
            else:
                print(f"Resource '{identifier}' not found")
                result = None
        else:
            # Fallback: use standalone function (simplified - no grouping)
            result = get_resource_access(identifier)
            if result:
                # Standalone function provides simple results without grouping
                total = result.count()
                print(f"\nFound {total:,} principal(s) with access (simplified view)")

        if result:
            display(result)
else:
    print("=" * 70)
    print("PRINCIPAL & RESOURCE ACCESS ANALYSIS")
    print("=" * 70)
    print("\nConfigure the analysis using the widgets above:")
    print("  1. Analysis Type: Select 'Principal Access' or 'Resource Access'")
    print("  2. Principal or Resource: Enter identifier (email, name, or ID)")
    print("\nExamples:")
    print("  - Principal Access: user@example.com")
    print("  - Resource Access: catalog.schema.table or my_catalog")

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC ## Tips
# MAGIC
# MAGIC ### Principal Access Examples
# MAGIC - User email: `user@example.com`
# MAGIC - Service principal: `my-service-principal`
# MAGIC - Group name: `data-scientists`
# MAGIC
# MAGIC ### Resource Access Examples
# MAGIC - Catalog: `main`
# MAGIC - Schema: `main.default`
# MAGIC - Table: `main.default.users`
# MAGIC - Job: `my-etl-job`
# MAGIC - Warehouse: `analytics-warehouse`
# MAGIC
# MAGIC ### Understanding Results
# MAGIC
# MAGIC **Access Sources:**
# MAGIC - **DIRECT**: Explicit permission grant to the principal
# MAGIC - **GROUP**: Inherited from group membership
# MAGIC - **OWNERSHIP**: Principal owns the resource
# MAGIC - **PARENT**: Inherited from parent resource (e.g., catalog permissions apply to schemas)
# MAGIC
# MAGIC **Permission Levels:**
# MAGIC - **ALL PRIVILEGES**: Full control over the resource
# MAGIC - **USE CATALOG/SCHEMA**: Basic read access
# MAGIC - **SELECT**: Read data
# MAGIC - **MODIFY**: Write data
# MAGIC - **CREATE**: Create child resources
# MAGIC - **MANAGE**: Manage permissions and metadata
