"""
Recursive Permissions Resolver for Databricks

Inspired by ac-lineage project's approach to recursive permission visualization.
This module provides utilities to resolve and trace permission inheritance chains
in Unity Catalog and workspace resources.

Key Capabilities:
- Trace permission origins (direct vs inherited)
- Resolve recursive permissions through group membership
- Calculate effective permissions from multiple sources
- Build permission inheritance trees
- Identify permission conflicts and redundancies
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

__all__ = [
    "PermissionSource",
    "PermissionGrant",
    "EffectivePermissions",
    "PermissionsResolver",
]


class PermissionSource(Enum):
    """Source of a permission grant"""
    DIRECT = "direct"                    # Directly granted to principal
    GROUP_MEMBERSHIP = "group"           # Inherited via group membership
    OWNERSHIP = "ownership"              # Derived from ownership
    CONTAINMENT = "containment"          # Inherited via parent resource
    CATALOG_GRANT = "catalog_grant"      # Granted at catalog level
    SCHEMA_GRANT = "schema_grant"        # Granted at schema level


@dataclass
class PermissionGrant:
    """Represents a single permission grant with its source"""
    principal_id: str
    principal_name: str
    principal_type: str
    resource_id: str
    resource_name: str
    resource_type: str
    permission_level: str
    source: PermissionSource
    source_path: List[str]  # Chain of resources/groups that granted this
    is_inherited: bool
    granted_by: Optional[str] = None  # ID of the granting entity (group, parent, etc.)


@dataclass
class EffectivePermissions:
    """Effective permissions for a principal on a resource"""
    principal_id: str
    principal_name: str
    resource_id: str
    resource_name: str
    permissions: List[PermissionGrant]
    highest_permission: str
    has_conflicts: bool
    redundant_grants: List[PermissionGrant]


class PermissionsResolver:
    """
    Resolves recursive permissions by tracing inheritance chains
    Similar to ac-lineage's recursive permission analysis
    """
    
    def __init__(self, vertices_df, edges_df, spark):
        """
        Initialize with graph data
        
        Args:
            vertices_df: DataFrame of graph vertices
            edges_df: DataFrame of graph edges
            spark: SparkSession
        """
        self.vertices = vertices_df
        self.edges = edges_df
        self.spark = spark
        
        # Permission hierarchy for Unity Catalog
        self.permission_hierarchy = {
            'ALL_PRIVILEGES': 5,
            'CAN_MANAGE': 4,
            'MODIFY': 3,
            'SELECT': 2,
            'CAN_USE': 1,
            'IS_OWNER': 6  # Special case - ownership
        }
    
    def get_effective_permissions(self, principal_id: str, resource_id: str) -> EffectivePermissions:
        """
        Calculate effective permissions for a principal on a resource.
        Considers:
        1. Direct grants
        2. Group membership grants
        3. Ownership-based permissions
        4. Parent resource grants (containment)
        
        Args:
            principal_id: ID of the principal (user, service principal)
            resource_id: ID of the resource
            
        Returns:
            EffectivePermissions object with all permission sources
        """
        from pyspark.sql import functions as F
        
        all_grants = []
        
        # Get principal info
        principal = self.vertices.filter(F.col("id") == principal_id).first()
        if not principal:
            raise ValueError(f"Principal {principal_id} not found")
        
        # Get resource info
        resource = self.vertices.filter(F.col("id") == resource_id).first()
        if not resource:
            raise ValueError(f"Resource {resource_id} not found")
        
        # 1. Direct permissions
        direct_perms = self._get_direct_permissions(principal_id, resource_id)
        all_grants.extend(direct_perms)
        
        # 2. Group membership permissions
        group_perms = self._get_group_permissions(principal_id, resource_id)
        all_grants.extend(group_perms)
        
        # 3. Ownership-based permissions
        ownership_perms = self._get_ownership_permissions(principal_id, resource_id)
        all_grants.extend(ownership_perms)
        
        # 4. Parent resource permissions (containment inheritance)
        parent_perms = self._get_parent_permissions(principal_id, resource_id)
        all_grants.extend(parent_perms)
        
        # Determine highest permission level
        highest = self._get_highest_permission(all_grants)
        
        # Detect conflicts and redundancies
        has_conflicts = self._has_permission_conflicts(all_grants)
        redundant = self._find_redundant_grants(all_grants)
        
        return EffectivePermissions(
            principal_id=principal_id,
            principal_name=principal.name,
            resource_id=resource_id,
            resource_name=resource.name,
            permissions=all_grants,
            highest_permission=highest,
            has_conflicts=has_conflicts,
            redundant_grants=redundant
        )
    
    def trace_permission_origin(self, principal_id: str, resource_id: str, 
                               permission_level: str) -> List[List[str]]:
        """
        Trace all paths that grant a specific permission.
        Returns a list of permission chains showing how access is granted.
        
        Args:
            principal_id: ID of the principal
            resource_id: ID of the resource
            permission_level: Specific permission to trace
            
        Returns:
            List of paths, where each path is a list of node IDs
        """
        from pyspark.sql import functions as F
        
        paths = []
        
        # Direct path
        direct_edge = self.edges.filter(
            (F.col("src") == principal_id) &
            (F.col("dst") == resource_id) &
            (F.col("permission_level") == permission_level)
        ).first()
        
        if direct_edge:
            paths.append([principal_id, resource_id])
        
        # Paths through groups
        group_paths = self._trace_group_paths(principal_id, resource_id, permission_level)
        paths.extend(group_paths)
        
        # Paths through parent resources
        parent_paths = self._trace_parent_paths(principal_id, resource_id, permission_level)
        paths.extend(parent_paths)
        
        return paths
    
    def build_permission_tree(self, resource_id: str, max_depth: int = 5) -> Dict:
        """
        Build a tree showing all principals with access to a resource
        and the inheritance chain for each.
        
        Similar to ac-lineage's recursive visualization approach.
        
        Args:
            resource_id: ID of the resource
            max_depth: Maximum depth to traverse
            
        Returns:
            Nested dictionary representing the permission tree
        """
        from pyspark.sql import functions as F
        
        resource = self.vertices.filter(F.col("id") == resource_id).first()
        if not resource:
            return {}
        
        tree = {
            'id': resource_id,
            'name': resource.name,
            'type': resource.node_type,
            'principals': []
        }
        
        # Get all principals with direct access
        direct_access = self.edges.filter(
            (F.col("dst") == resource_id) &
            (F.col("permission_level").isNotNull())
        ).collect()
        
        for edge in direct_access:
            principal = self.vertices.filter(F.col("id") == edge.src).first()
            if principal:
                principal_node = {
                    'id': edge.src,
                    'name': principal.name,
                    'type': principal.node_type,
                    'permission': edge.permission_level,
                    'source': 'direct',
                    'children': []
                }
                
                # If this is a group, recursively get members
                if principal.node_type == 'Group':
                    members = self._get_group_members_recursive(edge.src, depth=0, max_depth=max_depth)
                    principal_node['children'] = members
                
                tree['principals'].append(principal_node)
        
        return tree
    
    def analyze_permission_redundancies(self, principal_id: str) -> List[Dict]:
        """
        Find cases where a principal has redundant permission grants.
        E.g., both direct and group-based access to the same resource.
        
        Args:
            principal_id: ID of the principal to analyze
            
        Returns:
            List of redundancy findings
        """
        from pyspark.sql import functions as F
        
        redundancies = []
        
        # Get all resources the principal has access to
        accessible_resources = self.edges.filter(
            F.col("src") == principal_id
        ).select("dst").distinct().collect()
        
        for row in accessible_resources:
            resource_id = row.dst
            
            # Get effective permissions
            try:
                effective = self.get_effective_permissions(principal_id, resource_id)
                
                if effective.redundant_grants:
                    redundancies.append({
                        'resource_id': resource_id,
                        'resource_name': effective.resource_name,
                        'redundant_count': len(effective.redundant_grants),
                        'grants': effective.redundant_grants
                    })
            except ValueError:
                continue
        
        return redundancies
    
    def _get_direct_permissions(self, principal_id: str, resource_id: str) -> List[PermissionGrant]:
        """Get direct permission grants"""
        from pyspark.sql import functions as F
        
        grants = []
        
        direct_edges = self.edges.filter(
            (F.col("src") == principal_id) &
            (F.col("dst") == resource_id) &
            (F.col("permission_level").isNotNull())
        ).collect()
        
        for edge in direct_edges:
            principal = self.vertices.filter(F.col("id") == principal_id).first()
            resource = self.vertices.filter(F.col("id") == resource_id).first()
            
            grants.append(PermissionGrant(
                principal_id=principal_id,
                principal_name=principal.name if principal else "Unknown",
                principal_type=principal.node_type if principal else "Unknown",
                resource_id=resource_id,
                resource_name=resource.name if resource else "Unknown",
                resource_type=resource.node_type if resource else "Unknown",
                permission_level=edge.permission_level,
                source=PermissionSource.DIRECT,
                source_path=[principal_id, resource_id],
                is_inherited=edge.inherited if hasattr(edge, 'inherited') else False
            ))
        
        return grants
    
    def _get_group_permissions(self, principal_id: str, resource_id: str) -> List[PermissionGrant]:
        """Get permissions inherited through group membership"""
        from pyspark.sql import functions as F
        
        grants = []
        
        # Find groups the principal is a member of
        member_of = self.edges.filter(
            (F.col("src") == principal_id) &
            (F.col("relationship") == "MemberOf")
        ).collect()
        
        for membership in member_of:
            group_id = membership.dst
            
            # Check if group has access to resource
            group_access = self.edges.filter(
                (F.col("src") == group_id) &
                (F.col("dst") == resource_id) &
                (F.col("permission_level").isNotNull())
            ).collect()
            
            for access in group_access:
                principal = self.vertices.filter(F.col("id") == principal_id).first()
                group = self.vertices.filter(F.col("id") == group_id).first()
                resource = self.vertices.filter(F.col("id") == resource_id).first()
                
                grants.append(PermissionGrant(
                    principal_id=principal_id,
                    principal_name=principal.name if principal else "Unknown",
                    principal_type=principal.node_type if principal else "Unknown",
                    resource_id=resource_id,
                    resource_name=resource.name if resource else "Unknown",
                    resource_type=resource.node_type if resource else "Unknown",
                    permission_level=access.permission_level,
                    source=PermissionSource.GROUP_MEMBERSHIP,
                    source_path=[principal_id, group_id, resource_id],
                    is_inherited=True,
                    granted_by=group_id
                ))
        
        return grants
    
    def _get_ownership_permissions(self, principal_id: str, resource_id: str) -> List[PermissionGrant]:
        """Get permissions derived from resource ownership"""
        from pyspark.sql import functions as F
        
        grants = []
        
        # Check if principal owns the resource
        resource = self.vertices.filter(F.col("id") == resource_id).first()
        
        if resource and hasattr(resource, 'owner') and resource.owner == principal_id:
            principal = self.vertices.filter(F.col("id") == principal_id).first()
            
            grants.append(PermissionGrant(
                principal_id=principal_id,
                principal_name=principal.name if principal else "Unknown",
                principal_type=principal.node_type if principal else "Unknown",
                resource_id=resource_id,
                resource_name=resource.name,
                resource_type=resource.node_type,
                permission_level="IS_OWNER",
                source=PermissionSource.OWNERSHIP,
                source_path=[principal_id, resource_id],
                is_inherited=False
            ))
        
        return grants
    
    def _get_parent_permissions(self, principal_id: str, resource_id: str) -> List[PermissionGrant]:
        """Get permissions inherited from parent resources (catalog/schema)"""
        from pyspark.sql import functions as F
        
        grants = []
        
        # Find parent resource (via Contains relationship)
        parent_edges = self.edges.filter(
            (F.col("dst") == resource_id) &
            (F.col("relationship") == "Contains")
        ).collect()
        
        for parent_edge in parent_edges:
            parent_id = parent_edge.src
            
            # Check if principal has access to parent
            parent_access = self.edges.filter(
                (F.col("src") == principal_id) &
                (F.col("dst") == parent_id) &
                (F.col("permission_level").isNotNull())
            ).collect()
            
            for access in parent_access:
                principal = self.vertices.filter(F.col("id") == principal_id).first()
                parent = self.vertices.filter(F.col("id") == parent_id).first()
                resource = self.vertices.filter(F.col("id") == resource_id).first()
                
                grants.append(PermissionGrant(
                    principal_id=principal_id,
                    principal_name=principal.name if principal else "Unknown",
                    principal_type=principal.node_type if principal else "Unknown",
                    resource_id=resource_id,
                    resource_name=resource.name if resource else "Unknown",
                    resource_type=resource.node_type if resource else "Unknown",
                    permission_level=access.permission_level,
                    source=PermissionSource.CONTAINMENT,
                    source_path=[principal_id, parent_id, resource_id],
                    is_inherited=True,
                    granted_by=parent_id
                ))
        
        return grants
    
    def _get_highest_permission(self, grants: List[PermissionGrant]) -> str:
        """Determine the highest permission level from a list of grants"""
        if not grants:
            return "NONE"
        
        highest_level = 0
        highest_perm = "NONE"
        
        for grant in grants:
            level = self.permission_hierarchy.get(grant.permission_level, 0)
            if level > highest_level:
                highest_level = level
                highest_perm = grant.permission_level
        
        return highest_perm
    
    def _has_permission_conflicts(self, grants: List[PermissionGrant]) -> bool:
        """Check if there are conflicting permission grants"""
        # Conflict exists if same resource has multiple different permission levels
        permission_levels = set(g.permission_level for g in grants)
        return len(permission_levels) > 1
    
    def _find_redundant_grants(self, grants: List[PermissionGrant]) -> List[PermissionGrant]:
        """Find redundant permission grants"""
        redundant = []
        
        # Group by permission level
        by_level = {}
        for grant in grants:
            if grant.permission_level not in by_level:
                by_level[grant.permission_level] = []
            by_level[grant.permission_level].append(grant)
        
        # If same permission from multiple sources, mark as redundant
        for level, level_grants in by_level.items():
            if len(level_grants) > 1:
                # Keep direct grant, mark others as redundant
                non_direct = [g for g in level_grants if g.source != PermissionSource.DIRECT]
                redundant.extend(non_direct)
        
        return redundant
    
    def _trace_group_paths(
        self,
        principal_id: str,
        resource_id: str,
        permission_level: str
    ) -> List[List[str]]:
        """
        Trace permission paths through group memberships.

        Args:
            principal_id: ID of the principal
            resource_id: ID of the resource
            permission_level: Specific permission to trace

        Returns:
            List of paths, where each path is a list of node IDs
            showing the chain: [principal -> group -> ... -> resource]
        """
        from pyspark.sql import functions as F

        paths = []

        # Find groups the principal is a member of
        member_of = self.edges.filter(
            (F.col("src") == principal_id) &
            (F.col("relationship") == "MemberOf")
        ).collect()

        for membership in member_of:
            group_id = membership.dst

            # Check if group has the specified permission on resource
            group_access = self.edges.filter(
                (F.col("src") == group_id) &
                (F.col("dst") == resource_id) &
                (F.col("permission_level") == permission_level)
            ).first()

            if group_access:
                paths.append([principal_id, group_id, resource_id])

        return paths

    def _trace_parent_paths(
        self,
        principal_id: str,
        resource_id: str,
        permission_level: str
    ) -> List[List[str]]:
        """
        Trace permission paths through parent resources (containment hierarchy).

        Args:
            principal_id: ID of the principal
            resource_id: ID of the resource
            permission_level: Specific permission to trace

        Returns:
            List of paths, where each path is a list of node IDs
            showing the chain: [principal -> parent_resource -> ... -> resource]
        """
        from pyspark.sql import functions as F

        paths = []

        # Find parent resources via Contains relationship
        parent_edges = self.edges.filter(
            (F.col("dst") == resource_id) &
            (F.col("relationship") == "Contains")
        ).collect()

        for parent_edge in parent_edges:
            parent_id = parent_edge.src

            # Check if principal has the specified permission on parent
            parent_access = self.edges.filter(
                (F.col("src") == principal_id) &
                (F.col("dst") == parent_id) &
                (F.col("permission_level") == permission_level)
            ).first()

            if parent_access:
                paths.append([principal_id, parent_id, resource_id])

        return paths
    
    def _get_group_members_recursive(self, group_id: str, depth: int = 0, 
                                    max_depth: int = 5) -> List[Dict]:
        """Recursively get all members of a group"""
        from pyspark.sql import functions as F
        
        if depth >= max_depth:
            return []
        
        members = []
        
        # Get direct members
        member_edges = self.edges.filter(
            (F.col("dst") == group_id) &
            (F.col("relationship") == "HasMember")
        ).collect()
        
        for edge in member_edges:
            member = self.vertices.filter(F.col("id") == edge.src).first()
            if member:
                member_node = {
                    'id': edge.src,
                    'name': member.name,
                    'type': member.node_type,
                    'children': []
                }
                
                # If member is a group, recurse
                if member.node_type == 'Group':
                    member_node['children'] = self._get_group_members_recursive(
                        edge.src, depth + 1, max_depth
                    )
                
                members.append(member_node)
        
        return members

