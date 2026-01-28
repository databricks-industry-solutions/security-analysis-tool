"""
Configuration management for BrickHound
"""

import os
from typing import List, Optional
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

__all__ = ["DatabricksConfig", "GraphConfig", "CollectorConfig"]


@dataclass
class DatabricksConfig:
    """Databricks connection configuration"""
    
    workspace_url: str
    token: Optional[str] = None
    account_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    
    @classmethod
    def from_env(cls) -> "DatabricksConfig":
        """Load configuration from environment variables"""
        return cls(
            workspace_url=os.getenv("DATABRICKS_HOST", ""),
            token=os.getenv("DATABRICKS_TOKEN"),
            account_id=os.getenv("DATABRICKS_ACCOUNT_ID"),
            client_id=os.getenv("DATABRICKS_CLIENT_ID"),
            client_secret=os.getenv("DATABRICKS_CLIENT_SECRET"),
        )
    
    def validate(self) -> bool:
        """Validate configuration"""
        if not self.workspace_url:
            raise ValueError("workspace_url is required")
        
        # Must have either token or OAuth credentials
        has_token = bool(self.token)
        has_oauth = bool(self.client_id and self.client_secret)
        
        if not (has_token or has_oauth):
            raise ValueError(
                "Either token or OAuth credentials (client_id + client_secret) required"
            )
        
        return True


@dataclass
class GraphConfig:
    """Graph storage configuration"""
    
    catalog: str = "main"  # Default to 'main' catalog (exists in all workspaces)
    schema: str = "brickhound"
    vertices_table: str = "vertices"
    edges_table: str = "edges"
    
    @property
    def vertices_path(self) -> str:
        """Full path to vertices table"""
        return f"{self.catalog}.{self.schema}.{self.vertices_table}"
    
    @property
    def edges_path(self) -> str:
        """Full path to edges table"""
        return f"{self.catalog}.{self.schema}.{self.edges_table}"
    
    @classmethod
    def from_env(cls) -> "GraphConfig":
        """Load graph configuration from environment variables"""
        return cls(
            catalog=os.getenv("BRICKHOUND_CATALOG", "main"),
            schema=os.getenv("BRICKHOUND_SCHEMA", "brickhound"),
        )


@dataclass
class CollectorConfig:
    """Data collection configuration"""

    # Collection scope
    collect_account_level: bool = True
    collect_workspace_level: bool = True
    collect_unity_catalog: bool = True
    collect_permissions: bool = True

    # Object type toggles - Identity
    collect_users: bool = True
    collect_groups: bool = True
    collect_service_principals: bool = True

    # Object type toggles - Compute
    collect_clusters: bool = True
    collect_instance_pools: bool = True
    collect_cluster_policies: bool = True
    collect_global_init_scripts: bool = True

    # Object type toggles - Data & Analytics
    collect_warehouses: bool = True
    collect_metastores: bool = True
    collect_external_locations: bool = True
    collect_storage_credentials: bool = True
    collect_connections: bool = True

    # Object type toggles - AI/ML
    collect_serving_endpoints: bool = True
    collect_vector_search_endpoints: bool = True
    collect_vector_search_indexes: bool = True
    collect_registered_models: bool = True
    collect_experiments: bool = True

    # Object type toggles - Analytics/BI
    collect_dashboards: bool = True
    collect_queries: bool = True
    collect_alerts: bool = True

    # Object type toggles - Development
    collect_notebooks: bool = True
    collect_repos: bool = True

    # Object type toggles - Orchestration
    collect_jobs: bool = True
    collect_pipelines: bool = True

    # Object type toggles - Security
    collect_secret_scopes: bool = True
    collect_tokens: bool = True
    collect_ip_access_lists: bool = True

    # Object type toggles - Apps
    collect_apps: bool = True

    # Performance settings
    batch_size: int = 100
    max_retries: int = 3
    timeout_seconds: int = 30

    # Multi-workspace settings
    workspace_ids: Optional[List[str]] = None  # If None, collect from all workspaces

