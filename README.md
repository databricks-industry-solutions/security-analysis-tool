# SAT: Monitor the Security Health of Databricks Workspaces

Core security posture checks are now available natively within the Databricks platform in the [**Governance Hub's Security tab**](https://docs.databricks.com/aws/en/admin/governance-hub/security), providing an integrated, zero-installation method of assessing your Databricks security posture against recommended best practices. The Governance Hub Security Posture Management is currently in Private Preview. Please reach out to your Databricks account team to gain access.

The **Security Analysis Tool (SAT)** continues to provide additional security analysis capabilities that are not currently yet available in the Governance Hub, such as secrets scanning, permissions and resource analysis, and other specialized security utilities. If Governance Hub is not yet available in your environment (e.g. AWS GovCloud), refer to the v0.9.1 of **SAT**.

**Latest version:** [v1.0.0](https://github.com/databricks-industry-solutions/security-analysis-tool/releases) — SAT is now a single Databricks App: in-app setup and job provisioning, permissions & resource analysis, secret scanning (with in-app scan settings and custom detection rules), the security assistant, and admin-only alerts, with per-user authorization. Because the configuration-vs-best-practice security posture checks are now native in the Governance Hub Security tab, they — along with the classic dashboards and the Initializer/Driver notebooks — are retired from SAT. See the [Upgrade Guide](https://databricks-industry-solutions.github.io/security-analysis-tool/docs/upgrade) for what changes when moving from a pre-1.0 install.

## Documentation

Refer to the [SAT documentation](https://databricks-industry-solutions.github.io/security-analysis-tool/) for detailed information on how to use SAT, its features, and configuration options.

## Project Support

The code in this project is provided **for exploration purposes only** and is **not formally supported** by Databricks under any Service Level Agreements (SLAs). It is provided **AS-IS**, without any warranties or guarantees.  

Please **do not submit support tickets** to Databricks for issues related to the use of this project.  

The source code provided is subject to the Databricks [LICENSE](https://github.com/databricks-industry-solutions/security-analysis-tool/blob/main/LICENSE) . All third-party libraries included or referenced are subject to their respective licenses set forth in the project license.  

Any issues or bugs found should be submitted as **GitHub Issues** on the project repository. While these will be reviewed as time permits, there are **no formal SLAs** for support.

## Contributing

We happily welcome contributions. We accept PRs pursuant to a CLA.

Before you start, see [CONTRIBUTING.md](CONTRIBUTING.md) for the contribution process and project structure. Contributors using an AI coding agent (Claude Code or otherwise) should read [AGENTS.md](AGENTS.md) — the tool-agnostic guide to repository conventions and guardrails — with [CLAUDE.md](CLAUDE.md) as the detailed source of truth.
