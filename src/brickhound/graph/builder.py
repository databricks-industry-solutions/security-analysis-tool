"""
Graph builder - converts Databricks objects into graph format
"""

import logging
from typing import Dict, Any, List
from datetime import datetime
from brickhound.graph.schema import NodeType, EdgeType, GraphSchema

__all__ = ["GraphBuilder"]

logger = logging.getLogger(__name__)


class GraphBuilder:
    """Builds graph vertices and edges from Databricks objects"""

    def __init__(self):
        self.vertices: List[Dict[str, Any]] = []
        self.edges: List[Dict[str, Any]] = []
        self._vertex_ids: set = set()  # Track existing vertices
        self._edge_keys: set = set()  # Track existing edges to prevent duplicates

    def add_vertex(self, vertex: Dict[str, Any]) -> None:
        """Add a vertex to the graph"""
        vertex_id = vertex.get("id")
        if vertex_id and vertex_id not in self._vertex_ids:
            # Add timestamps if not present
            if "created_at" not in vertex:
                vertex["created_at"] = datetime.now()
            if "modified_at" not in vertex:
                vertex["modified_at"] = datetime.now()

            self.vertices.append(vertex)
            self._vertex_ids.add(vertex_id)

    def _get_edge_key(self, edge: Dict[str, Any]) -> str:
        """Generate a unique key for an edge to detect duplicates"""
        src = edge.get("src", "")
        dst = edge.get("dst", "")
        relationship = edge.get("relationship", "")
        permission_level = edge.get("permission_level", "")
        return f"{src}|{dst}|{relationship}|{permission_level}"

    def add_edge(self, edge: Dict[str, Any]) -> None:
        """Add an edge to the graph (with deduplication)"""
        edge_key = self._get_edge_key(edge)
        if edge_key in self._edge_keys:
            return  # Skip duplicate edge

        # Add timestamp if not present
        if "created_at" not in edge:
            edge["created_at"] = datetime.now()
        self.edges.append(edge)
        self._edge_keys.add(edge_key)

    def _add_owner_edge(self, owner: str, object_id: str) -> None:
        """Helper to add an ownership edge from owner to object"""
        if owner:
            edge = GraphSchema.create_edge(
                src=owner,
                dst=object_id,
                relationship=EdgeType.OWNS,
            )
            self.add_edge(edge)

    def build_user_node(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a User node from API response"""
        raw_id = user_data.get("id") or user_data.get("userName")
        user_id = f"user:{raw_id}"

        vertex = GraphSchema.create_vertex(
            id=user_id,
            node_type=NodeType.USER,
            name=user_data.get("userName"),
            display_name=user_data.get("displayName"),
            email=user_data.get("emails", [{}])[0].get("value") if user_data.get("emails") else None,
            active=user_data.get("active", True),
            metadata=user_data,
        )
        
        self.add_vertex(vertex)
        
        # Add group memberships
        for group in user_data.get("groups", []):
            raw_group_id = group.get("value") or group.get("display")
            if raw_group_id:
                edge = GraphSchema.create_edge(
                    src=user_id,
                    dst=f"group:{raw_group_id}",
                    relationship=EdgeType.MEMBER_OF,
                )
                self.add_edge(edge)
        
        return vertex
    
    def build_group_node(self, group_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a Group node from API response"""
        raw_id = group_data.get("id") or group_data.get("displayName")
        group_id = f"group:{raw_id}"

        vertex = GraphSchema.create_vertex(
            id=group_id,
            node_type=NodeType.GROUP,
            name=group_data.get("displayName"),
            active=True,
            metadata=group_data,
        )

        self.add_vertex(vertex)

        # Add members (members can be users, groups, or service principals)
        # The SCIM API returns members with $ref field indicating type
        for member in group_data.get("members", []):
            raw_member_id = member.get("value") or member.get("display")
            if not raw_member_id:
                continue

            # Determine member type from $ref field (SCIM standard)
            # Format: ".../Groups/{id}" or ".../Users/{id}" or ".../ServicePrincipals/{id}"
            ref = member.get("$ref", "")
            member_type = member.get("type", "")

            # Determine the prefixed member ID based on type
            if "Groups" in ref or member_type == "Group":
                prefixed_member_id = f"group:{raw_member_id}"
                # For nested groups: create MEMBER_OF edge (member_group -> this_group)
                member_of_edge = GraphSchema.create_edge(
                    src=prefixed_member_id,
                    dst=group_id,
                    relationship=EdgeType.MEMBER_OF,
                )
                self.add_edge(member_of_edge)
            elif "ServicePrincipals" in ref or member_type == "ServicePrincipal":
                prefixed_member_id = f"service_principal:{raw_member_id}"
                # SP is member of this group
                member_of_edge = GraphSchema.create_edge(
                    src=prefixed_member_id,
                    dst=group_id,
                    relationship=EdgeType.MEMBER_OF,
                )
                self.add_edge(member_of_edge)
            elif "Users" in ref or member_type == "User":
                prefixed_member_id = f"user:{raw_member_id}"
                # User is member of this group (also created in build_user_node, but ensure it exists)
                member_of_edge = GraphSchema.create_edge(
                    src=prefixed_member_id,
                    dst=group_id,
                    relationship=EdgeType.MEMBER_OF,
                )
                self.add_edge(member_of_edge)
            else:
                # Unknown type - try to infer from context or use raw ID
                # Could be user, group, or SP - create edges for all possible IDs
                prefixed_member_id = raw_member_id

            # Also add HAS_MEMBER edge (this_group -> member) with proper prefix
            has_member_edge = GraphSchema.create_edge(
                src=group_id,
                dst=prefixed_member_id,
                relationship=EdgeType.HAS_MEMBER,
            )
            self.add_edge(has_member_edge)

        return vertex

    def build_account_user_node(self, user_data: Dict[str, Any], account_id: str = None) -> Dict[str, Any]:
        """Build an Account User node from API response (account-level users)

        Args:
            user_data: User data from SCIM API
            account_id: Account ID for creating AccountAdmin edges
        """
        raw_id = user_data.get("id") or user_data.get("userName")
        user_id = f"account_user:{raw_id}"

        vertex = GraphSchema.create_vertex(
            id=user_id,
            node_type=NodeType.ACCOUNT_USER,
            name=user_data.get("userName"),
            display_name=user_data.get("displayName"),
            email=user_data.get("emails", [{}])[0].get("value") if user_data.get("emails") else None,
            active=user_data.get("active", True),
            metadata=user_data,
        )

        self.add_vertex(vertex)

        # Add group memberships from user data (if present)
        for group in user_data.get("groups", []):
            raw_group_id = group.get("value") or group.get("display")
            if raw_group_id:
                # Create MemberOf edge with account_group prefix
                edge = GraphSchema.create_edge(
                    src=user_id,
                    dst=f"account_group:{raw_group_id}",
                    relationship=EdgeType.MEMBER_OF,
                )
                self.add_edge(edge)

        # Check for account-level roles (e.g., account_admin)
        # The SCIM API returns roles as a list of objects with 'value' field
        roles = user_data.get("roles", [])

        for role in roles:
            role_value = role.get("value", "") if isinstance(role, dict) else str(role)
            if role_value.lower() == "account_admin":
                # Create AccountAdmin edge from user to account
                if account_id:
                    edge = GraphSchema.create_edge(
                        src=user_id,
                        dst=f"account:{account_id}",
                        relationship=EdgeType.ACCOUNT_ADMIN,
                    )
                    self.add_edge(edge)
                    logger.info(f"Created AccountAdmin edge for user {user_name}")

        return vertex

    def build_account_group_node(self, group_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build an Account Group node from API response (account-level groups)"""
        raw_id = group_data.get("id") or group_data.get("displayName")
        group_id = f"account_group:{raw_id}"
        group_name = group_data.get("displayName")

        vertex = GraphSchema.create_vertex(
            id=group_id,
            node_type=NodeType.ACCOUNT_GROUP,
            name=group_name,
            active=True,
            metadata=group_data,
        )

        self.add_vertex(vertex)

        # Add members (members can be users, groups, or service principals)
        # The SCIM API returns members with $ref field indicating type
        for member in group_data.get("members", []):
            raw_member_id = member.get("value") or member.get("display")
            if not raw_member_id:
                continue

            # Determine member type from $ref field (SCIM standard)
            # Format: ".../Groups/{id}" or ".../Users/{id}" or ".../ServicePrincipals/{id}"
            ref = member.get("$ref", "")
            member_type = member.get("type", "")

            # Determine the prefixed member ID based on type
            # Account-level members use account_* prefixes
            if "Groups" in ref or member_type == "Group":
                prefixed_member_id = f"account_group:{raw_member_id}"
                # For nested groups: create MEMBER_OF edge (member_group -> this_group)
                member_of_edge = GraphSchema.create_edge(
                    src=prefixed_member_id,
                    dst=group_id,
                    relationship=EdgeType.MEMBER_OF,
                )
                self.add_edge(member_of_edge)

                # Also add edge with group name as dst for query flexibility
                member_of_edge_by_name = GraphSchema.create_edge(
                    src=prefixed_member_id,
                    dst=group_name,
                    relationship=EdgeType.MEMBER_OF,
                )
                self.add_edge(member_of_edge_by_name)
            elif "ServicePrincipals" in ref or member_type == "ServicePrincipal":
                prefixed_member_id = f"account_sp:{raw_member_id}"
                # SP is member of this group
                member_of_edge = GraphSchema.create_edge(
                    src=prefixed_member_id,
                    dst=group_id,
                    relationship=EdgeType.MEMBER_OF,
                )
                self.add_edge(member_of_edge)

                # Also add edge with group name as dst for query flexibility
                member_of_edge_by_name = GraphSchema.create_edge(
                    src=prefixed_member_id,
                    dst=group_name,
                    relationship=EdgeType.MEMBER_OF,
                )
                self.add_edge(member_of_edge_by_name)
            elif "Users" in ref or member_type == "User":
                prefixed_member_id = f"account_user:{raw_member_id}"
                # User is member of this group
                member_of_edge = GraphSchema.create_edge(
                    src=prefixed_member_id,
                    dst=group_id,
                    relationship=EdgeType.MEMBER_OF,
                )
                self.add_edge(member_of_edge)

                # Also add edge with group name as dst for query flexibility
                member_of_edge_by_name = GraphSchema.create_edge(
                    src=prefixed_member_id,
                    dst=group_name,
                    relationship=EdgeType.MEMBER_OF,
                )
                self.add_edge(member_of_edge_by_name)
            else:
                # Unknown type - use raw ID with account prefix
                prefixed_member_id = f"account_user:{raw_member_id}"

            # Also add HAS_MEMBER edge (this_group -> member) with proper prefix
            has_member_edge = GraphSchema.create_edge(
                src=group_id,
                dst=prefixed_member_id,
                relationship=EdgeType.HAS_MEMBER,
            )
            self.add_edge(has_member_edge)

        return vertex

    def build_service_principal_node(self, sp_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a Service Principal node"""
        raw_id = sp_data.get("id") or sp_data.get("applicationId")
        sp_id = f"service_principal:{raw_id}"
        # applicationId is the stable identifier across workspace/account levels
        application_id = sp_data.get("applicationId")

        vertex = GraphSchema.create_vertex(
            id=sp_id,
            node_type=NodeType.SERVICE_PRINCIPAL,
            name=sp_data.get("displayName") or sp_data.get("applicationId"),
            application_id=application_id,
            active=sp_data.get("active", True),
            metadata=sp_data,
        )

        self.add_vertex(vertex)

        # Add group memberships (service principals can be members of groups)
        for group in sp_data.get("groups", []):
            raw_group_id = group.get("value") or group.get("display")
            if raw_group_id:
                edge = GraphSchema.create_edge(
                    src=sp_id,
                    dst=f"group:{raw_group_id}",
                    relationship=EdgeType.MEMBER_OF,
                )
                self.add_edge(edge)

        return vertex

    def build_account_service_principal_node(self, sp_data: Dict[str, Any], account_id: str = None) -> Dict[str, Any]:
        """Build an Account Service Principal node (account-level SPs)

        Args:
            sp_data: Service principal data from SCIM API
            account_id: Account ID for creating AccountAdmin edges
        """
        raw_id = sp_data.get("id") or sp_data.get("applicationId")
        sp_id = f"account_sp:{raw_id}"
        # applicationId is the stable identifier across workspace/account levels
        application_id = sp_data.get("applicationId")

        vertex = GraphSchema.create_vertex(
            id=sp_id,
            node_type=NodeType.ACCOUNT_SERVICE_PRINCIPAL,
            name=sp_data.get("displayName") or sp_data.get("applicationId"),
            application_id=application_id,
            active=sp_data.get("active", True),
            metadata=sp_data,
        )

        self.add_vertex(vertex)

        # Add group memberships (service principals can be members of groups)
        for group in sp_data.get("groups", []):
            raw_group_id = group.get("value") or group.get("display")
            if raw_group_id:
                edge = GraphSchema.create_edge(
                    src=sp_id,
                    dst=f"account_group:{raw_group_id}",
                    relationship=EdgeType.MEMBER_OF,
                )
                self.add_edge(edge)

        # Check for account-level roles (e.g., account_admin)
        # The SCIM API returns roles as a list of objects with 'value' field
        roles = sp_data.get("roles", [])
        for role in roles:
            role_value = role.get("value", "") if isinstance(role, dict) else str(role)
            if role_value.lower() == "account_admin":
                # Create AccountAdmin edge from SP to account
                if account_id:
                    edge = GraphSchema.create_edge(
                        src=sp_id,
                        dst=f"account:{account_id}",
                        relationship=EdgeType.ACCOUNT_ADMIN,
                    )
                    self.add_edge(edge)
                    logger.info(f"Created AccountAdmin edge for service principal {sp_data.get('displayName')}")

        return vertex

    def build_cluster_node(self, cluster_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a Cluster node"""
        raw_id = cluster_data.get("cluster_id")
        cluster_id = f"cluster:{raw_id}"

        vertex = GraphSchema.create_vertex(
            id=cluster_id,
            node_type=NodeType.CLUSTER,
            name=cluster_data.get("cluster_name"),
            owner=cluster_data.get("creator_user_name"),
            active=cluster_data.get("state") not in ["TERMINATED", "ERROR"],
            properties={
                "cluster_source": cluster_data.get("cluster_source"),
                "spark_version": cluster_data.get("spark_version"),
                "node_type_id": cluster_data.get("node_type_id"),
            },
            metadata=cluster_data,
        )
        
        self.add_vertex(vertex)

        # Add owner relationship
        self._add_owner_edge(cluster_data.get("creator_user_name"), cluster_id)

        # Add instance pool relationship
        if cluster_data.get("instance_pool_id"):
            edge = GraphSchema.create_edge(
                src=cluster_id,
                dst=f"instance_pool:{cluster_data['instance_pool_id']}",
                relationship=EdgeType.USES_POOL,
            )
            self.add_edge(edge)

        # Add policy relationship
        if cluster_data.get("policy_id"):
            edge = GraphSchema.create_edge(
                src=cluster_id,
                dst=f"cluster_policy:{cluster_data['policy_id']}",
                relationship=EdgeType.HAS_POLICY,
            )
            self.add_edge(edge)
        
        return vertex
    
    def build_job_node(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a Job node"""
        raw_id = str(job_data.get("job_id"))
        job_id = f"job:{raw_id}"

        settings = job_data.get("settings", {})
        vertex = GraphSchema.create_vertex(
            id=job_id,
            node_type=NodeType.JOB,
            name=settings.get("name") or f"Job-{job_id}",
            owner=job_data.get("creator_user_name"),
            active=True,
            metadata=job_data,
        )
        
        self.add_vertex(vertex)

        # Add owner relationship
        self._add_owner_edge(job_data.get("creator_user_name"), job_id)

        # Add cluster relationships
        tasks = settings.get("tasks", [])
        for task in tasks:
            if task.get("existing_cluster_id"):
                edge = GraphSchema.create_edge(
                    src=job_id,
                    dst=f"cluster:{task['existing_cluster_id']}",
                    relationship=EdgeType.RUNS_ON,
                )
                self.add_edge(edge)
        
        return vertex
    
    def build_notebook_node(self, notebook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a Notebook node"""
        path = notebook_data.get("path")
        
        vertex = GraphSchema.create_vertex(
            id=path,
            node_type=NodeType.NOTEBOOK,
            name=path.split("/")[-1] if path else "unknown",
            properties={
                "language": notebook_data.get("language"),
                "path": path,
            },
            metadata=notebook_data,
        )
        
        self.add_vertex(vertex)
        return vertex
    
    def build_catalog_node(self, catalog_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a Unity Catalog Catalog node"""
        catalog_name = catalog_data.get("name")
        
        vertex = GraphSchema.create_vertex(
            id=f"catalog:{catalog_name}",
            node_type=NodeType.CATALOG,
            name=catalog_name,
            owner=catalog_data.get("owner"),
            metadata=catalog_data,
        )
        
        self.add_vertex(vertex)

        # Add owner relationship
        self._add_owner_edge(catalog_data.get("owner"), f"catalog:{catalog_name}")

        return vertex

    def build_schema_node(self, schema_data: Dict[str, Any], catalog_name: str) -> Dict[str, Any]:
        """Build a Unity Catalog Schema node"""
        schema_name = schema_data.get("name")
        full_name = f"{catalog_name}.{schema_name}"
        
        vertex = GraphSchema.create_vertex(
            id=f"schema:{full_name}",
            node_type=NodeType.SCHEMA,
            name=schema_name,
            owner=schema_data.get("owner"),
            properties={"full_name": full_name, "catalog": catalog_name},
            metadata=schema_data,
        )
        
        self.add_vertex(vertex)
        
        # Add hierarchy relationship to catalog
        edge = GraphSchema.create_edge(
            src=f"catalog:{catalog_name}",
            dst=f"schema:{full_name}",
            relationship=EdgeType.CONTAINS,
        )
        self.add_edge(edge)

        # Add owner relationship
        self._add_owner_edge(schema_data.get("owner"), f"schema:{full_name}")

        return vertex

    def build_table_node(self, table_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a Unity Catalog Table node"""
        full_name = table_data.get("full_name")
        table_type = table_data.get("table_type", "TABLE")
        
        # Determine node type
        node_type = NodeType.VIEW if table_type == "VIEW" else NodeType.TABLE
        
        vertex = GraphSchema.create_vertex(
            id=f"table:{full_name}",
            node_type=node_type,
            name=table_data.get("name"),
            owner=table_data.get("owner"),
            properties={
                "full_name": full_name,
                "table_type": table_type,
                "catalog_name": table_data.get("catalog_name"),
                "schema_name": table_data.get("schema_name"),
            },
            metadata=table_data,
        )
        
        self.add_vertex(vertex)
        
        # Add hierarchy relationship to schema
        catalog = table_data.get("catalog_name")
        schema = table_data.get("schema_name")
        if catalog and schema:
            edge = GraphSchema.create_edge(
                src=f"schema:{catalog}.{schema}",
                dst=f"table:{full_name}",
                relationship=EdgeType.CONTAINS,
            )
            self.add_edge(edge)

        # Add owner relationship
        self._add_owner_edge(table_data.get("owner"), f"table:{full_name}")

        return vertex

    def build_warehouse_node(self, warehouse_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a SQL Warehouse node"""
        raw_id = warehouse_data.get("id")
        warehouse_id = f"warehouse:{raw_id}"

        vertex = GraphSchema.create_vertex(
            id=warehouse_id,
            node_type=NodeType.WAREHOUSE,
            name=warehouse_data.get("name"),
            owner=warehouse_data.get("creator_name"),
            active=warehouse_data.get("state") == "RUNNING",
            properties={
                "cluster_size": warehouse_data.get("cluster_size"),
                "warehouse_type": warehouse_data.get("warehouse_type"),
            },
            metadata=warehouse_data,
        )

        self.add_vertex(vertex)

        # Add owner relationship
        self._add_owner_edge(warehouse_data.get("creator_name"), warehouse_id)

        return vertex

    # =========================================================================
    # ACCOUNT-LEVEL NODE BUILDERS
    # =========================================================================

    def build_workspace_node(self, workspace_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a Workspace node"""
        workspace_id = str(workspace_data.get("workspace_id"))

        vertex = GraphSchema.create_vertex(
            id=f"workspace:{workspace_id}",
            node_type=NodeType.WORKSPACE,
            name=workspace_data.get("workspace_name"),
            active=workspace_data.get("workspace_status") == "RUNNING",
            properties={
                "deployment_name": workspace_data.get("deployment_name"),
                "workspace_url": f"https://{workspace_data.get('deployment_name')}.cloud.databricks.com",
                "cloud": workspace_data.get("cloud"),
                "region": workspace_data.get("location") or workspace_data.get("aws_region") or workspace_data.get("azure_region"),
            },
            metadata=workspace_data,
        )

        self.add_vertex(vertex)
        return vertex

    def build_account_node(self, account_id: str, account_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Build an Account node"""
        vertex = GraphSchema.create_vertex(
            id=f"account:{account_id}",
            node_type=NodeType.ACCOUNT,
            name=account_id,
            active=True,
            metadata=account_data or {},
        )

        self.add_vertex(vertex)
        return vertex

    def build_metastore_node(self, metastore_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a Metastore node"""
        metastore_id = metastore_data.get("metastore_id")

        vertex = GraphSchema.create_vertex(
            id=f"metastore:{metastore_id}",
            node_type=NodeType.METASTORE,
            name=metastore_data.get("name"),
            owner=metastore_data.get("owner"),
            active=True,
            properties={
                "region": metastore_data.get("region"),
                "cloud": metastore_data.get("cloud"),
                "storage_root": metastore_data.get("storage_root"),
            },
            metadata=metastore_data,
        )

        self.add_vertex(vertex)

        # Add owner relationship
        self._add_owner_edge(metastore_data.get("owner"), f"metastore:{metastore_id}")

        return vertex

    # =========================================================================
    # COMPUTE NODE BUILDERS
    # =========================================================================

    def build_instance_pool_node(self, pool_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build an Instance Pool node"""
        raw_id = pool_data.get("instance_pool_id")
        pool_id = f"instance_pool:{raw_id}"

        vertex = GraphSchema.create_vertex(
            id=pool_id,
            node_type=NodeType.INSTANCE_POOL,
            name=pool_data.get("instance_pool_name"),
            active=pool_data.get("state") == "ACTIVE",
            properties={
                "node_type_id": pool_data.get("node_type_id"),
                "min_idle_instances": str(pool_data.get("min_idle_instances", 0)),
                "max_capacity": str(pool_data.get("max_capacity", 0)),
            },
            metadata=pool_data,
        )

        self.add_vertex(vertex)
        return vertex

    def build_cluster_policy_node(self, policy_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a Cluster Policy node"""
        raw_id = policy_data.get("policy_id")
        policy_id = f"cluster_policy:{raw_id}"

        vertex = GraphSchema.create_vertex(
            id=policy_id,
            node_type=NodeType.CLUSTER_POLICY,
            name=policy_data.get("name"),
            owner=policy_data.get("creator_user_name"),
            active=True,
            properties={
                "is_default": str(policy_data.get("is_default", False)),
            },
            metadata=policy_data,
        )

        self.add_vertex(vertex)

        # Add owner relationship
        self._add_owner_edge(policy_data.get("creator_user_name"), policy_id)

        return vertex

    def build_global_init_script_node(self, script_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a Global Init Script node"""
        script_id = script_data.get("script_id")

        vertex = GraphSchema.create_vertex(
            id=f"init_script:{script_id}",
            node_type=NodeType.GLOBAL_INIT_SCRIPT,
            name=script_data.get("name"),
            owner=script_data.get("creator_user_name"),
            active=script_data.get("enabled", True),
            properties={
                "position": str(script_data.get("position", 0)),
            },
            metadata=script_data,
        )

        self.add_vertex(vertex)
        return vertex

    # =========================================================================
    # AI/ML NODE BUILDERS
    # =========================================================================

    def build_serving_endpoint_node(self, endpoint_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a Model Serving Endpoint node"""
        endpoint_name = endpoint_data.get("name")

        vertex = GraphSchema.create_vertex(
            id=f"serving_endpoint:{endpoint_name}",
            node_type=NodeType.SERVING_ENDPOINT,
            name=endpoint_name,
            owner=endpoint_data.get("creator"),
            active=endpoint_data.get("state", {}).get("ready") == "READY",
            properties={
                "endpoint_type": endpoint_data.get("endpoint_type", ""),
            },
            metadata=endpoint_data,
        )

        self.add_vertex(vertex)

        # Add owner relationship
        self._add_owner_edge(endpoint_data.get("creator"), f"serving_endpoint:{endpoint_name}")

        # Add served model relationships
        config = endpoint_data.get("config", {})
        for served_model in config.get("served_models", []) or config.get("served_entities", []):
            model_name = served_model.get("model_name") or served_model.get("entity_name")
            if model_name:
                edge = GraphSchema.create_edge(
                    src=f"serving_endpoint:{endpoint_name}",
                    dst=f"model:{model_name}",
                    relationship=EdgeType.SERVES_MODEL,
                )
                self.add_edge(edge)

        return vertex

    def build_vector_search_endpoint_node(self, endpoint_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a Vector Search Endpoint node"""
        endpoint_name = endpoint_data.get("name")

        vertex = GraphSchema.create_vertex(
            id=f"vs_endpoint:{endpoint_name}",
            node_type=NodeType.VECTOR_SEARCH_ENDPOINT,
            name=endpoint_name,
            owner=endpoint_data.get("creator"),
            active=endpoint_data.get("endpoint_status", {}).get("state") == "ONLINE",
            properties={
                "endpoint_type": endpoint_data.get("endpoint_type", ""),
            },
            metadata=endpoint_data,
        )

        self.add_vertex(vertex)
        return vertex

    def build_vector_search_index_node(self, index_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a Vector Search Index node"""
        index_name = index_data.get("name")

        vertex = GraphSchema.create_vertex(
            id=f"vs_index:{index_name}",
            node_type=NodeType.VECTOR_SEARCH_INDEX,
            name=index_name,
            owner=index_data.get("creator"),
            active=index_data.get("status", {}).get("ready", False),
            properties={
                "index_type": index_data.get("index_type", ""),
                "endpoint_name": index_data.get("endpoint_name", ""),
                "primary_key": index_data.get("primary_key", ""),
            },
            metadata=index_data,
        )

        self.add_vertex(vertex)

        # Add relationship to endpoint
        endpoint_name = index_data.get("endpoint_name")
        if endpoint_name:
            edge = GraphSchema.create_edge(
                src=f"vs_index:{index_name}",
                dst=f"vs_endpoint:{endpoint_name}",
                relationship=EdgeType.HOSTED_ON,
            )
            self.add_edge(edge)

        # Add relationship to source table
        delta_sync_config = index_data.get("delta_sync_index_spec", {})
        source_table = delta_sync_config.get("source_table")
        if source_table:
            edge = GraphSchema.create_edge(
                src=f"vs_index:{index_name}",
                dst=f"table:{source_table}",
                relationship=EdgeType.INDEXES_TABLE,
            )
            self.add_edge(edge)

        return vertex

    def build_registered_model_node(self, model_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a Registered Model node (Unity Catalog)"""
        full_name = model_data.get("full_name")

        vertex = GraphSchema.create_vertex(
            id=f"model:{full_name}",
            node_type=NodeType.REGISTERED_MODEL,
            name=model_data.get("name"),
            owner=model_data.get("owner"),
            active=True,
            properties={
                "full_name": full_name,
                "catalog_name": model_data.get("catalog_name"),
                "schema_name": model_data.get("schema_name"),
            },
            metadata=model_data,
        )

        self.add_vertex(vertex)

        # Add hierarchy relationship to schema
        catalog = model_data.get("catalog_name")
        schema = model_data.get("schema_name")
        if catalog and schema:
            edge = GraphSchema.create_edge(
                src=f"schema:{catalog}.{schema}",
                dst=f"model:{full_name}",
                relationship=EdgeType.CONTAINS,
            )
            self.add_edge(edge)

        # Add owner relationship
        self._add_owner_edge(model_data.get("owner"), f"model:{full_name}")

        return vertex

    def build_experiment_node(self, experiment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build an MLflow Experiment node"""
        experiment_id = experiment_data.get("experiment_id")

        vertex = GraphSchema.create_vertex(
            id=f"experiment:{experiment_id}",
            node_type=NodeType.EXPERIMENT,
            name=experiment_data.get("name"),
            active=experiment_data.get("lifecycle_stage") == "active",
            properties={
                "artifact_location": experiment_data.get("artifact_location", ""),
            },
            metadata=experiment_data,
        )

        self.add_vertex(vertex)
        return vertex

    # =========================================================================
    # ANALYTICS/BI NODE BUILDERS
    # =========================================================================

    def build_dashboard_node(self, dashboard_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a Dashboard node (Lakeview)"""
        dashboard_id = dashboard_data.get("dashboard_id")

        vertex = GraphSchema.create_vertex(
            id=f"dashboard:{dashboard_id}",
            node_type=NodeType.DASHBOARD,
            name=dashboard_data.get("display_name"),
            owner=dashboard_data.get("creator_name"),
            active=dashboard_data.get("lifecycle_state") == "ACTIVE",
            properties={
                "warehouse_id": dashboard_data.get("warehouse_id", ""),
                "path": dashboard_data.get("path", ""),
            },
            metadata=dashboard_data,
        )

        self.add_vertex(vertex)

        # Add owner relationship
        self._add_owner_edge(dashboard_data.get("creator_name"), f"dashboard:{dashboard_id}")

        # Add warehouse relationship
        if dashboard_data.get("warehouse_id"):
            edge = GraphSchema.create_edge(
                src=f"dashboard:{dashboard_id}",
                dst=f"warehouse:{dashboard_data['warehouse_id']}",
                relationship=EdgeType.USES_WAREHOUSE,
            )
            self.add_edge(edge)

        return vertex

    def build_query_node(self, query_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a SQL Query node"""
        query_id = query_data.get("id")

        vertex = GraphSchema.create_vertex(
            id=f"query:{query_id}",
            node_type=NodeType.QUERY,
            name=query_data.get("name") or query_data.get("display_name"),
            owner=query_data.get("owner_user_name"),
            active=True,
            properties={
                "warehouse_id": query_data.get("warehouse_id", ""),
            },
            metadata=query_data,
        )

        self.add_vertex(vertex)

        # Add owner relationship
        self._add_owner_edge(query_data.get("owner_user_name"), f"query:{query_id}")

        return vertex

    def build_alert_node(self, alert_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build an Alert node"""
        alert_id = alert_data.get("id")

        vertex = GraphSchema.create_vertex(
            id=f"alert:{alert_id}",
            node_type=NodeType.ALERT,
            name=alert_data.get("name") or alert_data.get("display_name"),
            owner=alert_data.get("owner_user_name"),
            active=alert_data.get("state") != "UNKNOWN",
            metadata=alert_data,
        )

        self.add_vertex(vertex)

        # Add owner relationship
        self._add_owner_edge(alert_data.get("owner_user_name"), f"alert:{alert_id}")

        return vertex

    # =========================================================================
    # ORCHESTRATION NODE BUILDERS
    # =========================================================================

    def build_pipeline_node(self, pipeline_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a Delta Live Tables Pipeline node"""
        pipeline_id = pipeline_data.get("pipeline_id")

        vertex = GraphSchema.create_vertex(
            id=f"pipeline:{pipeline_id}",
            node_type=NodeType.PIPELINE,
            name=pipeline_data.get("name"),
            owner=pipeline_data.get("creator_user_name"),
            active=pipeline_data.get("state") in ["RUNNING", "IDLE"],
            properties={
                "target": pipeline_data.get("spec", {}).get("target", ""),
                "catalog": pipeline_data.get("spec", {}).get("catalog", ""),
            },
            metadata=pipeline_data,
        )

        self.add_vertex(vertex)

        # Add owner relationship
        self._add_owner_edge(pipeline_data.get("creator_user_name"), f"pipeline:{pipeline_id}")

        # Add cluster relationship if specified
        spec = pipeline_data.get("spec", {})
        for cluster in spec.get("clusters", []):
            if cluster.get("existing_cluster_id"):
                edge = GraphSchema.create_edge(
                    src=f"pipeline:{pipeline_id}",
                    dst=f"cluster:{cluster['existing_cluster_id']}",
                    relationship=EdgeType.RUNS_ON,
                )
                self.add_edge(edge)

        return vertex

    # =========================================================================
    # UNITY CATALOG ADDITIONAL NODE BUILDERS
    # =========================================================================

    def build_external_location_node(self, location_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build an External Location node"""
        location_name = location_data.get("name")

        vertex = GraphSchema.create_vertex(
            id=f"external_location:{location_name}",
            node_type=NodeType.EXTERNAL_LOCATION,
            name=location_name,
            owner=location_data.get("owner"),
            active=True,
            properties={
                "url": location_data.get("url", ""),
                "credential_name": location_data.get("credential_name", ""),
            },
            metadata=location_data,
        )

        self.add_vertex(vertex)

        # Add owner relationship
        self._add_owner_edge(location_data.get("owner"), f"external_location:{location_name}")

        # Add credential relationship
        if location_data.get("credential_name"):
            edge = GraphSchema.create_edge(
                src=f"external_location:{location_name}",
                dst=f"storage_credential:{location_data['credential_name']}",
                relationship=EdgeType.USES_CREDENTIAL,
            )
            self.add_edge(edge)

        return vertex

    def build_storage_credential_node(self, credential_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a Storage Credential node"""
        cred_name = credential_data.get("name")

        vertex = GraphSchema.create_vertex(
            id=f"storage_credential:{cred_name}",
            node_type=NodeType.STORAGE_CREDENTIAL,
            name=cred_name,
            owner=credential_data.get("owner"),
            active=True,
            properties={
                "read_only": str(credential_data.get("read_only", False)),
            },
            metadata=credential_data,
        )

        self.add_vertex(vertex)

        # Add owner relationship
        self._add_owner_edge(credential_data.get("owner"), f"storage_credential:{cred_name}")

        return vertex

    def build_connection_node(self, connection_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a Connection node"""
        conn_name = connection_data.get("name")

        vertex = GraphSchema.create_vertex(
            id=f"connection:{conn_name}",
            node_type=NodeType.CONNECTION,
            name=conn_name,
            owner=connection_data.get("owner"),
            active=True,
            properties={
                "connection_type": connection_data.get("connection_type", ""),
            },
            metadata=connection_data,
        )

        self.add_vertex(vertex)

        # Add owner relationship
        self._add_owner_edge(connection_data.get("owner"), f"connection:{conn_name}")

        return vertex

    def build_function_node(self, function_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a Function node"""
        full_name = function_data.get("full_name")

        vertex = GraphSchema.create_vertex(
            id=f"function:{full_name}",
            node_type=NodeType.FUNCTION,
            name=function_data.get("name"),
            owner=function_data.get("owner"),
            active=True,
            properties={
                "full_name": full_name,
                "catalog_name": function_data.get("catalog_name"),
                "schema_name": function_data.get("schema_name"),
                "function_type": function_data.get("routine_type", ""),
            },
            metadata=function_data,
        )

        self.add_vertex(vertex)

        # Add hierarchy relationship to schema
        catalog = function_data.get("catalog_name")
        schema = function_data.get("schema_name")
        if catalog and schema:
            edge = GraphSchema.create_edge(
                src=f"schema:{catalog}.{schema}",
                dst=f"function:{full_name}",
                relationship=EdgeType.CONTAINS,
            )
            self.add_edge(edge)

        # Add owner relationship
        self._add_owner_edge(function_data.get("owner"), f"function:{full_name}")

        return vertex

    # =========================================================================
    # SECURITY NODE BUILDERS
    # =========================================================================

    def build_secret_scope_node(self, scope_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a Secret Scope node"""
        scope_name = scope_data.get("name")

        vertex = GraphSchema.create_vertex(
            id=f"secret_scope:{scope_name}",
            node_type=NodeType.SECRET_SCOPE,
            name=scope_name,
            active=True,
            properties={
                "backend_type": scope_data.get("backend_type", "DATABRICKS"),
            },
            metadata=scope_data,
        )

        self.add_vertex(vertex)
        return vertex

    def build_secret_node(self, secret_data: Dict[str, Any], scope_name: str) -> Dict[str, Any]:
        """Build a Secret node (metadata only)"""
        secret_key = secret_data.get("key")

        vertex = GraphSchema.create_vertex(
            id=f"secret:{scope_name}/{secret_key}",
            node_type=NodeType.SECRET,
            name=secret_key,
            active=True,
            properties={
                "scope": scope_name,
            },
            metadata=secret_data,
        )

        self.add_vertex(vertex)

        # Add hierarchy relationship to scope
        edge = GraphSchema.create_edge(
            src=f"secret_scope:{scope_name}",
            dst=f"secret:{scope_name}/{secret_key}",
            relationship=EdgeType.CONTAINS,
        )
        self.add_edge(edge)

        return vertex

    def build_token_node(self, token_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a Token node"""
        token_id = token_data.get("token_id")

        vertex = GraphSchema.create_vertex(
            id=f"token:{token_id}",
            node_type=NodeType.TOKEN,
            name=token_data.get("comment", f"token-{token_id}"),
            owner=token_data.get("created_by_username"),
            active=True,
            metadata=token_data,
        )

        self.add_vertex(vertex)

        # Add owner relationship
        self._add_owner_edge(token_data.get("created_by_username"), f"token:{token_id}")

        return vertex

    def build_ip_access_list_node(self, acl_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build an IP Access List node"""
        list_id = acl_data.get("list_id")

        vertex = GraphSchema.create_vertex(
            id=f"ip_access_list:{list_id}",
            node_type=NodeType.IP_ACCESS_LIST,
            name=acl_data.get("label"),
            active=acl_data.get("enabled", True),
            properties={
                "list_type": acl_data.get("list_type", ""),
            },
            metadata=acl_data,
        )

        self.add_vertex(vertex)
        return vertex

    # =========================================================================
    # APPS NODE BUILDERS
    # =========================================================================

    def build_app_node(self, app_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a Databricks App node"""
        app_name = app_data.get("name")

        vertex = GraphSchema.create_vertex(
            id=f"app:{app_name}",
            node_type=NodeType.APP,
            name=app_name,
            owner=app_data.get("creator_name"),
            active=app_data.get("status", {}).get("state") == "RUNNING",
            properties={
                "url": app_data.get("url", ""),
            },
            metadata=app_data,
        )

        self.add_vertex(vertex)

        # Add owner relationship
        self._add_owner_edge(app_data.get("creator_name"), f"app:{app_name}")

        return vertex

    # =========================================================================
    # DEVELOPMENT NODE BUILDERS
    # =========================================================================

    def build_repo_node(self, repo_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a Repo node"""
        repo_id = str(repo_data.get("id"))

        vertex = GraphSchema.create_vertex(
            id=f"repo:{repo_id}",
            node_type=NodeType.REPO,
            name=repo_data.get("path", "").split("/")[-1] if repo_data.get("path") else f"repo-{repo_id}",
            active=True,
            properties={
                "path": repo_data.get("path", ""),
                "url": repo_data.get("url", ""),
                "branch": repo_data.get("branch", ""),
            },
            metadata=repo_data,
        )

        self.add_vertex(vertex)
        return vertex

    def build_directory_node(self, dir_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a Directory node"""
        path = dir_data.get("path")

        vertex = GraphSchema.create_vertex(
            id=f"directory:{path}",
            node_type=NodeType.DIRECTORY,
            name=path.split("/")[-1] if path else "unknown",
            active=True,
            properties={
                "path": path,
            },
            metadata=dir_data,
        )

        self.add_vertex(vertex)
        return vertex
    
    def add_permission_edges(
        self,
        object_id: str,
        permissions: Dict[str, Any],
    ) -> None:
        """
        Add permission edges from permissions object
        
        Args:
            object_id: The object being granted permissions on
            permissions: Permissions data from API
        """
        acl = permissions.get("access_control_list", [])
        
        for entry in acl:
            principal = None
            
            # Determine principal
            if entry.get("user_name"):
                principal = entry["user_name"]
            elif entry.get("group_name"):
                principal = entry["group_name"]
            elif entry.get("service_principal_name"):
                principal = entry["service_principal_name"]
            
            if not principal:
                continue
            
            # Map permission levels to edge types
            perm_level = entry.get("all_permissions", [{}])[0].get("permission_level")
            
            if perm_level == "CAN_MANAGE":
                relationship = EdgeType.CAN_MANAGE
            elif perm_level == "CAN_USE":
                relationship = EdgeType.CAN_USE
            elif perm_level == "CAN_READ":
                relationship = EdgeType.CAN_READ
            elif perm_level == "CAN_RUN":
                relationship = EdgeType.CAN_USE
            elif perm_level == "CAN_EDIT":
                relationship = EdgeType.CAN_WRITE
            elif perm_level == "CAN_RESTART":
                relationship = EdgeType.CAN_RESTART
            elif perm_level == "CAN_ATTACH_TO":
                relationship = EdgeType.CAN_ATTACH_TO
            else:
                relationship = EdgeType.CAN_USE  # Default
            
            edge = GraphSchema.create_edge(
                src=principal,
                dst=object_id,
                relationship=relationship,
                permission_level=perm_level,
                inherited=entry.get("inherited", False),
            )
            self.add_edge(edge)
    
    def add_grant_edges(
        self,
        object_id: str,
        grants: List[Dict[str, Any]],
    ) -> None:
        """
        Add Unity Catalog grant edges

        Args:
            object_id: The securable object
            grants: List of grants from API
        """
        # Mapping from UC privilege names to EdgeType
        privilege_to_edge = {
            "ALL_PRIVILEGES": EdgeType.ALL_PRIVILEGES,
            "ALL PRIVILEGES": EdgeType.ALL_PRIVILEGES,
            "SELECT": EdgeType.SELECT,
            "MODIFY": EdgeType.MODIFY,
            "CREATE": EdgeType.CREATE,
            "USAGE": EdgeType.USAGE,
            "EXECUTE": EdgeType.EXECUTE,
            "READ_VOLUME": EdgeType.READ_VOLUME,
            "WRITE_VOLUME": EdgeType.WRITE_VOLUME,
            "CREATE_CATALOG": EdgeType.CREATE_CATALOG,
            "CREATE_SCHEMA": EdgeType.CREATE_SCHEMA,
            "CREATE_TABLE": EdgeType.CREATE_TABLE,
            "CREATE_VOLUME": EdgeType.CREATE_VOLUME,
            "CREATE_FUNCTION": EdgeType.CREATE_FUNCTION,
            "CREATE_MODEL": EdgeType.CREATE_MODEL,
            "CREATE_EXTERNAL_LOCATION": EdgeType.CREATE_EXTERNAL_LOCATION,
            "CREATE_STORAGE_CREDENTIAL": EdgeType.CREATE_STORAGE_CREDENTIAL,
            "CREATE_CONNECTION": EdgeType.CREATE_CONNECTION,
            "READ_FILES": EdgeType.READ_FILES,
            "WRITE_FILES": EdgeType.WRITE_FILES,
            "APPLY_TAG": EdgeType.APPLY_TAG,
            "REFRESH": EdgeType.REFRESH,
        }

        for grant in grants:
            principal = grant.get("principal")
            privileges = grant.get("privileges", [])

            if not principal:
                continue

            for priv in privileges:
                priv_name = priv.get("privilege")

                # Map privileges to edge types
                relationship = privilege_to_edge.get(priv_name, EdgeType.CAN_USE)

                edge = GraphSchema.create_edge(
                    src=principal,
                    dst=object_id,
                    relationship=relationship,
                    permission_level=priv_name,
                    inherited=priv.get("inherited", False),
                )
                self.add_edge(edge)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the built graph"""
        vertex_counts = {}
        for v in self.vertices:
            node_type = v.get("node_type")
            vertex_counts[node_type] = vertex_counts.get(node_type, 0) + 1
        
        edge_counts = {}
        for e in self.edges:
            rel_type = e.get("relationship")
            edge_counts[rel_type] = edge_counts.get(rel_type, 0) + 1
        
        return {
            "total_vertices": len(self.vertices),
            "total_edges": len(self.edges),
            "vertex_counts": vertex_counts,
            "edge_counts": edge_counts,
        }

