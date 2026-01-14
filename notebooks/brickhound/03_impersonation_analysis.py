# Databricks notebook source
# MAGIC %md
# MAGIC # Impersonation Analysis
# MAGIC *Discover impersonation paths between principals*
# MAGIC
# MAGIC ## Overview
# MAGIC **Question:** Can one principal reach another through the security graph?
# MAGIC
# MAGIC This analysis identifies paths from a source principal to a target principal, revealing:
# MAGIC - **Service account impersonation risks**: Can a user reach a privileged service account?
# MAGIC - **Cross-user impersonation capabilities**: Can one user act as another?
# MAGIC - **Privilege boundary violations**: Can a low-privilege principal reach high-privilege one?
# MAGIC - **Unauthorized access patterns**: Hidden connections between principals
# MAGIC
# MAGIC ## Example Scenarios
# MAGIC - Developer → service-principals group → admin-automation-sp (can the developer impersonate the admin SP?)
# MAGIC - contractor@external.com → data-team → platform-admin@company.com (can contractor reach admin?)
# MAGIC - my-app-sp → oauth-clients → user-impersonation-sp (can app SP impersonate users?)
# MAGIC
# MAGIC ## Use Cases
# MAGIC - Security audits: Identify impersonation risks
# MAGIC - Incident response: How could attacker pivot from compromised account?
# MAGIC - Compliance: Document principal isolation boundaries
# MAGIC
# MAGIC ## Prerequisites
# MAGIC
# MAGIC Run `/notebooks/permission_analysis_data_collection.py` first to populate the graph data.

# COMMAND ----------

# DBTITLE 1,Run Common Setup
# MAGIC %run ./00_analysis_common

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC # Analysis Configuration
# MAGIC
# MAGIC Choose your analysis type and configure the parameters below.

# COMMAND ----------

# DBTITLE 1,Configure Analysis
# Create widgets for impersonation analysis
dbutils.widgets.dropdown("source_type", "User", ["User", "Group", "ServicePrincipal"], "Source Type")
dbutils.widgets.text("source_identifier", "", "Source Principal")
dbutils.widgets.dropdown("target_type", "User", ["User", "Group", "ServicePrincipal"], "Target Type")
dbutils.widgets.text("target_identifier", "", "Target Principal")
dbutils.widgets.dropdown("path_type", "All Paths", ["All Paths", "Shortest Path"], "Analysis Type")

# COMMAND ----------

# DBTITLE 1,Helper Functions
import networkx as nx
from collections import deque

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


def find_impersonation_paths(source_type, source_identifier, target_type, target_identifier, find_all=True, max_depth=5):
    """
    Find paths from a source principal to a target principal through the security graph.

    This analysis identifies:
    - Service account impersonation risks
    - Cross-user impersonation capabilities
    - Privilege boundary violations
    - Unauthorized access patterns
    """
    # Map widget types to node types
    type_map = {
        "User": ["User", "AccountUser"],
        "Group": ["Group", "AccountGroup"],
        "ServicePrincipal": ["ServicePrincipal", "AccountServicePrincipal"]
    }

    source_node_types = type_map.get(source_type, [source_type])
    target_node_types = type_map.get(target_type, [target_type])

    # Find source principal
    source = vertices.filter(
        (F.col("node_type").isin(source_node_types)) &
        ((F.col("id") == source_identifier) |
         (F.col("email") == source_identifier) |
         (F.col("name") == source_identifier) |
         (F.col("display_name") == source_identifier))
    ).first()

    if not source:
        print(f"Source principal '{source_identifier}' of type '{source_type}' not found")
        return None

    # Find target principal
    target = vertices.filter(
        (F.col("node_type").isin(target_node_types)) &
        ((F.col("id") == target_identifier) |
         (F.col("email") == target_identifier) |
         (F.col("name") == target_identifier) |
         (F.col("display_name") == target_identifier))
    ).first()

    if not target:
        print(f"Target principal '{target_identifier}' of type '{target_type}' not found")
        return None

    source_id = source["id"]
    target_id = target["id"]
    source_display = format_principal_name(source["display_name"], source["email"], source["name"], source_id)
    target_display = format_principal_name(target["display_name"], target["email"], target["name"], target_id)

    print(f"Finding paths from: {source_display} ({source['node_type']})")
    print(f"              to: {target_display} ({target['node_type']})")

    # Build NetworkX graph
    G = nx.DiGraph()

    # Add vertices and track email/name mappings
    vertex_data = vertices.collect()
    email_to_ids = {}  # Map email to all node IDs with that email
    name_to_ids = {}   # Map name to all node IDs with that name

    for row in vertex_data:
        G.add_node(row["id"],
                   node_type=row["node_type"],
                   name=row["name"],
                   display_name=row["display_name"],
                   email=row["email"])

        # Track email mappings (for handling User + AccountUser variants)
        if row["email"]:
            email_lower = row["email"].lower()
            if email_lower not in email_to_ids:
                email_to_ids[email_lower] = []
            email_to_ids[email_lower].append(row["id"])

        # Track name mappings (for handling Group + AccountGroup variants)
        if row["name"]:
            name_lower = row["name"].lower()
            if name_lower not in name_to_ids:
                name_to_ids[name_lower] = []
            name_to_ids[name_lower].append(row["id"])

    # Add edges
    edge_data = edges.collect()
    for row in edge_data:
        G.add_edge(row["src"], row["dst"],
                   relationship=row["relationship"],
                   permission_level=row["permission_level"])

    # Find ALL node IDs that match source/target (handles account vs workspace level)
    source_ids = set([source_id])
    target_ids = set([target_id])

    # Add all variants with same email (for Users/ServicePrincipals)
    # Note: source/target are Spark Row objects, use bracket notation
    source_email = (source["email"] if source["email"] else "").lower()
    target_email = (target["email"] if target["email"] else "").lower()
    if source_email and source_email in email_to_ids:
        source_ids.update(email_to_ids[source_email])
    if target_email and target_email in email_to_ids:
        target_ids.update(email_to_ids[target_email])

    # Add all variants with same name (for Groups)
    source_name = (source["name"] if source["name"] else "").lower()
    target_name = (target["name"] if target["name"] else "").lower()
    if source_name and source_name in name_to_ids:
        source_ids.update(name_to_ids[source_name])
    if target_name and target_name in name_to_ids:
        target_ids.update(name_to_ids[target_name])

    print(f"  Source variants: {len(source_ids)} node(s)")
    print(f"  Target variants: {len(target_ids)} node(s)")

    # Find paths from ANY source variant to ANY target variant
    paths_found = []

    if not find_all:
        # Find shortest path only - try all source/target combinations
        for sid in source_ids:
            for tid in target_ids:
                try:
                    path = nx.shortest_path(G, source=sid, target=tid)
                    paths_found.append(path)
                    break  # Found shortest, stop
                except nx.NetworkXNoPath:
                    continue
            if paths_found:
                break
    else:
        # Find all simple paths (limited by max_depth)
        for sid in source_ids:
            for tid in target_ids:
                try:
                    paths = list(nx.all_simple_paths(G, source=sid, target=tid, cutoff=max_depth))
                    paths_found.extend(paths)
                    if len(paths_found) >= 20:  # Limit to 20 paths total
                        paths_found = paths_found[:20]
                        break
                except nx.NetworkXNoPath:
                    continue
            if len(paths_found) >= 20:
                break

    # Format results
    results = []
    for i, path in enumerate(paths_found, 1):
        path_details = []
        for j, node_id in enumerate(path):
            node_data = G.nodes.get(node_id, {})
            node_name = node_data.get("display_name") or node_data.get("email") or node_data.get("name") or node_id
            node_type = node_data.get("node_type", "Unknown")

            hop_info = {
                "node_id": node_id,
                "node_name": node_name,
                "node_type": node_type
            }

            # Add edge info (relationship from this node to next)
            if j < len(path) - 1:
                edge_data = G.edges.get((node_id, path[j + 1]), {})
                hop_info["relationship"] = edge_data.get("relationship", "")
                hop_info["permission_level"] = edge_data.get("permission_level", "")

            path_details.append(hop_info)

        # Create path string
        path_str = " → ".join([
            f"{h['node_name']}" + (f" [{h['relationship']}]" if h.get('relationship') else "")
            for h in path_details
        ])

        results.append({
            "path_number": i,
            "path_length": len(path),
            "hops": len(path) - 1,
            "path": path_str,
            "details": path_details
        })

    print(f"\nFound {len(results)} path(s)")

    if results:
        print("\n" + "=" * 70)
        for r in results:
            print(f"\nPath {r['path_number']} ({r['hops']} hops):")
            print(f"  {r['path']}")
    else:
        print("\nNo paths found between source and target")

    return results

# COMMAND ----------

# DBTITLE 1,Run Analysis
source_type = dbutils.widgets.get("source_type")
source_identifier = dbutils.widgets.get("source_identifier").strip()
target_type = dbutils.widgets.get("target_type")
target_identifier = dbutils.widgets.get("target_identifier").strip()
path_type = dbutils.widgets.get("path_type")

if source_identifier and target_identifier:
    print("=" * 70)
    print("IMPERSONATION ANALYSIS")
    print("=" * 70)
    print(f"\nAnalysis Type: {path_type}")

    find_all = (path_type == "All Paths")
    result = find_impersonation_paths(
        source_type, source_identifier,
        target_type, target_identifier,
        find_all=find_all
    )

    if result:
        # Convert to DataFrame for display
        paths_data = [
            {
                "Path #": r["path_number"],
                "Hops": r["hops"],
                "Path": r["path"]
            }
            for r in result
        ]
        if paths_data:
            paths_df = spark.createDataFrame(paths_data)
            print("\n📊 PATH SUMMARY:")
            display(paths_df)
    else:
        print("\n✓ No impersonation paths found")
        print(f"\n{source_type} '{source_identifier}' cannot reach {target_type} '{target_identifier}' through the security graph.")
        print("This indicates proper principal isolation.")
else:
    print("=" * 70)
    print("IMPERSONATION ANALYSIS")
    print("=" * 70)
    print("\nConfigure the analysis using the widgets above:")
    print("  1. Source Type: Select User, Group, or ServicePrincipal")
    print("  2. Source Principal: Enter email or name (e.g., user@example.com)")
    print("  3. Target Type: Select User, Group, or ServicePrincipal")
    print("  4. Target Principal: Enter email or name (e.g., admin@example.com)")
    print("  5. Analysis Type: 'All Paths' or 'Shortest Path'")
    print("\nThis analysis identifies:")
    print("  - Service account impersonation risks")
    print("  - Cross-user impersonation capabilities")
    print("  - Privilege boundary violations")
    print("  - Unauthorized access patterns")

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC ## Understanding Results
# MAGIC
# MAGIC ### Path Interpretation
# MAGIC - Each path shows the sequence of relationships connecting source to target
# MAGIC - Relationships shown in brackets: `[MemberOf]`, `[HasMember]`, `[CanManage]`
# MAGIC - Shorter paths = more direct connection = higher risk
# MAGIC
# MAGIC ### Risk Assessment
# MAGIC - **0 hops (same principal)**: Source and target are the same
# MAGIC - **1 hop**: Direct relationship (e.g., user is member of target group)
# MAGIC - **2-3 hops**: Moderate path (review for business justification)
# MAGIC - **4+ hops**: Long path (may indicate over-complex permission structure)
# MAGIC
# MAGIC ### Common Patterns
# MAGIC - User → Group → Service Principal (group-based SP access)
# MAGIC - Service Principal → Cluster → User (cluster creator relationships)
# MAGIC - User → Group → Group → Admin (nested group escalation)
# MAGIC
# MAGIC ### Security Use Cases
# MAGIC
# MAGIC **Incident Response:**
# MAGIC - "User X's credentials were compromised - can they reach admin accounts?"
# MAGIC - Run Impersonation Analysis from compromised user to admin principals
# MAGIC - Identify lateral movement opportunities
# MAGIC
# MAGIC **Access Review:**
# MAGIC - "Should contractor have access to admin service principal?"
# MAGIC - Run Impersonation Analysis from contractor to admin SP
# MAGIC - If path exists, review and remediate
# MAGIC
# MAGIC **Compliance & Auditing:**
# MAGIC - Document principal isolation boundaries
# MAGIC - Verify separation of duties
# MAGIC - Identify privilege escalation opportunities
# MAGIC
# MAGIC **Security Testing:**
# MAGIC - Test if low-privilege principals can reach high-privilege ones
# MAGIC - Validate security controls and boundaries
# MAGIC - Find unexpected access paths
