"""Security analysis module for BrickHound.

This module provides the SecurityAnalyzer class for analyzing Databricks
security graphs, including principal access, resource access, escalation
paths, and various security reports.
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class PrivilegedRole(Enum):
    """Databricks privileged roles for escalation analysis."""
    ACCOUNT_ADMIN = "account_admin"
    METASTORE_ADMIN = "metastore_admin"
    WORKSPACE_ADMIN = "workspace_admin"
    CATALOG_OWNER = "catalog_owner"


@dataclass
class PrivilegedRoleInfo:
    """Information about a privileged role."""
    name: str
    description: str
    risk_level: str  # CRITICAL, HIGH, MEDIUM, LOW


# Pre-defined privileged roles in Databricks
PRIVILEGED_ROLES: Dict[str, PrivilegedRoleInfo] = {
    "account_admin": PrivilegedRoleInfo(
        name="Account Admin",
        description="Full control over Databricks account",
        risk_level="CRITICAL"
    ),
    "metastore_admin": PrivilegedRoleInfo(
        name="Metastore Admin",
        description="Full control over Unity Catalog metastore",
        risk_level="CRITICAL"
    ),
    "workspace_admin": PrivilegedRoleInfo(
        name="Workspace Admin",
        description="Full control over workspace",
        risk_level="HIGH"
    ),
    "catalog_owner": PrivilegedRoleInfo(
        name="Catalog Owner",
        description="Full control over catalog and child objects",
        risk_level="HIGH"
    )
}

# Principal node types (workspace and account level)
PRINCIPAL_TYPES = [
    "User", "Group", "ServicePrincipal",
    "AccountUser", "AccountGroup", "AccountServicePrincipal"
]

# User/SP types (excludes groups)
USER_SP_TYPES = [
    "User", "ServicePrincipal",
    "AccountUser", "AccountServicePrincipal"
]

# Group types
GROUP_TYPES = ["Group", "AccountGroup"]


class SecurityAnalyzer:
    """
    Analyzer for Databricks security graph data.

    Provides methods for:
    - Principal access analysis (what can a user access?)
    - Resource access analysis (who can access a resource?)
    - Privilege escalation path detection
    - Security reports (orphaned resources, isolated principals, etc.)

    Args:
        spark: SparkSession instance
        vertices_table: Fully qualified name of vertices table (e.g., "catalog.schema.vertices")
        edges_table: Fully qualified name of edges table (e.g., "catalog.schema.edges")
        run_id: Optional run_id to filter data by specific collection run
    """

    def __init__(self, spark, vertices_table: str, edges_table: str, run_id: str = None):
        self.spark = spark
        self.vertices_table = vertices_table
        self.edges_table = edges_table
        self.run_id = run_id

        # Load and optionally filter DataFrames
        self._vertices = None
        self._edges = None
        self._nx_graph = None

    @property
    def vertices(self):
        """Lazily load and cache vertices DataFrame."""
        if self._vertices is None:
            from pyspark.sql import functions as F
            df = self.spark.table(self.vertices_table)
            if self.run_id:
                df = df.filter(F.col("run_id") == self.run_id)
            self._vertices = df.cache()
        return self._vertices

    @property
    def edges(self):
        """Lazily load and cache edges DataFrame."""
        if self._edges is None:
            from pyspark.sql import functions as F
            df = self.spark.table(self.edges_table)
            if self.run_id:
                df = df.filter(F.col("run_id") == self.run_id)
            self._edges = df.cache()
        return self._edges

    def set_run_id(self, run_id: str):
        """Set or change the run_id filter and reset cached data."""
        self.run_id = run_id
        self._vertices = None
        self._edges = None
        self._nx_graph = None

    # =========================================================================
    # Lookup Methods
    # =========================================================================

    def find_principal(self, identifier: str):
        """
        Find a principal (user/group/SP) by ID, email, or name.

        Args:
            identifier: ID, email, or name of the principal

        Returns:
            Row object with principal data, or None if not found
        """
        from pyspark.sql import functions as F

        result = self.vertices.filter(
            (F.col("id") == identifier) |
            (F.col("email") == identifier) |
            (F.col("name") == identifier) |
            (F.col("display_name") == identifier)
        ).filter(
            F.col("node_type").isin(PRINCIPAL_TYPES)
        ).first()
        return result

    def find_resource(self, identifier: str):
        """
        Find a resource by ID or name.

        Args:
            identifier: ID or name of the resource

        Returns:
            Row object with resource data, or None if not found
        """
        from pyspark.sql import functions as F

        result = self.vertices.filter(
            (F.col("id") == identifier) |
            (F.col("name") == identifier) |
            (F.col("display_name") == identifier)
        ).filter(
            ~F.col("node_type").isin(PRINCIPAL_TYPES)
        ).first()
        return result

    # =========================================================================
    # Group Membership Analysis
    # =========================================================================

    def get_principal_groups(self, principal_id: str, principal_email: str = None,
                             principal_name: str = None):
        """
        Get all groups a principal belongs to (including nested) with inheritance paths.

        Args:
            principal_id: ID of the principal
            principal_email: Optional email of the principal
            principal_name: Optional name of the principal

        Returns:
            DataFrame with columns: group_id, group_name, inheritance_path, depth
        """
        from pyspark.sql import functions as F

        # Get principal info if not provided
        if principal_email is None or principal_name is None:
            principal_info = self.vertices.filter(F.col("id") == principal_id).first()
            if principal_info:
                principal_email = principal_info.email
                principal_name = principal_info.name

        # Build list of ID variants to match
        id_variants = [principal_id]
        if ':' in str(principal_id):
            id_variants.append(principal_id.split(':')[-1])
        else:
            id_variants.append(f"account_user:{principal_id}")
            id_variants.append(f"account_group:{principal_id}")
            id_variants.append(f"account_sp:{principal_id}")

        # Build filter condition
        id_conditions = F.col("src") == id_variants[0]
        for vid in id_variants[1:]:
            id_conditions = id_conditions | (F.col("src") == vid)

        if principal_email:
            id_conditions = id_conditions | (F.col("src") == principal_email)
        if principal_name:
            id_conditions = id_conditions | (F.col("src") == principal_name)

        # Direct memberships
        direct = self.edges.filter(
            id_conditions &
            (F.col("relationship") == "MemberOf")
        ).alias("e").join(
            self.vertices.filter(F.col("node_type").isin(GROUP_TYPES))
                .select(F.col("id"), F.col("name").alias("group_name")).alias("g"),
            (F.col("e.dst") == F.col("g.id")) | (F.col("e.dst") == F.col("g.group_name"))
        ).select(
            F.col("g.id").alias("group_id"),
            F.col("g.group_name").alias("group_name"),
            F.col("g.group_name").alias("inheritance_path"),
            F.lit(0).alias("depth")
        ).distinct()

        # Get nested groups with path tracking (up to 10 levels)
        all_groups = direct
        current_level = direct

        for i in range(10):
            nested = self.edges.filter(
                F.col("relationship") == "MemberOf"
            ).alias("e2").join(
                current_level.alias("cl"),
                (F.col("e2.src") == F.col("cl.group_id")) | (F.col("e2.src") == F.col("cl.group_name"))
            ).join(
                self.vertices.filter(F.col("node_type").isin(GROUP_TYPES))
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

    def expand_group_members(self, group_id: str, group_name: str, initial_path: str,
                             permission: str, max_depth: int = 10) -> List[Tuple]:
        """
        Recursively expand group membership to find all members with inheritance paths.

        Args:
            group_id: ID of the group
            group_name: Name of the group
            initial_path: Initial path string for inheritance tracking
            permission: Permission level to propagate
            max_depth: Maximum recursion depth

        Returns:
            List of tuples: (principal_id, principal_name, principal_email, principal_type,
                           permission_level, source, inheritance_path)
        """
        return self._expand_group_members_recursive(
            group_id, group_name, initial_path, permission, 0, max_depth
        )

    def _expand_group_members_recursive(self, group_id: str, group_name: str,
                                        initial_path: str, permission: str,
                                        depth: int, max_depth: int) -> List[Tuple]:
        """Internal recursive group expansion."""
        if depth >= max_depth:
            return []

        results = []

        # Get direct members of this group
        members = self.spark.sql(f"""
            SELECT DISTINCT
                m.id as member_id,
                COALESCE(m.display_name, m.name) as member_name,
                m.email as member_email,
                m.node_type as member_type
            FROM {self.edges_table} e
            JOIN {self.vertices_table} m ON (e.src = m.id OR e.src = m.name OR e.src = m.email)
            WHERE (e.dst = '{group_id}' OR e.dst = '{group_name.replace("'", "''")}')
              AND e.relationship = 'MemberOf'
              {f"AND e.run_id = '{self.run_id}'" if self.run_id else ""}
              {f"AND m.run_id = '{self.run_id}'" if self.run_id else ""}
        """).collect()

        for member in members:
            member_id = member["member_id"]
            member_name = member["member_name"]
            member_email = member["member_email"]
            member_type = member["member_type"]

            if member_type in USER_SP_TYPES:
                results.append((
                    member_id, member_name, member_email, member_type,
                    permission, "GROUP", initial_path
                ))
            elif member_type in GROUP_TYPES:
                new_path = f"{member_name} -> {initial_path}"
                nested_results = self._expand_group_members_recursive(
                    member_id, member_name, new_path, permission, depth + 1, max_depth
                )
                results.extend(nested_results)

        return results

    # =========================================================================
    # Principal Access Analysis
    # =========================================================================

    def get_principal_access(self, principal_identifier: str, resource_type: str = None):
        """
        Get all resources a principal can access with effective permissions.

        Considers:
        - Direct grants to the principal
        - Grants via group membership (all nested levels)
        - Ownership (implicit ALL PRIVILEGES)
        - Parent resource inheritance (Catalog -> Schema -> Table)

        Args:
            principal_identifier: Email, name, or ID of the principal
            resource_type: Optional filter (e.g., "Table", "Schema", "Catalog")

        Returns:
            DataFrame with accessible resources, permission sources, and inheritance paths
        """
        from pyspark.sql import functions as F

        principal = self.find_principal(principal_identifier)
        if not principal:
            return None

        p_id = principal["id"]
        p_email = principal["email"] or ""
        p_name = principal["name"] or ""

        # Build ID variants
        p_id_variants = [p_id]
        if ':' in str(p_id):
            p_id_variants.append(p_id.split(':')[-1])
        else:
            p_id_variants.append(f"account_user:{p_id}")
            p_id_variants.append(f"account_group:{p_id}")
            p_id_variants.append(f"account_sp:{p_id}")

        # Get all groups
        all_groups_df = self.get_principal_groups(p_id, p_email, p_name)
        all_groups = all_groups_df.collect()

        group_paths = {row["group_id"]: row["inheritance_path"] for row in all_groups}
        group_name_paths = {row["group_name"]: row["inheritance_path"] for row in all_groups}
        group_ids = list(group_paths.keys())
        group_names = list(group_name_paths.keys())

        # Build the access query
        type_filter = f"AND v.node_type = '{resource_type}'" if resource_type else ""
        run_filter = f"AND e.run_id = '{self.run_id}'" if self.run_id else ""
        run_filter_v = f"AND v.run_id = '{self.run_id}'" if self.run_id else ""
        run_filter_g = f"AND g.run_id = '{self.run_id}'" if self.run_id else ""
        run_filter_parent = f"AND parent.run_id = '{self.run_id}'" if self.run_id else ""
        run_filter_child = f"AND child.run_id = '{self.run_id}'" if self.run_id else ""
        run_filter_contains = f"AND contains.run_id = '{self.run_id}'" if self.run_id else ""

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

        # Build group path cases
        group_path_cases_id = " ".join([
            f"WHEN e.src = '{gid}' THEN '{path.replace(chr(39), chr(39)+chr(39))}'"
            for gid, path in group_paths.items()
        ]) if group_paths else ""
        group_path_cases_name = " ".join([
            f"WHEN e.src = '{gname.replace(chr(39), chr(39)+chr(39))}' THEN '{path.replace(chr(39), chr(39)+chr(39))}'"
            for gname, path in group_name_paths.items()
        ]) if group_name_paths else ""
        group_path_cases = f"{group_path_cases_id} {group_path_cases_name}".strip()

        group_ids_sql = ','.join([f"'{gid}'" for gid in group_ids]) if group_ids else "'__none__'"
        group_names_sql = ','.join([f"'{gname.replace(chr(39), chr(39)+chr(39))}'" for gname in group_names]) if group_names else "'__none__'"

        principal_types_sql = ','.join([f"'{t}'" for t in PRINCIPAL_TYPES])

        query = f"""
        WITH direct_access AS (
            SELECT
                v.id as resource_id,
                v.name as resource_name,
                v.node_type as resource_type,
                e.permission_level,
                'DIRECT' as source,
                CAST(NULL AS STRING) as inheritance_path
            FROM {self.edges_table} e
            JOIN {self.vertices_table} v ON e.dst = v.id
            WHERE ({id_conditions})
              AND e.permission_level IS NOT NULL
              AND v.node_type NOT IN ({principal_types_sql})
              {type_filter}
              {run_filter}
              {run_filter_v}
        ),
        owned_resources AS (
            SELECT
                v.id as resource_id,
                v.name as resource_name,
                v.node_type as resource_type,
                'ALL PRIVILEGES' as permission_level,
                'OWNERSHIP' as source,
                CAST(NULL AS STRING) as inheritance_path
            FROM {self.vertices_table} v
            WHERE ({owner_conditions})
              AND v.node_type NOT IN ({principal_types_sql})
              {type_filter}
              {run_filter_v}
        ),
        group_access AS (
            SELECT
                v.id as resource_id,
                v.name as resource_name,
                v.node_type as resource_type,
                e.permission_level,
                'GROUP' as source,
                CASE {group_path_cases} ELSE COALESCE(g.name, e.src) END as inheritance_path
            FROM {self.edges_table} e
            JOIN {self.vertices_table} v ON e.dst = v.id {run_filter_v}
            LEFT JOIN {self.vertices_table} g ON (e.src = g.id OR e.src = g.name) {run_filter_g}
            WHERE (e.src IN ({group_ids_sql}) OR e.src IN ({group_names_sql}))
              AND e.permission_level IS NOT NULL
              AND v.node_type NOT IN ({principal_types_sql})
              {type_filter}
              {run_filter}
        ),
        parent_access AS (
            SELECT
                child.id as resource_id,
                child.name as resource_name,
                child.node_type as resource_type,
                e.permission_level,
                'PARENT_INHERITANCE' as source,
                parent.name as inheritance_path
            FROM {self.edges_table} contains
            JOIN {self.vertices_table} parent ON contains.src = parent.id {run_filter_parent}
            JOIN {self.vertices_table} child ON contains.dst = child.id {run_filter_child}
            JOIN {self.edges_table} e ON e.dst = parent.id {run_filter}
            WHERE contains.relationship = 'Contains'
              AND (({id_conditions}) OR e.src IN ({group_ids_sql}) OR e.src IN ({group_names_sql}))
              AND e.permission_level IS NOT NULL
              AND child.node_type NOT IN ({principal_types_sql})
              {type_filter}
              {run_filter_contains}
        )
        SELECT DISTINCT
            resource_id,
            resource_name,
            resource_type,
            permission_level,
            source,
            inheritance_path
        FROM (
            SELECT * FROM direct_access
            UNION ALL
            SELECT * FROM owned_resources
            UNION ALL
            SELECT * FROM group_access
            UNION ALL
            SELECT * FROM parent_access
        )
        ORDER BY resource_type, resource_name
        """

        return self.spark.sql(query)

    # =========================================================================
    # Resource Access Analysis
    # =========================================================================

    def get_resource_access(self, resource_identifier: str):
        """
        Get all principals who can access a resource, including via nested group membership.

        Args:
            resource_identifier: ID or name of the resource

        Returns:
            DataFrame with principals, permission sources, and inheritance paths
        """
        from pyspark.sql import functions as F

        resource = self.find_resource(resource_identifier)
        if not resource:
            return None

        r_id = resource["id"]
        r_name = resource["name"] or ""
        r_owner = resource["owner"] or ""

        run_filter = f"AND e.run_id = '{self.run_id}'" if self.run_id else ""
        run_filter_v = f"AND v.run_id = '{self.run_id}'" if self.run_id else ""
        run_filter_g = f"AND g.run_id = '{self.run_id}'" if self.run_id else ""
        run_filter_parent = f"AND parent.run_id = '{self.run_id}'" if self.run_id else ""
        run_filter_contains = f"AND contains.run_id = '{self.run_id}'" if self.run_id else ""

        principal_types_sql = ','.join([f"'{t}'" for t in PRINCIPAL_TYPES])
        user_sp_types_sql = ','.join([f"'{t}'" for t in USER_SP_TYPES])
        group_types_sql = ','.join([f"'{t}'" for t in GROUP_TYPES])

        # Find groups with direct access
        groups_with_access = self.spark.sql(f"""
            SELECT g.id as group_id, g.name as group_name, e.permission_level
            FROM {self.edges_table} e
            JOIN {self.vertices_table} g ON (e.src = g.id OR e.src = g.name)
            WHERE e.dst = '{r_id}'
              AND g.node_type IN ({group_types_sql})
              AND e.permission_level IS NOT NULL
              {run_filter}
              {run_filter_g}
        """).collect()

        # Expand group members recursively
        group_members_rows = []
        for group_row in groups_with_access:
            members = self._expand_group_members_recursive(
                group_row["group_id"], group_row["group_name"],
                group_row["group_name"], group_row["permission_level"], 0, 10
            )
            group_members_rows.extend(members)

        query = f"""
        WITH direct_grants AS (
            SELECT
                v.id as principal_id,
                COALESCE(v.display_name, v.name) as principal_name,
                v.email as principal_email,
                v.node_type as principal_type,
                e.permission_level,
                'DIRECT' as source,
                CAST(NULL AS STRING) as inheritance_path
            FROM {self.edges_table} e
            JOIN {self.vertices_table} v ON (e.src = v.id OR e.src = v.email OR e.src = v.name)
            WHERE e.dst = '{r_id}'
              AND e.permission_level IS NOT NULL
              AND v.node_type IN ({user_sp_types_sql})
              {run_filter}
              {run_filter_v}
        ),
        group_grants AS (
            SELECT
                g.id as principal_id,
                g.name as principal_name,
                CAST(NULL AS STRING) as principal_email,
                g.node_type as principal_type,
                e.permission_level,
                'DIRECT' as source,
                CAST(NULL AS STRING) as inheritance_path
            FROM {self.edges_table} e
            JOIN {self.vertices_table} g ON (e.src = g.id OR e.src = g.name)
            WHERE e.dst = '{r_id}'
              AND e.permission_level IS NOT NULL
              AND g.node_type IN ({group_types_sql})
              {run_filter}
              {run_filter_g}
        ),
        ownership AS (
            SELECT
                v.id as principal_id,
                COALESCE(v.display_name, v.name) as principal_name,
                v.email as principal_email,
                v.node_type as principal_type,
                'ALL PRIVILEGES' as permission_level,
                'OWNERSHIP' as source,
                CAST(NULL AS STRING) as inheritance_path
            FROM {self.vertices_table} v
            WHERE (v.id = '{r_owner}' OR v.email = '{r_owner}' OR v.name = '{r_owner}')
              AND v.node_type IN ({principal_types_sql})
              AND '{r_owner}' != ''
              {run_filter_v}
        ),
        parent_grants AS (
            SELECT
                v.id as principal_id,
                COALESCE(v.display_name, v.name) as principal_name,
                v.email as principal_email,
                v.node_type as principal_type,
                e.permission_level,
                'PARENT_INHERITANCE' as source,
                parent.name as inheritance_path
            FROM {self.edges_table} contains
            JOIN {self.vertices_table} parent ON contains.src = parent.id
            JOIN {self.edges_table} e ON e.dst = parent.id
            JOIN {self.vertices_table} v ON (e.src = v.id OR e.src = v.email OR e.src = v.name)
            WHERE contains.dst = '{r_id}'
              AND contains.relationship = 'Contains'
              AND e.permission_level IS NOT NULL
              AND v.node_type IN ({principal_types_sql})
              {run_filter_contains}
              {run_filter_parent}
              {run_filter}
              {run_filter_v}
        ),
        all_access AS (
            SELECT * FROM direct_grants
            UNION ALL
            SELECT * FROM group_grants
            UNION ALL
            SELECT * FROM ownership
            UNION ALL
            SELECT * FROM parent_grants
        ),
        deduplicated AS (
            -- Deduplicate by canonical ID (extract base ID from variants like ws_XXX_user:ID or account_user:ID)
            SELECT
                principal_id,
                principal_name,
                principal_email,
                principal_type,
                permission_level,
                source,
                inheritance_path,
                -- Extract canonical ID: take part after last ':', or whole ID if no ':'
                CASE
                    WHEN principal_id LIKE '%:%' THEN SPLIT(principal_id, ':')[1]
                    ELSE principal_id
                END as canonical_id,
                -- Prefer account-level principals over workspace-level
                ROW_NUMBER() OVER (
                    PARTITION BY
                        CASE
                            WHEN principal_id LIKE '%:%' THEN SPLIT(principal_id, ':')[1]
                            ELSE principal_id
                        END,
                        COALESCE(principal_email, principal_name),
                        permission_level,
                        source
                    ORDER BY
                        CASE principal_type
                            WHEN 'AccountUser' THEN 1
                            WHEN 'AccountGroup' THEN 1
                            WHEN 'AccountServicePrincipal' THEN 1
                            WHEN 'User' THEN 2
                            WHEN 'Group' THEN 2
                            WHEN 'ServicePrincipal' THEN 2
                            ELSE 3
                        END,
                        principal_id
                ) as rn
            FROM all_access
        )
        SELECT
            principal_id,
            principal_name,
            principal_email,
            principal_type,
            permission_level,
            source,
            inheritance_path
        FROM deduplicated
        WHERE rn = 1
        ORDER BY
            CASE source WHEN 'DIRECT' THEN 1 WHEN 'OWNERSHIP' THEN 2 ELSE 3 END,
            principal_type,
            principal_name
        """

        result = self.spark.sql(query)

        # Add group members
        if group_members_rows:
            group_members_df = self.spark.createDataFrame(group_members_rows, [
                "principal_id", "principal_name", "principal_email", "principal_type",
                "permission_level", "source", "inheritance_path"
            ])
            # Combine results
            combined = result.union(group_members_df)

            # Create temp view for deduplication
            combined.createOrReplaceTempView("combined_access")

            # Apply deduplication to final result
            result = self.spark.sql("""
                WITH deduplicated AS (
                    SELECT
                        principal_id,
                        principal_name,
                        principal_email,
                        principal_type,
                        permission_level,
                        source,
                        inheritance_path,
                        -- Extract canonical ID: take part after last ':', or whole ID if no ':'
                        CASE
                            WHEN principal_id LIKE '%:%' THEN SPLIT(principal_id, ':')[1]
                            ELSE principal_id
                        END as canonical_id,
                        -- Prefer account-level principals over workspace-level
                        ROW_NUMBER() OVER (
                            PARTITION BY
                                CASE
                                    WHEN principal_id LIKE '%:%' THEN SPLIT(principal_id, ':')[1]
                                    ELSE principal_id
                                END,
                                COALESCE(principal_email, principal_name),
                                permission_level,
                                source
                            ORDER BY
                                CASE principal_type
                                    WHEN 'AccountUser' THEN 1
                                    WHEN 'AccountGroup' THEN 1
                                    WHEN 'AccountServicePrincipal' THEN 1
                                    WHEN 'User' THEN 2
                                    WHEN 'Group' THEN 2
                                    WHEN 'ServicePrincipal' THEN 2
                                    ELSE 3
                                END,
                                principal_id
                        ) as rn
                    FROM combined_access
                )
                SELECT
                    principal_id,
                    principal_name,
                    principal_email,
                    principal_type,
                    permission_level,
                    source,
                    inheritance_path
                FROM deduplicated
                WHERE rn = 1
                ORDER BY
                    CASE source WHEN 'DIRECT' THEN 1 WHEN 'OWNERSHIP' THEN 2 WHEN 'GROUP' THEN 3 ELSE 4 END,
                    principal_type,
                    principal_name
            """)

        return result

    # =========================================================================
    # Escalation Analysis
    # =========================================================================

    def identify_escalation_targets(self):
        """
        Identify GROUPS and ROLES that confer privileged access when joined.

        Returns:
            DataFrame with columns: target_id, target_name, target_type,
                                   privileged_role, resource_name, risk_level
        """
        run_filter = f"AND v.run_id = '{self.run_id}'" if self.run_id else ""
        run_filter_m = f"AND m.run_id = '{self.run_id}'" if self.run_id else ""
        run_filter_c = f"AND c.run_id = '{self.run_id}'" if self.run_id else ""

        query = f"""
        WITH
        -- Account-level 'admins' group (by node_type OR id prefix) or groups with 'account admin' in name
        account_admin_groups AS (
            SELECT
                v.id as target_id,
                v.name as target_name,
                v.node_type as target_type,
                'Account Admin' as privileged_role,
                v.name as resource_name,
                'CRITICAL' as risk_level
            FROM {self.vertices_table} v
            WHERE v.node_type IN ('Group', 'AccountGroup')
              AND (((v.node_type = 'AccountGroup' OR v.id LIKE 'account_group:%') AND LOWER(v.name) = 'admins')
                   OR LOWER(v.name) = 'account admins'
                   OR LOWER(v.name) LIKE '%account%admin%')
              {run_filter}
        ),
        metastore_admin_groups AS (
            SELECT
                v.id as target_id,
                v.name as target_name,
                v.node_type as target_type,
                'Metastore Admin' as privileged_role,
                v.name as resource_name,
                'CRITICAL' as risk_level
            FROM {self.vertices_table} v
            WHERE v.node_type IN ('Group', 'AccountGroup')
              AND LOWER(v.name) LIKE '%metastore%admin%'
              {run_filter}
            UNION ALL
            SELECT
                m.id as target_id,
                m.name as target_name,
                m.node_type as target_type,
                'Metastore Admin' as privileged_role,
                m.name as resource_name,
                'CRITICAL' as risk_level
            FROM {self.vertices_table} m
            WHERE m.node_type = 'Metastore'
              {run_filter_m}
        ),
        -- Workspace-level 'admins' group (not account-level) or groups with 'workspace admin' in name
        workspace_admin_groups AS (
            SELECT
                v.id as target_id,
                v.name as target_name,
                v.node_type as target_type,
                'Workspace Admin' as privileged_role,
                v.name as resource_name,
                'HIGH' as risk_level
            FROM {self.vertices_table} v
            WHERE v.node_type IN ('Group', 'AccountGroup')
              AND ((v.node_type = 'Group' AND v.id NOT LIKE 'account_group:%' AND LOWER(v.name) = 'admins')
                   OR LOWER(v.name) LIKE '%workspace%admin%'
                   OR LOWER(v.name) = 'workspace admins')
              {run_filter}
        ),
        catalog_owner_targets AS (
            SELECT
                c.id as target_id,
                c.name as target_name,
                c.node_type as target_type,
                'Catalog Owner' as privileged_role,
                c.name as resource_name,
                'HIGH' as risk_level
            FROM {self.vertices_table} c
            WHERE c.node_type = 'Catalog'
              {run_filter_c}
        )
        SELECT DISTINCT * FROM (
            SELECT * FROM account_admin_groups
            UNION ALL
            SELECT * FROM metastore_admin_groups
            UNION ALL
            SELECT * FROM workspace_admin_groups
            UNION ALL
            SELECT * FROM catalog_owner_targets
        )
        ORDER BY
            CASE risk_level WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END,
            privileged_role,
            target_name
        """

        return self.spark.sql(query)

    def identify_privileged_principals(self):
        """
        Identify all principals that ALREADY hold privileged roles.

        Returns:
            DataFrame with columns: principal_id, principal_name, principal_type,
                                   privileged_role, resource_name, risk_level
        """
        run_filter = f"AND e.run_id = '{self.run_id}'" if self.run_id else ""
        run_filter_v = f"AND v.run_id = '{self.run_id}'" if self.run_id else ""
        run_filter_c = f"AND c.run_id = '{self.run_id}'" if self.run_id else ""

        principal_types_sql = ','.join([f"'{t}'" for t in PRINCIPAL_TYPES])

        query = f"""
        WITH
        -- Account Admins via direct AccountAdmin edge (from roles field in SCIM API)
        account_admins_direct AS (
            SELECT
                v.id as principal_id,
                COALESCE(v.display_name, v.name, v.email) as principal_name,
                v.node_type as principal_type,
                'Account Admin' as privileged_role,
                'Direct Role Assignment' as resource_name,
                'CRITICAL' as risk_level
            FROM {self.edges_table} e
            JOIN {self.vertices_table} v ON e.src = v.id
            WHERE e.relationship = 'AccountAdmin'
              AND v.node_type IN ({principal_types_sql})
              {run_filter}
              {run_filter_v}
        ),
        -- Account-level 'admins' group (by node_type OR id prefix) or groups with 'account admin' in name
        account_admins_group AS (
            SELECT
                v.id as principal_id,
                COALESCE(v.display_name, v.name, v.email) as principal_name,
                v.node_type as principal_type,
                'Account Admin' as privileged_role,
                g.name as resource_name,
                'CRITICAL' as risk_level
            FROM {self.edges_table} e
            JOIN {self.vertices_table} v ON e.src = v.id
            JOIN {self.vertices_table} g ON e.dst = g.id
            WHERE e.relationship = 'MemberOf'
              AND g.node_type IN ('Group', 'AccountGroup')
              AND (((g.node_type = 'AccountGroup' OR g.id LIKE 'account_group:%') AND LOWER(g.name) = 'admins')
                   OR LOWER(g.name) = 'account admins'
                   OR LOWER(g.name) LIKE '%account%admin%')
              {run_filter}
        ),
        metastore_admins AS (
            SELECT
                v.id as principal_id,
                COALESCE(v.display_name, v.name, v.email) as principal_name,
                v.node_type as principal_type,
                'Metastore Admin' as privileged_role,
                COALESCE(g.name, r.name, 'Metastore') as resource_name,
                'CRITICAL' as risk_level
            FROM {self.edges_table} e
            JOIN {self.vertices_table} v ON e.src = v.id
            LEFT JOIN {self.vertices_table} g ON e.dst = g.id AND g.node_type IN ('Group', 'AccountGroup')
            LEFT JOIN {self.vertices_table} r ON e.dst = r.id AND r.node_type = 'Metastore'
            WHERE (
                (e.relationship = 'MemberOf' AND LOWER(g.name) LIKE '%metastore%admin%')
                OR
                (e.permission_level IN ('MANAGE', 'ALL PRIVILEGES', 'ALL_PRIVILEGES') AND r.node_type = 'Metastore')
            )
            {run_filter}
        ),
        -- Workspace-level 'admins' group (not account-level) or groups with 'workspace admin' in name
        workspace_admins AS (
            SELECT
                v.id as principal_id,
                COALESCE(v.display_name, v.name, v.email) as principal_name,
                v.node_type as principal_type,
                'Workspace Admin' as privileged_role,
                g.name as resource_name,
                'HIGH' as risk_level
            FROM {self.edges_table} e
            JOIN {self.vertices_table} v ON e.src = v.id
            JOIN {self.vertices_table} g ON e.dst = g.id
            WHERE e.relationship = 'MemberOf'
              AND g.node_type IN ('Group', 'AccountGroup')
              AND ((g.node_type = 'Group' AND g.id NOT LIKE 'account_group:%' AND LOWER(g.name) = 'admins')
                   OR LOWER(g.name) LIKE '%workspace%admin%'
                   OR LOWER(g.name) = 'workspace admins')
              {run_filter}
        ),
        catalog_owners AS (
            SELECT
                v.id as principal_id,
                COALESCE(v.display_name, v.name, v.email) as principal_name,
                v.node_type as principal_type,
                'Catalog Owner' as privileged_role,
                c.name as resource_name,
                'HIGH' as risk_level
            FROM {self.vertices_table} c
            JOIN {self.vertices_table} v ON (c.owner = v.id OR c.owner = v.email OR c.owner = v.name)
            WHERE c.node_type = 'Catalog'
              AND v.node_type IN ({principal_types_sql})
              {run_filter_c}
              {run_filter_v}
        )
        SELECT DISTINCT * FROM (
            SELECT * FROM account_admins_direct
            UNION ALL
            SELECT * FROM account_admins_group
            UNION ALL
            SELECT * FROM metastore_admins
            UNION ALL
            SELECT * FROM workspace_admins
            UNION ALL
            SELECT * FROM catalog_owners
        )
        ORDER BY
            CASE risk_level WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END,
            privileged_role,
            principal_name
        """

        return self.spark.sql(query)

    # =========================================================================
    # Advanced Reports
    # =========================================================================

    def find_orphaned_resources(self):
        """
        Find resources with no explicit grants (only accessible via ownership or inheritance).

        Returns:
            DataFrame with orphaned resources (id, name, node_type, owner)
        """
        run_filter = f"AND v.run_id = '{self.run_id}'" if self.run_id else ""
        run_filter_e = f"WHERE run_id = '{self.run_id}'" if self.run_id else ""

        query = f"""
        WITH granted_resources AS (
            SELECT DISTINCT dst as resource_id
            FROM {self.edges_table}
            WHERE permission_level IS NOT NULL
            {f"AND run_id = '{self.run_id}'" if self.run_id else ""}
        )
        SELECT
            v.id,
            v.name,
            v.node_type,
            v.owner
        FROM {self.vertices_table} v
        LEFT JOIN granted_resources gr ON v.id = gr.resource_id
        WHERE gr.resource_id IS NULL
          AND v.node_type IN ('Table', 'View', 'Schema', 'Catalog', 'Volume', 'Function')
          {run_filter}
        ORDER BY v.node_type, v.name
        """

        return self.spark.sql(query)

    def find_isolated_principals(self):
        """
        Find principals with minimal connections (potentially orphaned accounts).

        A principal is considered isolated if they:
        - Belong to no groups
        - Have no direct permissions
        - Own no resources

        Returns:
            DataFrame with isolated principals and their connectivity metrics
        """
        from pyspark.sql import functions as F

        run_filter = f"AND run_id = '{self.run_id}'" if self.run_id else ""

        # Get all principals
        principals = self.vertices.filter(
            F.col("node_type").isin(USER_SP_TYPES)
        ).select("id", "name", "email", "node_type", "display_name")

        # Count group memberships
        group_memberships = self.edges.filter(
            F.col("relationship") == "MemberOf"
        ).groupBy("src").agg(F.count("*").alias("group_count"))

        # Count direct permissions
        direct_permissions = self.edges.filter(
            F.col("permission_level").isNotNull()
        ).groupBy("src").agg(F.count("*").alias("permission_count"))

        # Count owned resources
        owned_resources = self.vertices.filter(
            F.col("owner").isNotNull()
        ).groupBy("owner").agg(F.count("*").alias("owned_count"))

        # Combine metrics
        result = (
            principals
            .join(group_memberships, principals.id == group_memberships.src, "left")
            .join(direct_permissions, principals.id == direct_permissions.src, "left")
            .join(owned_resources,
                  (principals.email == owned_resources.owner) | (principals.id == owned_resources.owner),
                  "left")
            .select(
                principals.id,
                F.coalesce(principals.display_name, principals.name).alias("name"),
                principals.email,
                principals.node_type,
                F.coalesce(F.col("group_count"), F.lit(0)).alias("groups"),
                F.coalesce(F.col("permission_count"), F.lit(0)).alias("permissions"),
                F.coalesce(F.col("owned_count"), F.lit(0)).alias("owned")
            )
            .withColumn(
                "connectivity_score",
                F.col("groups") * 5 + F.col("permissions") + F.col("owned") * 2
            )
            .withColumn(
                "isolation_risk",
                F.when(
                    (F.col("groups") == 0) & (F.col("permissions") == 0) & (F.col("owned") == 0),
                    "CRITICAL"
                ).when(
                    F.col("connectivity_score") < 5,
                    "HIGH"
                ).when(
                    F.col("connectivity_score") < 10,
                    "MEDIUM"
                ).otherwise("LOW")
            )
            .orderBy("connectivity_score")
        )

        return result

    def find_over_privileged_principals(self):
        """
        Identify principals with excessive permissions.

        Criteria:
        - ALL PRIVILEGES on multiple catalogs
        - MANAGE on many resources
        - Broad access patterns

        Returns:
            DataFrame with over-privileged principals
        """
        from pyspark.sql import functions as F

        run_filter = f"AND e.run_id = '{self.run_id}'" if self.run_id else ""
        run_filter_v = f"AND v.run_id = '{self.run_id}'" if self.run_id else ""
        run_filter_r = f"AND r.run_id = '{self.run_id}'" if self.run_id else ""

        query = f"""
        WITH permission_counts AS (
            SELECT
                v.id as principal_id,
                COALESCE(v.display_name, v.name) as principal_name,
                v.node_type as principal_type,
                COUNT(DISTINCT e.dst) as total_resources,
                COUNT(DISTINCT CASE WHEN r.node_type = 'Catalog' THEN r.id END) as catalog_count,
                COUNT(DISTINCT CASE WHEN r.node_type = 'Schema' THEN r.id END) as schema_count,
                COUNT(DISTINCT CASE WHEN r.node_type = 'Table' THEN r.id END) as table_count,
                COUNT(DISTINCT CASE WHEN e.permission_level IN ('ALL PRIVILEGES', 'ALL_PRIVILEGES', 'MANAGE') THEN r.id END) as admin_grants,
                COLLECT_SET(DISTINCT e.permission_level) as permission_types
            FROM {self.edges_table} e
            JOIN {self.vertices_table} v ON (e.src = v.id OR e.src = v.email OR e.src = v.name)
            JOIN {self.vertices_table} r ON e.dst = r.id
            WHERE e.permission_level IS NOT NULL
              AND v.node_type IN ('User', 'ServicePrincipal')
              {run_filter}
              {run_filter_v}
              {run_filter_r}
            GROUP BY v.id, v.display_name, v.name, v.node_type
        )
        SELECT
            *,
            CASE
                WHEN catalog_count >= 3 OR admin_grants >= 10 THEN 'HIGH'
                WHEN catalog_count >= 1 OR admin_grants >= 5 THEN 'MEDIUM'
                ELSE 'LOW'
            END as risk_level
        FROM permission_counts
        WHERE admin_grants > 0 OR catalog_count > 0
        ORDER BY admin_grants DESC, catalog_count DESC
        """

        return self.spark.sql(query)

    def get_summary_statistics(self):
        """
        Get summary statistics for the security graph.

        Returns:
            Dict with various statistics about the graph
        """
        from pyspark.sql import functions as F

        # Vertex counts by type
        vertex_counts = self.vertices.groupBy("node_type").count().collect()
        vertex_summary = {row["node_type"]: row["count"] for row in vertex_counts}

        # Edge counts by relationship
        edge_counts = self.edges.groupBy("relationship").count().collect()
        edge_summary = {row["relationship"]: row["count"] for row in edge_counts}

        # Permission grants by type
        permission_counts = self.edges.filter(
            F.col("permission_level").isNotNull()
        ).groupBy("permission_level").count().collect()
        permission_summary = {row["permission_level"]: row["count"] for row in permission_counts}

        # Total counts
        total_vertices = self.vertices.count()
        total_edges = self.edges.count()
        total_permissions = sum(permission_summary.values())

        # Principal counts
        principal_count = self.vertices.filter(
            F.col("node_type").isin(PRINCIPAL_TYPES)
        ).count()

        user_count = self.vertices.filter(
            F.col("node_type").isin(["User", "AccountUser"])
        ).count()

        group_count = self.vertices.filter(
            F.col("node_type").isin(GROUP_TYPES)
        ).count()

        sp_count = self.vertices.filter(
            F.col("node_type").isin(["ServicePrincipal", "AccountServicePrincipal"])
        ).count()

        return {
            "total_vertices": total_vertices,
            "total_edges": total_edges,
            "total_permissions": total_permissions,
            "principal_count": principal_count,
            "user_count": user_count,
            "group_count": group_count,
            "service_principal_count": sp_count,
            "vertices_by_type": vertex_summary,
            "edges_by_relationship": edge_summary,
            "permissions_by_type": permission_summary
        }

    # =========================================================================
    # NetworkX Graph Building
    # =========================================================================

    def build_networkx_graph(self):
        """
        Build a NetworkX DiGraph from the security graph data.

        Returns:
            networkx.DiGraph with vertices and edges
        """
        import networkx as nx

        if self._nx_graph is not None:
            return self._nx_graph

        G = nx.DiGraph()

        # Add vertices
        for row in self.vertices.collect():
            G.add_node(row["id"], **{
                "node_type": row["node_type"],
                "name": row["name"],
                "display_name": row["display_name"],
                "email": row["email"],
                "owner": row["owner"]
            })

        # Add edges
        for row in self.edges.collect():
            G.add_edge(row["src"], row["dst"], **{
                "relationship": row["relationship"],
                "permission_level": row["permission_level"],
                "inherited": row["inherited"]
            })

        self._nx_graph = G
        return G
