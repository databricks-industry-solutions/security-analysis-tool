"""
Core data collector for BrickHound

Orchestrates data collection from Databricks APIs and builds the privilege graph.
Supports both single-workspace and multi-workspace (account-level) collection.
"""

import logging
from typing import Optional, Dict, Any, List
from tqdm import tqdm

from brickhound.utils.config import DatabricksConfig, CollectorConfig
from brickhound.utils.api_client import DatabricksAPIClient
from brickhound.graph.builder import GraphBuilder
from brickhound.graph.schema import NodeType, EdgeType, GraphSchema

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatabricksCollector:
    """
    Main collector class for gathering Databricks objects and permissions.

    Supports:
    - Single workspace collection (default)
    - Multi-workspace collection via account-level APIs
    - Configurable object type collection
    """

    def __init__(
        self,
        databricks_config: Optional[DatabricksConfig] = None,
        collector_config: Optional[CollectorConfig] = None,
    ):
        """
        Initialize the collector

        Args:
            databricks_config: Databricks connection configuration
            collector_config: Collection behavior configuration
        """
        self.db_config = databricks_config or DatabricksConfig.from_env()
        self.collector_config = collector_config or CollectorConfig()

        self.api_client = DatabricksAPIClient(self.db_config)
        self.graph_builder = GraphBuilder()

        # Track current workspace context for multi-workspace collection
        self._current_workspace_id: Optional[str] = None
        self._current_workspace_url: Optional[str] = None

        logger.info("Initialized DatabricksCollector")

    # =========================================================================
    # ACCOUNT-LEVEL COLLECTION
    # =========================================================================

    def collect_account_level(self) -> None:
        """Collect account-level objects (workspaces, account users, metastores)"""
        if not self.collector_config.collect_account_level:
            logger.info("Account-level collection disabled")
            return

        if not self.api_client.account_client:
            logger.warning("Account client not initialized - skipping account-level collection")
            return

        logger.info("Starting account-level collection...")

        # Create account node
        if self.db_config.account_id:
            self.graph_builder.build_account_node(self.db_config.account_id)

        # Collect workspaces
        self._collect_workspaces()

        # Collect account-level identities
        self._collect_account_users()
        self._collect_account_groups()
        self._collect_account_service_principals()

        # Collect account-level metastores
        self._collect_account_metastores()

        logger.info("Account-level collection complete")

    def _collect_workspaces(self) -> None:
        """Collect all workspaces in the account"""
        logger.info("Collecting workspaces...")
        workspaces = self.api_client.list_workspaces()

        for ws in tqdm(workspaces, desc="Processing workspaces"):
            self.graph_builder.build_workspace_node(ws)

            # Add workspace to account relationship
            if self.db_config.account_id:
                edge = GraphSchema.create_edge(
                    src=f"account:{self.db_config.account_id}",
                    dst=f"workspace:{ws.get('workspace_id')}",
                    relationship=EdgeType.CONTAINS,
                )
                self.graph_builder.add_edge(edge)

            # Collect workspace principal assignments
            workspace_id = ws.get("workspace_id")
            if workspace_id:
                assignments = self.api_client.list_workspace_assignments(workspace_id)
                for assignment in assignments:
                    principal = assignment.get("principal", {})
                    principal_id = principal.get("principal_id")
                    if principal_id:
                        # Determine source node based on which name field is populated
                        # The API returns group_name, user_name, or service_principal_name
                        # to indicate the principal type (no principal_type field exists)
                        if principal.get("group_name"):
                            src = f"account_group:{principal_id}"
                        elif principal.get("service_principal_name"):
                            src = f"account_sp:{principal_id}"
                        else:
                            # Default to user (user_name is populated)
                            src = f"account_user:{principal_id}"

                        edge = GraphSchema.create_edge(
                            src=src,
                            dst=f"workspace:{workspace_id}",
                            relationship=EdgeType.WORKSPACE_ACCESS,
                        )
                        self.graph_builder.add_edge(edge)

                # Get metastore assignment
                metastore_assignment = self.api_client.get_metastore_assignment(workspace_id)
                if metastore_assignment:
                    metastore_id = metastore_assignment.get("metastore_id")
                    if metastore_id:
                        edge = GraphSchema.create_edge(
                            src=f"metastore:{metastore_id}",
                            dst=f"workspace:{workspace_id}",
                            relationship=EdgeType.ASSIGNED_TO,
                        )
                        self.graph_builder.add_edge(edge)

        logger.info(f"Collected {len(workspaces)} workspaces")

    def _collect_account_users(self) -> None:
        """Collect account-level users with proper account_user: prefix"""
        logger.info("Collecting account-level users...")
        users = self.api_client.list_account_users()

        for user in tqdm(users, desc="Processing account users"):
            # Use account-specific builder that creates proper account_user: prefix
            # Pass account_id to detect account-level roles like account_admin
            self.graph_builder.build_account_user_node(user, account_id=self.db_config.account_id)

        logger.info(f"Collected {len(users)} account users")

    def _collect_account_groups(self) -> None:
        """Collect account-level groups with members and MemberOf edges"""
        logger.info("Collecting account-level groups...")
        groups = self.api_client.list_account_groups()

        for group in tqdm(groups, desc="Processing account groups"):
            # Use account-specific builder that creates proper account_group: prefix
            # and MemberOf edges with account_user:/account_group: prefixes
            self.graph_builder.build_account_group_node(group)

        logger.info(f"Collected {len(groups)} account groups")

    def _collect_account_service_principals(self) -> None:
        """Collect account-level service principals with proper account_sp: prefix"""
        logger.info("Collecting account-level service principals...")
        sps = self.api_client.list_account_service_principals()

        for sp in tqdm(sps, desc="Processing account service principals"):
            # Use account-specific builder that creates proper account_sp: prefix
            # Pass account_id to detect account-level roles like account_admin
            self.graph_builder.build_account_service_principal_node(sp, account_id=self.db_config.account_id)

        logger.info(f"Collected {len(sps)} account service principals")

    def _collect_account_metastores(self) -> None:
        """Collect account-level metastores"""
        logger.info("Collecting account-level metastores...")
        metastores = self.api_client.list_account_metastores()

        for ms in tqdm(metastores, desc="Processing account metastores"):
            self.graph_builder.build_metastore_node(ms)

        logger.info(f"Collected {len(metastores)} account metastores")

    def collect_all_workspaces(self) -> None:
        """
        Collect data from all workspaces in the account.

        This method:
        1. Collects account-level objects first
        2. Iterates through all workspaces
        3. Creates a new API client for each workspace
        4. Collects workspace-level objects from each
        """
        if not self.api_client.account_client:
            logger.warning("Account client not initialized - collecting from current workspace only")
            self.collect_all()
            return

        logger.info("Starting multi-workspace collection...")

        # First collect account-level objects
        self.collect_account_level()

        # Get list of workspaces
        workspaces = self.api_client.list_workspaces()

        # Filter workspaces if specific ones are requested
        if self.collector_config.workspace_ids:
            workspaces = [
                ws for ws in workspaces
                if ws.get("workspace_id") in self.collector_config.workspace_ids
            ]

        # Collect from each workspace
        for ws in tqdm(workspaces, desc="Processing workspaces"):
            workspace_id = ws.get("workspace_id")
            workspace_name = ws.get("workspace_name")
            deployment_name = ws.get("deployment_name")

            if ws.get("workspace_status") != "RUNNING":
                logger.info(f"Skipping workspace {workspace_name} - not running")
                continue

            # Construct workspace URL
            workspace_url = f"https://{deployment_name}.cloud.databricks.com"

            logger.info(f"Collecting from workspace: {workspace_name} ({workspace_url})")

            try:
                # Create workspace-specific API client
                ws_api_client = DatabricksAPIClient(self.db_config, workspace_url=workspace_url)

                # Swap API client temporarily
                original_client = self.api_client
                self.api_client = ws_api_client
                self._current_workspace_id = str(workspace_id)
                self._current_workspace_url = workspace_url

                # Collect workspace-level objects
                self._collect_workspace_level()

                # Restore original client
                self.api_client = original_client
                self._current_workspace_id = None
                self._current_workspace_url = None

            except Exception as e:
                logger.error(f"Error collecting from workspace {workspace_name}: {e}")
                continue

        # Print final statistics
        self._print_stats()

    # =========================================================================
    # WORKSPACE-LEVEL IDENTITY COLLECTION
    # =========================================================================

    def collect_users(self) -> None:
        """Collect all workspace users"""
        if not self.collector_config.collect_users:
            return
        logger.info("Collecting users...")
        users = self.api_client.list_users()

        for user in tqdm(users, desc="Processing users"):
            self.graph_builder.build_user_node(user)

        logger.info(f"Collected {len(users)} users")

    def collect_groups(self) -> None:
        """Collect all workspace groups"""
        if not self.collector_config.collect_groups:
            return
        logger.info("Collecting groups...")
        groups = self.api_client.list_groups()

        for group in tqdm(groups, desc="Processing groups"):
            self.graph_builder.build_group_node(group)

        logger.info(f"Collected {len(groups)} groups")

    def collect_service_principals(self) -> None:
        """Collect all service principals"""
        if not self.collector_config.collect_service_principals:
            return
        logger.info("Collecting service principals...")
        sps = self.api_client.list_service_principals()

        for sp in tqdm(sps, desc="Processing service principals"):
            self.graph_builder.build_service_principal_node(sp)

        logger.info(f"Collected {len(sps)} service principals")

    # =========================================================================
    # COMPUTE COLLECTION
    # =========================================================================

    def collect_clusters(self) -> None:
        """Collect all clusters with permissions"""
        if not self.collector_config.collect_clusters:
            return
        logger.info("Collecting clusters...")
        clusters = self.api_client.list_clusters()

        for cluster in tqdm(clusters, desc="Processing clusters"):
            self.graph_builder.build_cluster_node(cluster)

            # Get permissions if enabled
            if self.collector_config.collect_permissions:
                cluster_id = cluster.get("cluster_id")
                if cluster_id:
                    perms = self.api_client.get_permissions("clusters", cluster_id)
                    if perms:
                        self.graph_builder.add_permission_edges(cluster_id, perms)

        logger.info(f"Collected {len(clusters)} clusters")

    def collect_instance_pools(self) -> None:
        """Collect all instance pools with permissions"""
        if not self.collector_config.collect_instance_pools:
            return
        logger.info("Collecting instance pools...")
        pools = self.api_client.list_instance_pools()

        for pool in tqdm(pools, desc="Processing instance pools"):
            self.graph_builder.build_instance_pool_node(pool)

            # Get permissions if enabled
            if self.collector_config.collect_permissions:
                pool_id = pool.get("instance_pool_id")
                if pool_id:
                    perms = self.api_client.get_permissions("instance-pools", pool_id)
                    if perms:
                        self.graph_builder.add_permission_edges(pool_id, perms)

        logger.info(f"Collected {len(pools)} instance pools")

    def collect_cluster_policies(self) -> None:
        """Collect all cluster policies with permissions"""
        if not self.collector_config.collect_cluster_policies:
            return
        logger.info("Collecting cluster policies...")
        policies = self.api_client.list_cluster_policies()

        for policy in tqdm(policies, desc="Processing cluster policies"):
            self.graph_builder.build_cluster_policy_node(policy)

            # Get permissions if enabled
            if self.collector_config.collect_permissions:
                policy_id = policy.get("policy_id")
                if policy_id:
                    perms = self.api_client.get_permissions("cluster-policies", policy_id)
                    if perms:
                        self.graph_builder.add_permission_edges(policy_id, perms)

        logger.info(f"Collected {len(policies)} cluster policies")

    def collect_global_init_scripts(self) -> None:
        """Collect all global init scripts"""
        if not self.collector_config.collect_global_init_scripts:
            return
        logger.info("Collecting global init scripts...")
        scripts = self.api_client.list_global_init_scripts()

        for script in tqdm(scripts, desc="Processing global init scripts"):
            self.graph_builder.build_global_init_script_node(script)

        logger.info(f"Collected {len(scripts)} global init scripts")

    # =========================================================================
    # AI/ML COLLECTION
    # =========================================================================

    def collect_serving_endpoints(self) -> None:
        """Collect all model serving endpoints with permissions"""
        if not self.collector_config.collect_serving_endpoints:
            return
        logger.info("Collecting serving endpoints...")
        endpoints = self.api_client.list_serving_endpoints()

        for endpoint in tqdm(endpoints, desc="Processing serving endpoints"):
            self.graph_builder.build_serving_endpoint_node(endpoint)

            # Get permissions if enabled
            if self.collector_config.collect_permissions:
                endpoint_name = endpoint.get("name")
                if endpoint_name:
                    perms = self.api_client.get_permissions("serving-endpoints", endpoint_name)
                    if perms:
                        self.graph_builder.add_permission_edges(
                            f"serving_endpoint:{endpoint_name}", perms
                        )

        logger.info(f"Collected {len(endpoints)} serving endpoints")

    def collect_vector_search_endpoints(self) -> None:
        """Collect all vector search endpoints"""
        if not self.collector_config.collect_vector_search_endpoints:
            return
        logger.info("Collecting vector search endpoints...")
        endpoints = self.api_client.list_vector_search_endpoints()

        for endpoint in tqdm(endpoints, desc="Processing vector search endpoints"):
            self.graph_builder.build_vector_search_endpoint_node(endpoint)

        logger.info(f"Collected {len(endpoints)} vector search endpoints")

    def collect_vector_search_indexes(self) -> None:
        """Collect all vector search indexes"""
        if not self.collector_config.collect_vector_search_indexes:
            return
        logger.info("Collecting vector search indexes...")
        indexes = self.api_client.list_vector_search_indexes()

        for index in tqdm(indexes, desc="Processing vector search indexes"):
            self.graph_builder.build_vector_search_index_node(index)

        logger.info(f"Collected {len(indexes)} vector search indexes")

    def collect_registered_models(self) -> None:
        """Collect all registered models (Unity Catalog)"""
        if not self.collector_config.collect_registered_models:
            return
        logger.info("Collecting registered models...")
        models = self.api_client.list_registered_models()

        for model in tqdm(models, desc="Processing registered models"):
            self.graph_builder.build_registered_model_node(model)

            # Get grants if enabled
            if self.collector_config.collect_permissions:
                full_name = model.get("full_name")
                if full_name:
                    grants = self.api_client.get_grants("function", full_name)
                    if grants:
                        self.graph_builder.add_grant_edges(f"model:{full_name}", grants)

        logger.info(f"Collected {len(models)} registered models")

    def collect_experiments(self) -> None:
        """Collect all MLflow experiments with permissions"""
        if not self.collector_config.collect_experiments:
            return
        logger.info("Collecting experiments...")
        experiments = self.api_client.list_experiments()

        for exp in tqdm(experiments, desc="Processing experiments"):
            self.graph_builder.build_experiment_node(exp)

            # Get permissions if enabled
            if self.collector_config.collect_permissions:
                exp_id = exp.get("experiment_id")
                if exp_id:
                    perms = self.api_client.get_permissions("experiments", exp_id)
                    if perms:
                        self.graph_builder.add_permission_edges(f"experiment:{exp_id}", perms)

        logger.info(f"Collected {len(experiments)} experiments")

    # =========================================================================
    # ANALYTICS/BI COLLECTION
    # =========================================================================

    def collect_dashboards(self) -> None:
        """Collect all Lakeview dashboards with permissions"""
        if not self.collector_config.collect_dashboards:
            return
        logger.info("Collecting dashboards...")
        dashboards = self.api_client.list_dashboards()

        for dashboard in tqdm(dashboards, desc="Processing dashboards"):
            self.graph_builder.build_dashboard_node(dashboard)

            # Get permissions if enabled
            if self.collector_config.collect_permissions:
                dashboard_id = dashboard.get("dashboard_id")
                if dashboard_id:
                    perms = self.api_client.get_permissions("dashboards", dashboard_id)
                    if perms:
                        self.graph_builder.add_permission_edges(
                            f"dashboard:{dashboard_id}", perms
                        )

        logger.info(f"Collected {len(dashboards)} dashboards")

    def collect_queries(self) -> None:
        """Collect all SQL queries with permissions"""
        if not self.collector_config.collect_queries:
            return
        logger.info("Collecting queries...")
        queries = self.api_client.list_queries()

        for query in tqdm(queries, desc="Processing queries"):
            self.graph_builder.build_query_node(query)

            # Get permissions if enabled
            if self.collector_config.collect_permissions:
                query_id = query.get("id")
                if query_id:
                    perms = self.api_client.get_permissions("queries", query_id)
                    if perms:
                        self.graph_builder.add_permission_edges(f"query:{query_id}", perms)

        logger.info(f"Collected {len(queries)} queries")

    def collect_alerts(self) -> None:
        """Collect all alerts"""
        if not self.collector_config.collect_alerts:
            return
        logger.info("Collecting alerts...")
        alerts = self.api_client.list_alerts()

        for alert in tqdm(alerts, desc="Processing alerts"):
            self.graph_builder.build_alert_node(alert)

        logger.info(f"Collected {len(alerts)} alerts")

    # =========================================================================
    # ORCHESTRATION COLLECTION
    # =========================================================================

    def collect_jobs(self) -> None:
        """Collect all jobs with permissions"""
        if not self.collector_config.collect_jobs:
            return
        logger.info("Collecting jobs...")
        jobs = self.api_client.list_jobs()

        for job in tqdm(jobs, desc="Processing jobs"):
            self.graph_builder.build_job_node(job)

            # Get permissions if enabled
            if self.collector_config.collect_permissions:
                job_id = str(job.get("job_id"))
                if job_id:
                    perms = self.api_client.get_permissions("jobs", job_id)
                    if perms:
                        self.graph_builder.add_permission_edges(job_id, perms)

        logger.info(f"Collected {len(jobs)} jobs")

    def collect_pipelines(self) -> None:
        """Collect all DLT pipelines with permissions"""
        if not self.collector_config.collect_pipelines:
            return
        logger.info("Collecting pipelines...")
        pipelines = self.api_client.list_pipelines()

        for pipeline in tqdm(pipelines, desc="Processing pipelines"):
            self.graph_builder.build_pipeline_node(pipeline)

            # Get permissions if enabled
            if self.collector_config.collect_permissions:
                pipeline_id = pipeline.get("pipeline_id")
                if pipeline_id:
                    perms = self.api_client.get_permissions("pipelines", pipeline_id)
                    if perms:
                        self.graph_builder.add_permission_edges(
                            f"pipeline:{pipeline_id}", perms
                        )

        logger.info(f"Collected {len(pipelines)} pipelines")

    # =========================================================================
    # DEVELOPMENT COLLECTION
    # =========================================================================

    def collect_notebooks(self) -> None:
        """Collect all notebooks with permissions"""
        if not self.collector_config.collect_notebooks:
            return
        logger.info("Collecting notebooks...")
        notebooks = self.api_client.list_notebooks("/")

        for notebook in tqdm(notebooks, desc="Processing notebooks"):
            self.graph_builder.build_notebook_node(notebook)

            # Get permissions if enabled
            if self.collector_config.collect_permissions:
                path = notebook.get("path")
                if path:
                    perms = self.api_client.get_permissions("notebooks", path)
                    if perms:
                        self.graph_builder.add_permission_edges(path, perms)

        logger.info(f"Collected {len(notebooks)} notebooks")

    def collect_repos(self) -> None:
        """Collect all repos with permissions"""
        if not self.collector_config.collect_repos:
            return
        logger.info("Collecting repos...")
        repos = self.api_client.list_repos()

        for repo in tqdm(repos, desc="Processing repos"):
            self.graph_builder.build_repo_node(repo)

            # Get permissions if enabled
            if self.collector_config.collect_permissions:
                repo_id = str(repo.get("id"))
                if repo_id:
                    perms = self.api_client.get_permissions("repos", repo_id)
                    if perms:
                        self.graph_builder.add_permission_edges(f"repo:{repo_id}", perms)

        logger.info(f"Collected {len(repos)} repos")

    # =========================================================================
    # DATA & ANALYTICS (SQL WAREHOUSES)
    # =========================================================================

    def collect_warehouses(self) -> None:
        """Collect all SQL warehouses with permissions"""
        if not self.collector_config.collect_warehouses:
            return
        logger.info("Collecting SQL warehouses...")
        warehouses = self.api_client.list_warehouses()

        for warehouse in tqdm(warehouses, desc="Processing warehouses"):
            self.graph_builder.build_warehouse_node(warehouse)

            # Get permissions if enabled
            if self.collector_config.collect_permissions:
                wh_id = warehouse.get("id")
                if wh_id:
                    perms = self.api_client.get_permissions("sql/warehouses", wh_id)
                    if perms:
                        self.graph_builder.add_permission_edges(wh_id, perms)

        logger.info(f"Collected {len(warehouses)} warehouses")

    # =========================================================================
    # SECURITY COLLECTION
    # =========================================================================

    def collect_secret_scopes(self) -> None:
        """Collect all secret scopes with secrets and ACLs"""
        if not self.collector_config.collect_secret_scopes:
            return
        logger.info("Collecting secret scopes...")
        scopes = self.api_client.list_secret_scopes()

        for scope in tqdm(scopes, desc="Processing secret scopes"):
            scope_name = scope.get("name")
            self.graph_builder.build_secret_scope_node(scope)

            # Collect secrets in this scope
            secrets = self.api_client.list_secrets(scope_name)
            for secret in secrets:
                self.graph_builder.build_secret_node(secret, scope_name)

            # Collect ACLs for this scope
            acls = self.api_client.list_secret_acls(scope_name)
            for acl in acls:
                principal = acl.get("principal")
                permission = acl.get("permission")
                if principal and permission:
                    # Map permission to edge type
                    if permission == "MANAGE":
                        rel = EdgeType.CAN_MANAGE_SECRET
                    elif permission == "WRITE":
                        rel = EdgeType.CAN_WRITE_SECRET
                    else:
                        rel = EdgeType.CAN_READ_SECRET

                    edge = GraphSchema.create_edge(
                        src=principal,
                        dst=f"secret_scope:{scope_name}",
                        relationship=rel,
                        permission_level=permission,
                    )
                    self.graph_builder.add_edge(edge)

        logger.info(f"Collected {len(scopes)} secret scopes")

    def collect_tokens(self) -> None:
        """Collect all tokens"""
        if not self.collector_config.collect_tokens:
            return
        logger.info("Collecting tokens...")
        tokens = self.api_client.list_tokens()

        for token in tqdm(tokens, desc="Processing tokens"):
            self.graph_builder.build_token_node(token)

        logger.info(f"Collected {len(tokens)} tokens")

    def collect_ip_access_lists(self) -> None:
        """Collect all IP access lists"""
        if not self.collector_config.collect_ip_access_lists:
            return
        logger.info("Collecting IP access lists...")
        lists = self.api_client.list_ip_access_lists()

        for acl in tqdm(lists, desc="Processing IP access lists"):
            self.graph_builder.build_ip_access_list_node(acl)

        logger.info(f"Collected {len(lists)} IP access lists")

    # =========================================================================
    # APPS COLLECTION
    # =========================================================================

    def collect_apps(self) -> None:
        """Collect all Databricks Apps"""
        if not self.collector_config.collect_apps:
            return
        logger.info("Collecting apps...")
        apps = self.api_client.list_apps()

        for app in tqdm(apps, desc="Processing apps"):
            self.graph_builder.build_app_node(app)

        logger.info(f"Collected {len(apps)} apps")

    # =========================================================================
    # UNITY CATALOG COLLECTION
    # =========================================================================

    def collect_unity_catalog(self) -> None:
        """Collect Unity Catalog objects (catalogs, schemas, tables, etc.)"""
        if not self.collector_config.collect_unity_catalog:
            logger.info("Unity Catalog collection disabled")
            return

        logger.info("Collecting Unity Catalog objects...")

        # Collect metastores (workspace-level view)
        if self.collector_config.collect_metastores:
            self._collect_metastores()

        # Collect storage credentials
        if self.collector_config.collect_storage_credentials:
            self._collect_storage_credentials()

        # Collect external locations
        if self.collector_config.collect_external_locations:
            self._collect_external_locations()

        # Collect connections
        if self.collector_config.collect_connections:
            self._collect_connections()

        # Collect catalogs
        catalogs = self.api_client.list_catalogs()

        # Filter out system catalogs that cause excessive noise
        system_catalogs = {'__databricks_internal', 'system'}
        catalogs = [c for c in catalogs if c.get('name') not in system_catalogs]

        logger.info(f"Found {len(catalogs)} catalogs (excluding system catalogs)")

        for catalog in tqdm(catalogs, desc="Processing catalogs"):
            catalog_name = catalog.get("name")
            self.graph_builder.build_catalog_node(catalog)

            # Get catalog grants
            if self.collector_config.collect_permissions:
                grants = self.api_client.get_grants("catalog", catalog_name)
                if grants:
                    self.graph_builder.add_grant_edges(
                        f"catalog:{catalog_name}",
                        grants
                    )

            # Collect schemas in this catalog
            schemas = self.api_client.list_schemas(catalog_name)

            for schema in tqdm(schemas, desc=f"Processing schemas in {catalog_name}", leave=False):
                schema_name = schema.get("name")
                full_schema_name = f"{catalog_name}.{schema_name}"

                self.graph_builder.build_schema_node(schema, catalog_name)

                # Get schema grants
                if self.collector_config.collect_permissions:
                    grants = self.api_client.get_grants("schema", full_schema_name)
                    if grants:
                        self.graph_builder.add_grant_edges(
                            f"schema:{full_schema_name}",
                            grants
                        )

                # Collect tables in this schema
                tables = self.api_client.list_tables(catalog_name, schema_name)

                for table in tqdm(tables, desc=f"Processing tables in {full_schema_name}", leave=False):
                    self.graph_builder.build_table_node(table)

                    # Get table grants
                    if self.collector_config.collect_permissions:
                        table_full_name = table.get("full_name")
                        if table_full_name:
                            grants = self.api_client.get_grants("table", table_full_name)
                            if grants:
                                self.graph_builder.add_grant_edges(
                                    f"table:{table_full_name}",
                                    grants
                                )

                # Collect volumes in this schema
                volumes = self.api_client.list_volumes(catalog_name, schema_name)

                for volume in volumes:
                    volume_name = volume.get("name")
                    full_volume_name = volume.get("full_name")

                    vertex = GraphSchema.create_vertex(
                        id=f"volume:{full_volume_name}",
                        node_type=NodeType.VOLUME,
                        name=volume_name,
                        owner=volume.get("owner"),
                        properties={"full_name": full_volume_name},
                        metadata=volume,
                    )
                    self.graph_builder.add_vertex(vertex)

                    # Add hierarchy relationship
                    edge = GraphSchema.create_edge(
                        src=f"schema:{full_schema_name}",
                        dst=f"volume:{full_volume_name}",
                        relationship=EdgeType.CONTAINS,
                    )
                    self.graph_builder.add_edge(edge)

                    # Get volume grants
                    if self.collector_config.collect_permissions and full_volume_name:
                        grants = self.api_client.get_grants("volume", full_volume_name)
                        if grants:
                            self.graph_builder.add_grant_edges(
                                f"volume:{full_volume_name}",
                                grants
                            )

                # Collect functions in this schema
                functions = self.api_client.list_functions(catalog_name, schema_name)

                for func in functions:
                    self.graph_builder.build_function_node(func)

                    # Get function grants
                    if self.collector_config.collect_permissions:
                        func_full_name = func.get("full_name")
                        if func_full_name:
                            grants = self.api_client.get_grants("function", func_full_name)
                            if grants:
                                self.graph_builder.add_grant_edges(
                                    f"function:{func_full_name}",
                                    grants
                                )

        logger.info("Unity Catalog collection complete")

    def _collect_metastores(self) -> None:
        """Collect workspace-visible metastores"""
        logger.info("Collecting metastores...")
        metastores = self.api_client.list_metastores()

        for ms in tqdm(metastores, desc="Processing metastores"):
            self.graph_builder.build_metastore_node(ms)

            # Get metastore grants
            if self.collector_config.collect_permissions:
                metastore_id = ms.get("metastore_id")
                if metastore_id:
                    grants = self.api_client.get_grants("metastore", metastore_id)
                    if grants:
                        self.graph_builder.add_grant_edges(
                            f"metastore:{metastore_id}",
                            grants
                        )

        logger.info(f"Collected {len(metastores)} metastores")

    def _collect_storage_credentials(self) -> None:
        """Collect storage credentials"""
        logger.info("Collecting storage credentials...")
        credentials = self.api_client.list_storage_credentials()

        for cred in tqdm(credentials, desc="Processing storage credentials"):
            self.graph_builder.build_storage_credential_node(cred)

            # Get grants
            if self.collector_config.collect_permissions:
                cred_name = cred.get("name")
                if cred_name:
                    grants = self.api_client.get_grants("storage_credential", cred_name)
                    if grants:
                        self.graph_builder.add_grant_edges(
                            f"storage_credential:{cred_name}",
                            grants
                        )

        logger.info(f"Collected {len(credentials)} storage credentials")

    def _collect_external_locations(self) -> None:
        """Collect external locations"""
        logger.info("Collecting external locations...")
        locations = self.api_client.list_external_locations()

        for loc in tqdm(locations, desc="Processing external locations"):
            self.graph_builder.build_external_location_node(loc)

            # Get grants
            if self.collector_config.collect_permissions:
                loc_name = loc.get("name")
                if loc_name:
                    grants = self.api_client.get_grants("external_location", loc_name)
                    if grants:
                        self.graph_builder.add_grant_edges(
                            f"external_location:{loc_name}",
                            grants
                        )

        logger.info(f"Collected {len(locations)} external locations")

    def _collect_connections(self) -> None:
        """Collect connections (foreign catalogs)"""
        logger.info("Collecting connections...")
        connections = self.api_client.list_connections()

        for conn in tqdm(connections, desc="Processing connections"):
            self.graph_builder.build_connection_node(conn)

            # Get grants
            if self.collector_config.collect_permissions:
                conn_name = conn.get("name")
                if conn_name:
                    grants = self.api_client.get_grants("connection", conn_name)
                    if grants:
                        self.graph_builder.add_grant_edges(
                            f"connection:{conn_name}",
                            grants
                        )

        logger.info(f"Collected {len(connections)} connections")

    # =========================================================================
    # MAIN COLLECTION METHODS
    # =========================================================================

    def _collect_workspace_level(self) -> None:
        """Collect all workspace-level objects (internal method)"""
        # Identity & Access
        self.collect_users()
        self.collect_groups()
        self.collect_service_principals()

        # Compute
        self.collect_clusters()
        self.collect_instance_pools()
        self.collect_cluster_policies()
        self.collect_global_init_scripts()

        # AI/ML
        self.collect_serving_endpoints()
        self.collect_vector_search_endpoints()
        self.collect_vector_search_indexes()
        self.collect_registered_models()
        self.collect_experiments()

        # Analytics/BI
        self.collect_dashboards()
        self.collect_queries()
        self.collect_alerts()

        # Development
        self.collect_notebooks()
        self.collect_repos()

        # Orchestration
        self.collect_jobs()
        self.collect_pipelines()

        # Data & Analytics
        self.collect_warehouses()
        if self.collector_config.collect_unity_catalog:
            self.collect_unity_catalog()

        # Security
        self.collect_secret_scopes()
        self.collect_tokens()
        self.collect_ip_access_lists()

        # Apps
        self.collect_apps()

    def collect_all(self) -> None:
        """Collect all Databricks objects from current workspace"""
        logger.info("Starting comprehensive data collection...")

        try:
            self._collect_workspace_level()
            self._print_stats()

        except Exception as e:
            logger.error(f"Error during collection: {e}", exc_info=True)
            raise

    def _print_stats(self) -> None:
        """Print collection statistics"""
        stats = self.graph_builder.get_stats()
        logger.info("Collection complete!")
        logger.info(f"Total vertices: {stats['total_vertices']}")
        logger.info(f"Total edges: {stats['total_edges']}")
        logger.info(f"Vertex breakdown: {stats['vertex_counts']}")

    def save_to_spark(self, spark, catalog: str = "brickhound", schema: str = "graph") -> None:
        """
        Save collected graph to Delta Lake using Spark

        Args:
            spark: SparkSession
            catalog: Target catalog name (must already exist)
            schema: Target schema name

        Note:
            Catalog must exist before calling this method. Create it manually or use an existing catalog.
            This method will NOT create the catalog (requires metastore admin permissions).
        """
        import pandas as pd
        import json

        logger.info(f"Saving graph to {catalog}.{schema}...")

        # Use existing catalog (don't try to create it - may not have permission)
        try:
            spark.sql(f"USE CATALOG {catalog}")
            logger.info(f"Using catalog '{catalog}'")
        except Exception as e:
            logger.error(f"Cannot use catalog '{catalog}': {e}")
            logger.error("Please create the catalog first or use an existing one like 'main'")
            raise

        # Create schema if it doesn't exist
        spark.sql(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        logger.info(f"Using schema '{schema}'")

        # Convert vertices to DataFrame with metadata/properties as JSON strings
        vertices_data = []
        for v in self.graph_builder.vertices:
            v_copy = v.copy()
            # Convert metadata and properties to JSON strings (required for Delta Lake)
            v_copy['metadata'] = json.dumps(v_copy.get('metadata'))
            v_copy['properties'] = json.dumps(v_copy.get('properties'))
            vertices_data.append(v_copy)

        vertices_df = spark.createDataFrame(pd.DataFrame(vertices_data))

        # Write vertices
        vertices_table = f"{catalog}.{schema}.vertices"
        vertices_df.write.format("delta").mode("overwrite").saveAsTable(vertices_table)
        logger.info(f"Saved {vertices_df.count()} vertices to {vertices_table}")

        # Convert edges to DataFrame with properties as JSON strings
        edges_data = []
        for e in self.graph_builder.edges:
            e_copy = e.copy()
            # Convert properties to JSON string (required for Delta Lake)
            e_copy['properties'] = json.dumps(e_copy.get('properties'))
            edges_data.append(e_copy)

        edges_df = spark.createDataFrame(pd.DataFrame(edges_data))

        # Write edges
        edges_table = f"{catalog}.{schema}.edges"
        edges_df.write.format("delta").mode("overwrite").saveAsTable(edges_table)
        logger.info(f"Saved {edges_df.count()} edges to {edges_table}")

        logger.info("Graph saved successfully!")

    def get_graph_data(self) -> Dict[str, Any]:
        """
        Get the collected graph data

        Returns:
            Dictionary with vertices and edges
        """
        return {
            "vertices": self.graph_builder.vertices,
            "edges": self.graph_builder.edges,
            "stats": self.graph_builder.get_stats(),
        }

    @staticmethod
    def get_collection_scope() -> Dict[str, List[str]]:
        """
        Return a dictionary documenting all object types currently in scope for collection.

        Returns:
            Dictionary with categories and their object types
        """
        return {
            "Identity": [
                "Users",
                "Groups",
                "Service Principals",
            ],
            "Compute": [
                "Clusters",
                "Instance Pools",
                "Cluster Policies",
                "Global Init Scripts",
            ],
            "AI/ML": [
                "Serving Endpoints",
                "Vector Search Endpoints",
                "Vector Search Indexes",
                "Registered Models (Unity Catalog)",
                "MLflow Experiments",
            ],
            "Analytics/BI": [
                "Dashboards (Lakeview)",
                "SQL Queries",
                "Alerts",
            ],
            "Development": [
                "Notebooks",
                "Repos",
                "Directories",
            ],
            "Orchestration": [
                "Jobs",
                "Pipelines (Delta Live Tables)",
            ],
            "Data & Analytics": [
                "SQL Warehouses",
                "Metastores",
                "Catalogs",
                "Schemas",
                "Tables",
                "Views",
                "Volumes",
                "Functions",
                "External Locations",
                "Storage Credentials",
                "Connections",
            ],
            "Security": [
                "Secret Scopes",
                "Secrets",
                "Tokens",
                "IP Access Lists",
            ],
            "Apps": [
                "Databricks Apps",
            ],
            "Account-Level": [
                "Workspaces",
                "Account Users",
                "Account Groups",
                "Account Service Principals",
                "Account Metastores",
                "Workspace Assignments",
                "Metastore Assignments",
            ],
        }
