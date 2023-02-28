#Make sure Files in Repos option is enabled in Workspace Admin Console > Workspace Settings

resource "databricks_repo" "security-analysis-tool" {
  url = "https://github.com/databricks-industry-solutions/security-analysis-tool.git"
}
