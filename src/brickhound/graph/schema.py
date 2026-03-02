"""
Graph schema definitions for BrickHound

Defines the structure of vertices (nodes) and edges (relationships)
stored in Delta Lake for GraphFrames processing.
"""

from enum import Enum
from typing import Dict, Any, List
from dataclasses import dataclass, field

__all__ = ["NodeType", "EdgeType", "GraphSchema", "AttackPath"]


class NodeType(str, Enum):
    """Types of nodes in the Databricks privilege graph"""

    # Identity nodes (workspace-level)
    USER = "User"
    GROUP = "Group"
    SERVICE_PRINCIPAL = "ServicePrincipal"

    # Identity nodes (account-level)
    ACCOUNT_USER = "AccountUser"
    ACCOUNT_GROUP = "AccountGroup"
    ACCOUNT_SERVICE_PRINCIPAL = "AccountServicePrincipal"

    # Compute nodes
    CLUSTER = "Cluster"
    INSTANCE_POOL = "InstancePool"
    CLUSTER_POLICY = "ClusterPolicy"
    GLOBAL_INIT_SCRIPT = "GlobalInitScript"

    # Data & Analytics nodes
    CATALOG = "Catalog"
    SCHEMA = "Schema"
    TABLE = "Table"
    VIEW = "View"
    VOLUME = "Volume"
    FUNCTION = "Function"
    WAREHOUSE = "Warehouse"
    METASTORE = "Metastore"
    EXTERNAL_LOCATION = "ExternalLocation"
    STORAGE_CREDENTIAL = "StorageCredential"
    CONNECTION = "Connection"

    # AI/ML nodes
    SERVING_ENDPOINT = "ServingEndpoint"
    VECTOR_SEARCH_ENDPOINT = "VectorSearchEndpoint"
    VECTOR_SEARCH_INDEX = "VectorSearchIndex"
    REGISTERED_MODEL = "RegisteredModel"
    MODEL_VERSION = "ModelVersion"
    EXPERIMENT = "Experiment"

    # Analytics/BI nodes
    DASHBOARD = "Dashboard"
    QUERY = "Query"
    ALERT = "Alert"

    # Development nodes
    NOTEBOOK = "Notebook"
    DIRECTORY = "Directory"
    REPO = "Repo"
    LIBRARY = "Library"

    # Orchestration nodes
    JOB = "Job"
    PIPELINE = "Pipeline"

    # Security nodes
    SECRET_SCOPE = "SecretScope"
    SECRET = "Secret"
    TOKEN = "Token"
    IP_ACCESS_LIST = "IpAccessList"

    # Apps
    APP = "App"

    # Workspace/Account nodes
    WORKSPACE = "Workspace"
    ACCOUNT = "Account"


class EdgeType(str, Enum):
    """Types of edges (relationships) in the privilege graph"""

    # Group membership
    MEMBER_OF = "MemberOf"  # User/SP -> Group
    HAS_MEMBER = "HasMember"  # Group -> User/SP

    # Workspace/Account access
    WORKSPACE_ACCESS = "WorkspaceAccess"  # Principal -> Workspace
    ACCOUNT_ADMIN = "AccountAdmin"  # Principal -> Account (admin role)

    # Permissions (workspace-level)
    CAN_USE = "CanUse"
    CAN_READ = "CanRead"
    CAN_WRITE = "CanWrite"
    CAN_MANAGE = "CanManage"
    CAN_RESTART = "CanRestart"
    CAN_ATTACH_TO = "CanAttachTo"
    CAN_EDIT = "CanEdit"
    CAN_RUN = "CanRun"
    CAN_VIEW = "CanView"
    CAN_QUERY = "CanQuery"

    # Unity Catalog grants
    ALL_PRIVILEGES = "AllPrivileges"
    SELECT = "Select"
    MODIFY = "Modify"
    CREATE = "Create"
    USAGE = "Usage"
    EXECUTE = "Execute"
    READ_VOLUME = "ReadVolume"
    WRITE_VOLUME = "WriteVolume"
    CREATE_CATALOG = "CreateCatalog"
    CREATE_SCHEMA = "CreateSchema"
    CREATE_TABLE = "CreateTable"
    CREATE_VOLUME = "CreateVolume"
    CREATE_FUNCTION = "CreateFunction"
    CREATE_MODEL = "CreateModel"
    CREATE_EXTERNAL_LOCATION = "CreateExternalLocation"
    CREATE_STORAGE_CREDENTIAL = "CreateStorageCredential"
    CREATE_CONNECTION = "CreateConnection"
    READ_FILES = "ReadFiles"
    WRITE_FILES = "WriteFiles"
    APPLY_TAG = "ApplyTag"
    REFRESH = "Refresh"

    # Ownership
    OWNS = "Owns"
    CREATED_BY = "CreatedBy"

    # Hierarchy
    CONTAINS = "Contains"  # Catalog->Schema, Schema->Table, etc.
    PART_OF = "PartOf"  # Table->Schema, Schema->Catalog, etc.
    ASSIGNED_TO = "AssignedTo"  # Metastore -> Workspace

    # Job/Cluster relationships
    RUNS_ON = "RunsOn"  # Job -> Cluster
    USES_POOL = "UsesPool"  # Cluster -> Instance Pool
    HAS_POLICY = "HasPolicy"  # Cluster -> Cluster Policy

    # AI/ML relationships
    DEPLOYED_ON = "DeployedOn"  # Model -> Serving Endpoint
    SERVES_MODEL = "ServesModel"  # Serving Endpoint -> Model
    INDEXES_TABLE = "IndexesTable"  # Vector Search Index -> Table
    HOSTED_ON = "HostedOn"  # Vector Search Index -> Vector Search Endpoint

    # Analytics relationships
    QUERIES_TABLE = "QueriesTable"  # Query/Dashboard -> Table
    USES_WAREHOUSE = "UsesWarehouse"  # Query/Dashboard -> Warehouse

    # Pipeline relationships
    READS_FROM = "ReadsFrom"  # Pipeline -> Table (source)
    WRITES_TO = "WritesTo"  # Pipeline -> Table (target)

    # Secret access
    CAN_READ_SECRET = "CanReadSecret"
    CAN_WRITE_SECRET = "CanWriteSecret"
    CAN_MANAGE_SECRET = "CanManageSecret"

    # Storage/External access
    ACCESSES_LOCATION = "AccessesLocation"  # Storage Credential -> External Location
    USES_CREDENTIAL = "UsesCredential"  # External Location -> Storage Credential


@dataclass
class GraphSchema:
    """Schema definition for BrickHound graph in Delta Lake"""
    
    @staticmethod
    def get_vertex_schema() -> str:
        """
        Get Spark SQL schema for vertices table

        Returns:
            DDL string for creating vertices table
        """
        return """
            CREATE TABLE IF NOT EXISTS {table_name} (
                id STRING NOT NULL COMMENT 'Unique vertex identifier. Format varies by entity type: ws_{{workspace_id}}_{{type}}:{{entity_id}} for workspace entities, catalog.schema.table for UC objects, account_{{type}}:{{id}} for account-level entities',
                node_type STRING NOT NULL COMMENT 'Entity type — e.g. User, Group, AccountServicePrincipal, Table, View, Schema, Catalog, Cluster, Job, SecretScope, Query, Alert, ServingEndpoint',
                name STRING COMMENT 'Technical identifier: email address for users, full catalog.schema.table path for tables, display name for other entity types',
                display_name STRING COMMENT 'Human-readable display name (e.g. user full name, table name)',
                email STRING COMMENT 'Email address — populated for User and AccountServicePrincipal node types',
                application_id STRING COMMENT 'OAuth application ID — populated for ServicePrincipal vertices',
                active BOOLEAN COMMENT 'True if this entity is currently active in Databricks',
                created_at TIMESTAMP COMMENT 'Timestamp when the entity was created in Databricks',
                modified_at TIMESTAMP COMMENT 'Timestamp when the entity was last updated in Databricks',
                owner STRING COMMENT 'Owner email or identity of this entity in Databricks',
                properties MAP<STRING, STRING> COMMENT 'Additional entity-specific properties as JSON',
                metadata MAP<STRING, STRING> COMMENT 'Additional metadata about this vertex as JSON'
            )
            USING DELTA
            PARTITIONED BY (node_type)
            COMMENT 'BrickHound graph vertices — Databricks objects and identities. Known node_type values: Table, View, Secret, Alert, Cluster, Schema, Job, User, SecretScope, Query, ServingEndpoint, AccountServicePrincipal, Catalog, Group, AccountUser. Use with brickhound_edges to trace who can access what.'
        """
    
    @staticmethod
    def get_edge_schema() -> str:
        """
        Get Spark SQL schema for edges table

        Returns:
            DDL string for creating edges table
        """
        return """
            CREATE TABLE IF NOT EXISTS {table_name} (
                src STRING NOT NULL COMMENT 'Source vertex ID or user email — the entity that holds the relationship or permission',
                dst STRING NOT NULL COMMENT 'Destination vertex ID or object path — the entity being accessed or contained',
                relationship STRING NOT NULL COMMENT 'Relationship type. UC grants: ALL PRIVILEGES, SELECT, USE SCHEMA, USE CATALOG, EXECUTE, READ VOLUME, CREATE TABLE. Structural: Contains, MemberOf. Access: WorkspaceAccess, CanManageSecret, CanReadSecret, MANAGE, BROWSE',
                permission_level STRING COMMENT 'Permission level granted. Matches relationship for UC privilege edges; NULL for structural relationships (MemberOf, Contains)',
                inherited BOOLEAN DEFAULT FALSE COMMENT 'True if this permission is inherited through group membership or UC hierarchy; False if directly granted',
                created_at TIMESTAMP COMMENT 'Timestamp when this edge record was created',
                properties MAP<STRING, STRING> COMMENT 'Additional edge properties as JSON'
            )
            USING DELTA
            PARTITIONED BY (relationship)
            COMMENT 'BrickHound graph edges — relationships and permissions between Databricks entities. UC privilege types: ALL PRIVILEGES, SELECT, USE SCHEMA, USE CATALOG, EXECUTE, READ VOLUME, CREATE TABLE. Structural: Contains, MemberOf. Access: WorkspaceAccess, CanManageSecret, CanReadSecret. Use with brickhound_vertices to answer who can access what.'
        """
    
    @staticmethod
    def get_metadata_schema() -> str:
        """
        Get Spark SQL schema for collection metadata table

        Returns:
            DDL string for creating the brickhound_collection_metadata table
        """
        return """
            CREATE TABLE IF NOT EXISTS {table_name} (
                run_id STRING NOT NULL COMMENT 'Unique run identifier in format YYYYMMDD_HHMMSS_hash (e.g. 20260218_212211_4a73dbfd)',
                collection_timestamp TIMESTAMP NOT NULL COMMENT 'Timestamp when the data collection started',
                vertices_count STRING COMMENT 'Total number of graph vertices (entities) collected in this run',
                edges_count STRING COMMENT 'Total number of graph edges (relationships/permissions) collected in this run',
                collected_by STRING COMMENT 'Email or identity of the service principal or user that ran the collection',
                collection_config STRING COMMENT 'JSON object with 30+ boolean flags controlling which entity types were collected (e.g. collect_clusters, collect_jobs, collect_unity_catalog)',
                workspaces_collected STRING COMMENT 'JSON array of workspace names successfully collected (e.g. ["plain","csp","sfe"])',
                workspaces_failed STRING COMMENT 'JSON array of workspace names that failed during collection. Empty array means all workspaces succeeded.',
                workspace_status STRING COMMENT 'JSON map of workspace_id to status object: {name, status, error} for each workspace',
                collection_mode STRING COMMENT 'Collection scope: multi-workspace when collecting across workspaces, single-workspace for isolated runs'
            )
            USING DELTA
            COMMENT 'One row per Permission Analysis (BrickHound) data collection run. Tracks what was collected, from which workspaces, and the outcome. The collection_config JSON documents exactly which entity types were included in each run.'
        """

    @staticmethod
    def vertex_columns() -> List[str]:
        """Get list of vertex table columns"""
        return [
            "id",
            "node_type",
            "name",
            "display_name",
            "email",
            "application_id",
            "active",
            "created_at",
            "modified_at",
            "owner",
            "properties",
            "metadata"
        ]
    
    @staticmethod
    def edge_columns() -> List[str]:
        """Get list of edge table columns"""
        return [
            "src",
            "dst",
            "relationship",
            "permission_level",
            "inherited",
            "created_at",
            "properties"
        ]
    
    @staticmethod
    def create_vertex(
        id: str,
        node_type: NodeType,
        name: str = None,
        display_name: str = None,
        email: str = None,
        application_id: str = None,
        active: bool = True,
        owner: str = None,
        properties: Dict[str, Any] = None,
        metadata: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Create a vertex dictionary

        Args:
            id: Unique identifier for the node
            node_type: Type of node
            name: Node name
            display_name: Display name
            email: Email (for users/SPs)
            application_id: Application ID (for service principals)
            active: Whether the node is active
            owner: Owner identifier
            properties: Additional properties
            metadata: Metadata from source system

        Returns:
            Dictionary representing a vertex
        """
        return {
            "id": id,
            "node_type": node_type.value,
            "name": name or id,
            "display_name": display_name,
            "email": email,
            "application_id": application_id,
            "active": active,
            "owner": owner,
            "properties": properties or {},
            "metadata": metadata or {},
        }
    
    @staticmethod
    def create_edge(
        src: str,
        dst: str,
        relationship: EdgeType,
        permission_level: str = None,
        inherited: bool = False,
        properties: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Create an edge dictionary
        
        Args:
            src: Source vertex ID
            dst: Destination vertex ID
            relationship: Type of relationship
            permission_level: Permission level (if applicable)
            inherited: Whether permission is inherited
            properties: Additional properties
            
        Returns:
            Dictionary representing an edge
        """
        return {
            "src": src,
            "dst": dst,
            "relationship": relationship.value,
            "permission_level": permission_level,
            "inherited": inherited,
            "properties": properties or {},
        }


class AttackPath:
    """Pre-defined attack path patterns"""
    
    @staticmethod
    def privilege_escalation_via_group() -> str:
        """
        Find paths where a user can escalate privileges through group membership
        
        Pattern: User -> Group -> Resource with elevated permissions
        """
        return """
            -- Find privilege escalation through group membership
            SELECT 
                u.id as user_id,
                u.name as user_name,
                g.id as group_id,
                g.name as group_name,
                r.id as resource_id,
                r.node_type as resource_type,
                e2.permission_level as permission
            FROM vertices u
            JOIN edges e1 ON u.id = e1.src AND e1.relationship = 'MemberOf'
            JOIN vertices g ON e1.dst = g.id AND g.node_type = 'Group'
            JOIN edges e2 ON g.id = e2.src
            JOIN vertices r ON e2.dst = r.id
            WHERE u.node_type = 'User'
            AND e2.permission_level IN ('CAN_MANAGE', 'ALL_PRIVILEGES')
        """
    
    @staticmethod
    def find_over_privileged_users() -> str:
        """Find users with excessive permissions"""
        return """
            SELECT 
                u.id,
                u.name,
                COUNT(DISTINCT e.dst) as resource_count,
                COUNT(DISTINCT CASE WHEN e.permission_level = 'CAN_MANAGE' THEN e.dst END) as manage_perms,
                COUNT(DISTINCT CASE WHEN e.permission_level = 'ALL_PRIVILEGES' THEN e.dst END) as all_privs
            FROM vertices u
            JOIN edges e ON u.id = e.src
            WHERE u.node_type IN ('User', 'ServicePrincipal')
            GROUP BY u.id, u.name
            HAVING manage_perms > 10 OR all_privs > 5
            ORDER BY all_privs DESC, manage_perms DESC
        """
    
    @staticmethod
    def find_orphaned_resources() -> str:
        """Find resources without clear ownership"""
        return """
            SELECT 
                r.id,
                r.node_type,
                r.name,
                r.owner
            FROM vertices r
            LEFT JOIN edges e ON r.id = e.dst AND e.relationship = 'Owns'
            WHERE r.node_type IN ('Cluster', 'Job', 'Warehouse', 'Table')
            AND e.src IS NULL
            AND (r.owner IS NULL OR r.owner = '')
        """
    
    @staticmethod
    def blast_radius(principal_id: str) -> str:
        """
        Calculate blast radius if a principal is compromised
        
        Args:
            principal_id: User or Service Principal ID
        """
        return f"""
            -- Blast radius analysis for principal: {principal_id}
            WITH RECURSIVE reachable AS (
                -- Direct access
                SELECT dst as resource_id, 1 as depth, relationship, permission_level
                FROM edges
                WHERE src = '{principal_id}'
                
                UNION ALL
                
                -- Indirect access through groups
                SELECT e2.dst, r.depth + 1, e2.relationship, e2.permission_level
                FROM reachable r
                JOIN edges e2 ON r.resource_id = e2.src
                WHERE r.depth < 5
            )
            SELECT 
                v.node_type,
                v.name,
                r.permission_level,
                MIN(r.depth) as min_hops
            FROM reachable r
            JOIN vertices v ON r.resource_id = v.id
            GROUP BY v.node_type, v.name, r.permission_level
            ORDER BY min_hops, v.node_type
        """

