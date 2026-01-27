"""
Command-line interface for BrickHound
"""

import click
import logging
from brickhound.collector import DatabricksCollector
from brickhound.utils.config import DatabricksConfig, CollectorConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.group()
@click.version_option(version="0.1.0")
def main():
    """BrickHound - Databricks Security Analysis Tool"""
    pass


@main.command()
@click.option(
    "--workspace-url",
    envvar="DATABRICKS_HOST",
    required=True,
    help="Databricks workspace URL",
)
@click.option(
    "--token",
    envvar="DATABRICKS_TOKEN",
    help="Databricks personal access token",
)
@click.option(
    "--account-id",
    envvar="DATABRICKS_ACCOUNT_ID",
    help="Databricks account ID for account-level collection",
)
@click.option(
    "--collect-unity-catalog/--no-unity-catalog",
    default=True,
    help="Collect Unity Catalog objects",
)
@click.option(
    "--collect-permissions/--no-permissions",
    default=True,
    help="Collect permission information",
)
@click.option(
    "--output",
    type=click.Path(),
    help="Output path for graph data (JSON)",
)
def collect(
    workspace_url: str,
    token: str,
    account_id: str,
    collect_unity_catalog: bool,
    collect_permissions: bool,
    output: str,
):
    """Collect Databricks objects and permissions"""
    
    click.echo("Starting BrickHound data collection...")
    
    # Configure
    db_config = DatabricksConfig(
        workspace_url=workspace_url,
        token=token,
        account_id=account_id,
    )
    
    collector_config = CollectorConfig(
        collect_unity_catalog=collect_unity_catalog,
        collect_permissions=collect_permissions,
    )
    
    # Collect
    collector = DatabricksCollector(
        databricks_config=db_config,
        collector_config=collector_config,
    )
    
    collector.collect_all()
    
    # Get results
    graph_data = collector.get_graph_data()
    stats = graph_data["stats"]
    
    click.echo(f"\n✓ Collection complete!")
    click.echo(f"  Total vertices: {stats['total_vertices']}")
    click.echo(f"  Total edges: {stats['total_edges']}")
    
    # Save if output specified
    if output:
        import json
        with open(output, "w") as f:
            json.dump(graph_data, f, indent=2, default=str)
        click.echo(f"\n✓ Saved graph data to {output}")
    else:
        click.echo("\nTo save the graph, use: brickhound collect --output graph.json")
        click.echo("Or use the Databricks notebooks to save to Delta Lake")


@main.command()
@click.argument("graph_file", type=click.Path(exists=True))
def stats(graph_file: str):
    """Show statistics about collected graph data"""
    
    import json
    
    with open(graph_file, "r") as f:
        graph_data = json.load(f)
    
    stats = graph_data.get("stats", {})
    
    click.echo("BrickHound Graph Statistics")
    click.echo("=" * 50)
    click.echo(f"\nTotal Vertices: {stats.get('total_vertices', 0)}")
    click.echo(f"Total Edges: {stats.get('total_edges', 0)}")
    
    click.echo("\n Vertex Counts by Type:")
    for node_type, count in stats.get("vertex_counts", {}).items():
        click.echo(f"  {node_type:20s}: {count:5d}")
    
    click.echo("\nEdge Counts by Relationship:")
    for rel_type, count in stats.get("edge_counts", {}).items():
        click.echo(f"  {rel_type:20s}: {count:5d}")


@main.command()
def version():
    """Show BrickHound version"""
    click.echo("BrickHound v0.1.0")
    click.echo("Six Degrees of Databricks Admin")


if __name__ == "__main__":
    main()

