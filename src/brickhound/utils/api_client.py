"""
Databricks REST API client wrapper

Supports both workspace-level and account-level APIs for multi-workspace collection.
"""

import logging
from typing import Any, Dict, List, Optional
from databricks.sdk import WorkspaceClient, AccountClient
from databricks.sdk.core import Config
from brickhound.utils.config import DatabricksConfig

__all__ = ["DatabricksAPIClient"]

logger = logging.getLogger(__name__)


class DatabricksAPIClient:
    """Wrapper for Databricks SDK with retry logic and account-level support"""

    def _list_with_error_handling(
        self,
        list_func,
        resource_name: str,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Generic helper to list resources with consistent error handling.

        Args:
            list_func: The SDK list method to call
            resource_name: Name of the resource for logging
            **kwargs: Additional arguments to pass to list_func

        Returns:
            List of dictionaries representing the resources
        """
        try:
            items = list(list_func(**kwargs) if kwargs else list_func())
            return [item.as_dict() for item in items]
        except Exception as e:
            logger.error(f"Error listing {resource_name}: {e}")
            return []

    def __init__(self, config: DatabricksConfig, workspace_url: Optional[str] = None):
        """
        Initialize API client

        Args:
            config: Databricks configuration
            workspace_url: Optional workspace URL override (for multi-workspace collection)
        """
        config.validate()
        self.config = config

        # Use provided workspace_url or fall back to config
        effective_workspace_url = workspace_url or config.workspace_url

        # Initialize workspace client
        sdk_config = Config(
            host=effective_workspace_url,
            token=config.token,
            client_id=config.client_id,
            client_secret=config.client_secret,
        )
        self.workspace_client = WorkspaceClient(config=sdk_config)
        self.workspace_url = effective_workspace_url

        # Initialize account client if account_id provided
        self.account_client = None
        if config.account_id:
            # Determine account host based on cloud provider
            account_host = self._get_account_host(effective_workspace_url)
            account_config = Config(
                host=account_host,
                account_id=config.account_id,
                client_id=config.client_id,
                client_secret=config.client_secret,
            )
            self.account_client = AccountClient(config=account_config)

        logger.info(f"Initialized API client for {effective_workspace_url}")

    def _get_account_host(self, workspace_url: str) -> str:
        """Determine the account console host based on workspace URL"""
        if "azure" in workspace_url.lower() or "azuredatabricks" in workspace_url.lower():
            return "https://accounts.azuredatabricks.net"
        elif "gcp" in workspace_url.lower():
            return "https://accounts.gcp.databricks.com"
        else:
            # Default to AWS
            return "https://accounts.cloud.databricks.com"

    # =========================================================================
    # ACCOUNT-LEVEL APIs
    # =========================================================================

    def list_workspaces(self) -> List[Dict[str, Any]]:
        """List all workspaces in the account (requires account admin)"""
        if not self.account_client:
            logger.warning("Account client not initialized - cannot list workspaces")
            return []
        try:
            workspaces = list(self.account_client.workspaces.list())
            return [ws.as_dict() for ws in workspaces]
        except Exception as e:
            logger.error(f"Error listing workspaces: {e}")
            return []

    def list_account_users(self) -> List[Dict[str, Any]]:
        """List all users at account level with full details including roles"""
        if not self.account_client:
            logger.warning("Account client not initialized - cannot list account users")
            return []
        try:
            # First get list of all users (without full details)
            users = list(self.account_client.users.list())

            # For each user, fetch full details including roles
            full_users = []
            for user in users:
                try:
                    # Get full user details with roles
                    full_user = self.account_client.users.get(user.id)
                    full_users.append(full_user.as_dict())
                except Exception as e:
                    logger.warning(f"Error getting full details for user {user.id}: {e}")
                    # Fall back to basic user info
                    full_users.append(user.as_dict())

            return full_users
        except Exception as e:
            logger.error(f"Error listing account users: {e}")
            return []

    def list_account_groups(self) -> List[Dict[str, Any]]:
        """List all groups at account level with full details including members"""
        if not self.account_client:
            logger.warning("Account client not initialized - cannot list account groups")
            return []
        try:
            # First get list of all groups (without members)
            groups = list(self.account_client.groups.list())

            # For each group, fetch full details including members
            full_groups = []
            for group in groups:
                try:
                    # Get full group details with members
                    full_group = self.account_client.groups.get(group.id)
                    full_groups.append(full_group.as_dict())
                except Exception as e:
                    logger.warning(f"Error getting full details for group {group.id}: {e}")
                    # Fall back to basic group info
                    full_groups.append(group.as_dict())

            return full_groups
        except Exception as e:
            logger.error(f"Error listing account groups: {e}")
            return []

    def list_account_service_principals(self) -> List[Dict[str, Any]]:
        """List all service principals at account level with full details including roles"""
        if not self.account_client:
            logger.warning("Account client not initialized - cannot list account service principals")
            return []
        try:
            # First get list of all service principals (without full details)
            sps = list(self.account_client.service_principals.list())

            # For each SP, fetch full details including roles
            full_sps = []
            for sp in sps:
                try:
                    # Get full SP details with roles
                    full_sp = self.account_client.service_principals.get(sp.id)
                    full_sps.append(full_sp.as_dict())
                except Exception as e:
                    logger.warning(f"Error getting full details for service principal {sp.id}: {e}")
                    # Fall back to basic SP info
                    full_sps.append(sp.as_dict())

            return full_sps
        except Exception as e:
            logger.error(f"Error listing account service principals: {e}")
            return []

    def list_account_metastores(self) -> List[Dict[str, Any]]:
        """List all metastores at account level"""
        if not self.account_client:
            logger.warning("Account client not initialized - cannot list account metastores")
            return []
        try:
            metastores = list(self.account_client.metastores.list())
            return [ms.as_dict() for ms in metastores]
        except Exception as e:
            logger.error(f"Error listing account metastores: {e}")
            return []

    def list_workspace_assignments(self, workspace_id: int) -> List[Dict[str, Any]]:
        """List principal assignments for a workspace"""
        if not self.account_client:
            logger.warning("Account client not initialized - cannot list workspace assignments")
            return []
        try:
            assignments = list(self.account_client.workspace_assignment.list(workspace_id=workspace_id))
            return [a.as_dict() for a in assignments]
        except Exception as e:
            logger.error(f"Error listing workspace assignments for {workspace_id}: {e}")
            return []

    def get_metastore_assignment(self, workspace_id: int) -> Optional[Dict[str, Any]]:
        """Get metastore assignment for a workspace"""
        if not self.account_client:
            return None
        try:
            assignment = self.account_client.metastore_assignments.get(workspace_id=workspace_id)
            return assignment.as_dict() if assignment else None
        except Exception as e:
            logger.debug(f"No metastore assignment for workspace {workspace_id}: {e}")
            return None

    # =========================================================================
    # WORKSPACE-LEVEL IDENTITY APIs
    # =========================================================================

    def list_users(self) -> List[Dict[str, Any]]:
        """List all workspace users"""
        return self._list_with_error_handling(
            self.workspace_client.users.list, "users"
        )

    def list_groups(self) -> List[Dict[str, Any]]:
        """List all workspace groups"""
        return self._list_with_error_handling(
            self.workspace_client.groups.list, "groups"
        )

    def list_service_principals(self) -> List[Dict[str, Any]]:
        """List all service principals"""
        return self._list_with_error_handling(
            self.workspace_client.service_principals.list, "service principals"
        )

    def list_clusters(self) -> List[Dict[str, Any]]:
        """List all clusters"""
        return self._list_with_error_handling(
            self.workspace_client.clusters.list, "clusters"
        )

    def list_jobs(self) -> List[Dict[str, Any]]:
        """List all jobs"""
        return self._list_with_error_handling(
            self.workspace_client.jobs.list, "jobs"
        )
    
    def list_notebooks(self, path: str = "/") -> List[Dict[str, Any]]:
        """List notebooks recursively"""
        notebooks = []
        try:
            objects = list(self.workspace_client.workspace.list(path))
            for obj in objects:
                obj_dict = obj.as_dict()
                if obj_dict.get("object_type") == "NOTEBOOK":
                    notebooks.append(obj_dict)
                elif obj_dict.get("object_type") == "DIRECTORY":
                    # Recursively list notebooks in subdirectories
                    notebooks.extend(self.list_notebooks(obj_dict.get("path", "")))
        except Exception as e:
            logger.error(f"Error listing notebooks in {path}: {e}")
        
        return notebooks
    
    def list_repos(self) -> List[Dict[str, Any]]:
        """List all repos"""
        return self._list_with_error_handling(
            self.workspace_client.repos.list, "repos"
        )

    def list_warehouses(self) -> List[Dict[str, Any]]:
        """List all SQL warehouses"""
        return self._list_with_error_handling(
            self.workspace_client.warehouses.list, "warehouses"
        )

    def list_instance_pools(self) -> List[Dict[str, Any]]:
        """List all instance pools"""
        return self._list_with_error_handling(
            self.workspace_client.instance_pools.list, "instance pools"
        )

    def list_secret_scopes(self) -> List[Dict[str, Any]]:
        """List all secret scopes"""
        return self._list_with_error_handling(
            self.workspace_client.secrets.list_scopes, "secret scopes"
        )

    def list_catalogs(self) -> List[Dict[str, Any]]:
        """List Unity Catalog catalogs"""
        return self._list_with_error_handling(
            self.workspace_client.catalogs.list, "catalogs"
        )
    
    def list_schemas(self, catalog_name: str) -> List[Dict[str, Any]]:
        """List schemas in a catalog"""
        try:
            schemas = list(self.workspace_client.schemas.list(catalog_name=catalog_name))
            return [schema.as_dict() for schema in schemas]
        except Exception as e:
            logger.error(f"Error listing schemas in {catalog_name}: {e}")
            return []
    
    def list_tables(self, catalog_name: str, schema_name: str) -> List[Dict[str, Any]]:
        """List tables in a schema"""
        try:
            tables = list(
                self.workspace_client.tables.list(
                    catalog_name=catalog_name, 
                    schema_name=schema_name
                )
            )
            return [table.as_dict() for table in tables]
        except Exception as e:
            logger.error(f"Error listing tables in {catalog_name}.{schema_name}: {e}")
            return []
    
    def list_volumes(self, catalog_name: str, schema_name: str) -> List[Dict[str, Any]]:
        """List volumes in a schema"""
        try:
            volumes = list(
                self.workspace_client.volumes.list(
                    catalog_name=catalog_name,
                    schema_name=schema_name
                )
            )
            return [volume.as_dict() for volume in volumes]
        except Exception as e:
            logger.error(f"Error listing volumes in {catalog_name}.{schema_name}: {e}")
            return []
    
    def get_permissions(self, object_type: str, object_id: str) -> Dict[str, Any]:
        """Get permissions for an object"""
        try:
            # URL encode the object_id to handle special characters and spaces
            from urllib.parse import quote
            
            # Remove leading slash if present (workspace paths shouldn't have it)
            if object_id.startswith('/'):
                object_id = object_id[1:]
            
            perms = self.workspace_client.permissions.get(
                request_object_type=object_type,
                request_object_id=object_id
            )
            return perms.as_dict() if perms else {}
        except Exception as e:
            error_msg = str(e)
            # Skip logging for known unsupported types
            if 'not a supported object type' in error_msg:
                logger.debug(f"Skipping {object_type} - permissions not supported")
            # Skip logging for invalid notebook paths
            elif 'No API found' in error_msg and object_type == 'notebooks':
                logger.debug(f"Skipping notebook permissions for {object_id}")
            else:
                logger.warning(f"Could not get permissions for {object_type}/{object_id}: {e}")
            return {}
    
    def get_grants(self, securable_type: str, full_name: str) -> List[Dict[str, Any]]:
        """Get Unity Catalog grants"""
        try:
            # Get grants using the SDK
            grants_response = self.workspace_client.grants.get(
                securable_type=securable_type,
                full_name=full_name
            )
            
            # Handle the response - it returns a PermissionsList object
            if hasattr(grants_response, 'privilege_assignments'):
                # Extract privilege assignments
                result = []
                for assignment in grants_response.privilege_assignments or []:
                    # Handle privileges - they can be enum objects or strings
                    privileges = []
                    for p in (assignment.privileges or []):
                        if p is None:
                            continue
                        # Try different ways to extract the privilege value
                        if isinstance(p, str):
                            priv_value = p
                        elif hasattr(p, 'value'):
                            priv_value = p.value
                        elif hasattr(p, 'name'):
                            priv_value = p.name
                        else:
                            priv_value = str(p)
                        
                        privileges.append({'privilege': priv_value})
                    
                    result.append({
                        'principal': assignment.principal,
                        'privileges': privileges
                    })
                return result
            else:
                # Fallback if structure is different
                return []
                
        except Exception as e:
            # Silently skip grants for system catalogs and internal schemas
            if '__databricks_internal' in full_name or 'information_schema' in full_name or 'system.' in full_name:
                logger.debug(f"Skipping grants for system object {full_name}")
            else:
                logger.debug(f"Could not get grants for {securable_type}/{full_name}: {e}")
            return []

    # =========================================================================
    # COMPUTE APIs
    # =========================================================================

    def list_cluster_policies(self) -> List[Dict[str, Any]]:
        """List all cluster policies"""
        return self._list_with_error_handling(
            self.workspace_client.cluster_policies.list, "cluster policies"
        )

    def list_global_init_scripts(self) -> List[Dict[str, Any]]:
        """List all global init scripts"""
        return self._list_with_error_handling(
            self.workspace_client.global_init_scripts.list, "global init scripts"
        )

    # =========================================================================
    # AI/ML APIs
    # =========================================================================

    def list_serving_endpoints(self) -> List[Dict[str, Any]]:
        """List all model serving endpoints"""
        return self._list_with_error_handling(
            self.workspace_client.serving_endpoints.list, "serving endpoints"
        )

    def list_vector_search_endpoints(self) -> List[Dict[str, Any]]:
        """List all vector search endpoints"""
        return self._list_with_error_handling(
            self.workspace_client.vector_search_endpoints.list_endpoints,
            "vector search endpoints"
        )

    def list_vector_search_indexes(self, endpoint_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all vector search indexes"""
        try:
            indexes = list(self.workspace_client.vector_search_indexes.list_indexes(
                endpoint_name=endpoint_name
            ))
            return [idx.as_dict() for idx in indexes]
        except Exception as e:
            logger.error(f"Error listing vector search indexes: {e}")
            return []

    def list_registered_models(self) -> List[Dict[str, Any]]:
        """List all registered models (Unity Catalog)"""
        return self._list_with_error_handling(
            self.workspace_client.registered_models.list, "registered models"
        )

    def list_model_versions(self, model_name: str) -> List[Dict[str, Any]]:
        """List all versions of a registered model"""
        try:
            versions = list(self.workspace_client.model_versions.list(full_name=model_name))
            return [v.as_dict() for v in versions]
        except Exception as e:
            logger.error(f"Error listing model versions for {model_name}: {e}")
            return []

    def list_experiments(self) -> List[Dict[str, Any]]:
        """List all MLflow experiments"""
        try:
            experiments = list(self.workspace_client.experiments.list_experiments())
            return [exp.as_dict() for exp in experiments]
        except Exception as e:
            logger.error(f"Error listing experiments: {e}")
            return []

    # =========================================================================
    # ANALYTICS/BI APIs
    # =========================================================================

    def list_dashboards(self) -> List[Dict[str, Any]]:
        """List all Lakeview dashboards"""
        return self._list_with_error_handling(
            self.workspace_client.lakeview.list, "dashboards"
        )

    def list_queries(self) -> List[Dict[str, Any]]:
        """List all SQL queries"""
        return self._list_with_error_handling(
            self.workspace_client.queries.list, "queries"
        )

    def list_alerts(self) -> List[Dict[str, Any]]:
        """List all alerts"""
        return self._list_with_error_handling(
            self.workspace_client.alerts.list, "alerts"
        )

    # =========================================================================
    # ORCHESTRATION APIs
    # =========================================================================

    def list_pipelines(self) -> List[Dict[str, Any]]:
        """List all Delta Live Tables pipelines"""
        return self._list_with_error_handling(
            self.workspace_client.pipelines.list_pipelines, "pipelines"
        )

    # =========================================================================
    # UNITY CATALOG ADDITIONAL APIs
    # =========================================================================

    def list_metastores(self) -> List[Dict[str, Any]]:
        """List metastores visible to the workspace"""
        return self._list_with_error_handling(
            self.workspace_client.metastores.list, "metastores"
        )

    def list_external_locations(self) -> List[Dict[str, Any]]:
        """List all external locations"""
        return self._list_with_error_handling(
            self.workspace_client.external_locations.list, "external locations"
        )

    def list_storage_credentials(self) -> List[Dict[str, Any]]:
        """List all storage credentials"""
        return self._list_with_error_handling(
            self.workspace_client.storage_credentials.list, "storage credentials"
        )

    def list_connections(self) -> List[Dict[str, Any]]:
        """List all connections (foreign catalogs)"""
        return self._list_with_error_handling(
            self.workspace_client.connections.list, "connections"
        )

    def list_functions(self, catalog_name: str, schema_name: str) -> List[Dict[str, Any]]:
        """List all functions in a schema"""
        try:
            functions = list(self.workspace_client.functions.list(
                catalog_name=catalog_name,
                schema_name=schema_name
            ))
            return [f.as_dict() for f in functions]
        except Exception as e:
            logger.error(f"Error listing functions in {catalog_name}.{schema_name}: {e}")
            return []

    # =========================================================================
    # SECURITY APIs
    # =========================================================================

    def list_secrets(self, scope_name: str) -> List[Dict[str, Any]]:
        """List all secrets in a scope (metadata only, not values)"""
        try:
            secrets = list(self.workspace_client.secrets.list_secrets(scope=scope_name))
            return [s.as_dict() for s in secrets]
        except Exception as e:
            logger.error(f"Error listing secrets in scope {scope_name}: {e}")
            return []

    def list_secret_acls(self, scope_name: str) -> List[Dict[str, Any]]:
        """List ACLs for a secret scope"""
        try:
            acls = list(self.workspace_client.secrets.list_acls(scope=scope_name))
            return [acl.as_dict() for acl in acls]
        except Exception as e:
            logger.debug(f"Could not list ACLs for scope {scope_name}: {e}")
            return []

    def list_tokens(self) -> List[Dict[str, Any]]:
        """List all tokens (for current user or admin view)"""
        return self._list_with_error_handling(
            self.workspace_client.tokens.list, "tokens"
        )

    def list_ip_access_lists(self) -> List[Dict[str, Any]]:
        """List all IP access lists"""
        return self._list_with_error_handling(
            self.workspace_client.ip_access_lists.list, "IP access lists"
        )

    # =========================================================================
    # APPS APIs
    # =========================================================================

    def list_apps(self) -> List[Dict[str, Any]]:
        """List all Databricks Apps"""
        return self._list_with_error_handling(
            self.workspace_client.apps.list, "apps"
        )

    # =========================================================================
    # WORKSPACE OBJECT APIs
    # =========================================================================

    def list_directories(self, path: str = "/") -> List[Dict[str, Any]]:
        """List directories in the workspace"""
        directories = []
        try:
            objects = list(self.workspace_client.workspace.list(path))
            for obj in objects:
                obj_dict = obj.as_dict()
                if obj_dict.get("object_type") == "DIRECTORY":
                    directories.append(obj_dict)
                    # Recursively list subdirectories
                    directories.extend(self.list_directories(obj_dict.get("path", "")))
        except Exception as e:
            logger.debug(f"Error listing directories in {path}: {e}")
        return directories

