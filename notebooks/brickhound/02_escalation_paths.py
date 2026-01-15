# Databricks notebook source
# MAGIC %md
# MAGIC # Privilege Escalation Path Analysis
# MAGIC *Identify paths from a principal to admin privileges*
# MAGIC
# MAGIC ## What This Analysis Does
# MAGIC
# MAGIC This notebook identifies **privilege escalation paths** - routes through the security graph that allow a principal to reach administrative privileges.
# MAGIC
# MAGIC ### Detection Methods
# MAGIC
# MAGIC 1. **Direct Role Assignment**
# MAGIC    - AccountAdmin role directly assigned via SCIM API
# MAGIC    - Shows as "Direct Role (account_admin)" in results
# MAGIC
# MAGIC 2. **Group-Based Escalation**
# MAGIC    - Membership in admin groups (including nested groups):
# MAGIC      - `admins` (account-level) → Account Admin
# MAGIC      - Groups with "account admin" in name → Account Admin
# MAGIC      - Groups with "metastore admin" in name → Metastore Admin
# MAGIC      - Groups with "workspace admin" in name → Workspace Admin
# MAGIC    - Shows path through group memberships
# MAGIC
# MAGIC ### Why This Matters
# MAGIC
# MAGIC **Security Use Cases:**
# MAGIC - **Attack Surface Analysis**: Understand how an attacker with compromised credentials could escalate privileges
# MAGIC - **Least Privilege Review**: Identify users who can reach admin rights through non-obvious paths
# MAGIC - **Access Review**: Discover hidden administrative access via nested groups
# MAGIC - **Compliance**: Document privilege escalation risks for audit requirements
# MAGIC
# MAGIC **Example Scenarios:**
# MAGIC - A developer is in "data-team" group, which is in "platform-admins" group, which is in "admins" group → Account Admin (2-hop path)
# MAGIC - A service principal has AccountAdmin role directly → Account Admin (direct)
# MAGIC - A user is in "uc-admins" group → Metastore Admin (1-hop path)
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
# MAGIC # Escalation Path Analysis
# MAGIC
# MAGIC Use the widget below to analyze privilege escalation paths for a specific principal.

# COMMAND ----------

# DBTITLE 1,Configure Analysis
# Create widget for principal identifier
dbutils.widgets.text("identifier", "", "Principal (email, name, or ID)")

# COMMAND ----------

# DBTITLE 1,Helper Functions
import networkx as nx

PRINCIPAL_TYPES = ["User", "Group", "ServicePrincipal", "AccountUser", "AccountGroup", "AccountServicePrincipal"]
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


def find_escalation_paths(principal_identifier, max_depth=5):
    """Find privilege escalation paths from a principal to admin roles."""
    principal = find_principal(principal_identifier)
    if not principal:
        print(f"Principal '{principal_identifier}' not found")
        return None

    p_id = principal["id"]
    p_display = format_principal_name(principal['display_name'], principal['email'], principal['name'], p_id)

    print(f"Finding escalation paths for: {p_display}")

    # Build NetworkX graph
    G = nx.DiGraph()
    for row in vertices.collect():
        G.add_node(row["id"], node_type=row["node_type"], name=row["name"],
                   display_name=row["display_name"], email=row["email"])
    for row in edges.collect():
        G.add_edge(row["src"], row["dst"], relationship=row["relationship"],
                   permission_level=row["permission_level"])

    attack_paths = []

    # First check for DIRECT AccountAdmin edges (Account Admin via direct role assignment)
    if p_id in G.nodes():
        for neighbor in G.neighbors(p_id):
            edge_data = G.edges.get((p_id, neighbor), {})
            if edge_data.get("relationship") == "AccountAdmin":
                p_name = G.nodes[p_id].get("email") or G.nodes[p_id].get("name") or p_id
                target_name = G.nodes[neighbor].get("name") or neighbor
                attack_paths.append({
                    "target": "Account Admin (Direct Role)",
                    "path_length": 1,
                    "path": f"{p_name} -> [AccountAdmin] -> {target_name}",
                    "path_type": "DIRECT_ROLE"
                })
                print(f"\n  👑 Direct Account Admin: {p_name} has AccountAdmin role")

    # Find admin groups for group-based escalation paths
    admin_groups = vertices.filter(
        (F.col("node_type").isin(GROUP_TYPES)) &
        ((F.lower(F.col("name")) == "admins") |
         (F.lower(F.col("name")).like("%account%admin%")) |
         (F.lower(F.col("name")).like("%metastore%admin%")) |
         (F.lower(F.col("name")).like("%workspace%admin%")))
    ).select("id", "name").collect()

    target_ids = {row["id"] for row in admin_groups}
    target_names = {row["id"]: row["name"] for row in admin_groups}

    print(f"Found {len(target_ids)} admin group targets")

    # Find paths to admin groups
    for target_id in target_ids:
        if target_id not in G.nodes() or p_id not in G.nodes():
            continue
        try:
            paths = list(nx.all_simple_paths(G, source=p_id, target=target_id, cutoff=max_depth))
            for path in paths[:3]:
                is_membership = all(
                    G.edges.get((path[i-1], path[i]), {}).get("relationship") in ("MemberOf", "HasMember")
                    for i in range(1, len(path))
                )
                if is_membership:
                    path_names = [G.nodes[n].get("email") or G.nodes[n].get("name") or n for n in path]
                    attack_paths.append({
                        "target": target_names.get(target_id, target_id),
                        "path_length": len(path),
                        "path": " -> ".join(path_names),
                        "path_type": "GROUP_MEMBERSHIP"
                    })
        except nx.NetworkXNoPath:
            pass

    print(f"\nFound {len(attack_paths)} escalation paths")
    for i, path in enumerate(attack_paths[:10], 1):
        path_type = path.get("path_type", "GROUP_MEMBERSHIP")
        icon = "👑" if path_type == "DIRECT_ROLE" else "📋"
        print(f"\n  {icon} Path {i} to [{path['target']}]:")
        print(f"    {path['path']}")

    return attack_paths

# COMMAND ----------

# DBTITLE 1,Run Escalation Path Analysis
identifier = dbutils.widgets.get("identifier").strip()

if identifier:
    print("=" * 70)
    print("PRIVILEGE ESCALATION PATH ANALYSIS")
    print("=" * 70)

    result = find_escalation_paths(identifier)

    if result:
        # Convert to DataFrame for display
        paths_df = spark.createDataFrame(result)

        print("\n" + "=" * 70)
        print("ESCALATION PATHS SUMMARY")
        print("=" * 70)

        # Summary by target role
        print("\nPaths by Target Role:")
        display(paths_df.groupBy("target").count().orderBy(F.desc("count")))

        # Summary by path type
        print("\nPaths by Type:")
        display(paths_df.groupBy("path_type").count().orderBy(F.desc("count")))

        print("\n" + "=" * 70)
        print("ALL ESCALATION PATHS")
        print("=" * 70)
        display(paths_df.orderBy("path_length", "target"))
    else:
        print("\n✓ No escalation paths found - this principal cannot reach admin privileges")
        print("\nThis is a good security posture if the principal should not have admin access.")
else:
    print("=" * 70)
    print("PRIVILEGE ESCALATION PATH ANALYSIS")
    print("=" * 70)
    print("\nConfigure the analysis using the widget above:")
    print("  Principal: Enter email, name, or ID")
    print("\nExamples:")
    print("  - User: user@example.com")
    print("  - Service Principal: my-service-principal")
    print("  - Group: data-scientists")
    print("\nThe analysis will identify:")
    print("  👑 Direct Account Admin role assignments")
    print("  📋 Paths through group memberships to admin groups")
    print("\nAdmin groups detected:")
    print("  - 'admins' (account-level) → Account Admin")
    print("  - Groups with 'account admin' → Account Admin")
    print("  - Groups with 'metastore admin' → Metastore Admin")
    print("  - Groups with 'workspace admin' → Workspace Admin")

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC ## Understanding Results
# MAGIC
# MAGIC ### Path Types
# MAGIC
# MAGIC **DIRECT_ROLE** (👑)
# MAGIC - Principal has AccountAdmin role directly assigned
# MAGIC - Highest risk - immediate admin access
# MAGIC - Common for break-glass accounts and automation service principals
# MAGIC
# MAGIC **GROUP_MEMBERSHIP** (📋)
# MAGIC - Principal reaches admin group through group membership chain
# MAGIC - Can involve nested groups (user → team → division → admins)
# MAGIC - Path length indicates number of hops
# MAGIC
# MAGIC ### Target Roles
# MAGIC
# MAGIC **Account Admin**
# MAGIC - Highest privilege level in Databricks
# MAGIC - Full control over entire account
# MAGIC - Can manage workspaces, users, billing
# MAGIC
# MAGIC **Metastore Admin**
# MAGIC - Full control over Unity Catalog metastore
# MAGIC - Can manage all catalogs, schemas, tables
# MAGIC - Can grant permissions on any data object
# MAGIC
# MAGIC **Workspace Admin**
# MAGIC - Full control over a specific workspace
# MAGIC - Can manage clusters, jobs, notebooks
# MAGIC - Cannot access Unity Catalog admin functions
# MAGIC
# MAGIC ### Security Recommendations
# MAGIC
# MAGIC **If escalation paths are found:**
# MAGIC
# MAGIC 1. **Review Necessity**: Does this principal need admin access?
# MAGIC 2. **Reduce Path Length**: Shorter paths = more direct control
# MAGIC 3. **Document Justification**: Admin access should have business justification
# MAGIC 4. **Monitor Activity**: Principals with escalation paths should be monitored
# MAGIC 5. **Regular Reviews**: Periodically verify admin access is still needed
# MAGIC
# MAGIC **If no paths are found:**
# MAGIC - Good security posture for regular users
# MAGIC - Expected for service accounts with limited scope
# MAGIC - Verify admin users DO have paths (false negative check)
# MAGIC
# MAGIC ### Common Patterns
# MAGIC
# MAGIC **Low Risk (Expected):**
# MAGIC - Service principal for Terraform → Account Admin (direct role)
# MAGIC - Security team member → admins group (1-hop)
# MAGIC
# MAGIC **Medium Risk (Review):**
# MAGIC - Developer → team-leads → platform-admins → admins (3-hop)
# MAGIC - Data analyst → data-team → metastore-admins (2-hop)
# MAGIC
# MAGIC **High Risk (Investigate):**
# MAGIC - External contractor → temp-users → admins (2-hop)
# MAGIC - Read-only service principal → Account Admin (direct role)
# MAGIC - Multiple independent paths to admin (redundant access)
