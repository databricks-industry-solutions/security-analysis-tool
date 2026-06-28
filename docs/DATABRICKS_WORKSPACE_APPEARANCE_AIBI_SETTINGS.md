# Databricks Workspace Appearance, AI/BI, Security, Compute, Development, And Advanced Settings

Reviewed: 2026-06-28

This document explains Databricks workspace settings shown in the admin UI, with a focus on:

- Workspace label
- AI/BI workspace theme
- Genie One homepage
- Security settings for data access, external access, and egress/ingress controls
- Compute settings for SQL warehouses, serverless environments, usage policies, and interactive timeout
- Development settings for Git folders and Databricks Apps
- Advanced settings for access control, storage, Unity Catalog defaults, AI/ML behavior, and audit logs

Use this as an internal enablement guide for workspace administrators, BI owners, governance teams, and support teams.

## Summary

Databricks workspace settings help make a workspace easier to identify, easier to govern, more consistent for dashboard and Genie users, and safer for data movement.

| Setting | What it controls | Why enable or configure it |
| --- | --- | --- |
| Workspace label | A colored pill next to the workspace name in the top navigation bar | Reduces confusion between dev, test, staging, and production workspaces. |
| AI/BI workspace theme | Default styling for new AI/BI dashboards | Standardizes dashboard colors, fonts, layout, and visual presentation across the workspace. |
| Genie One homepage | Workspace-level Genie One landing experience | Promotes trusted dashboards, Genie Spaces, announcements, and team-specific starting points. |
| Security - data security | Default access mode for job compute | Moves legacy or undefined jobs compute toward Unity Catalog-compatible access modes. |
| Security - external access | Embedding and collaboration platform controls | Limits where dashboards, Genie Spaces, Slack, and Teams integrations can expose answers. |
| Security - egress and ingress | UI download, export, upload, and clipboard controls | Reduces common data exfiltration paths through the Databricks UI. |
| Compute - SQL | Default warehouse and SQL warehouse/serverless compute settings | Aligns SQL workloads with approved compute and warehouse-level configuration. |
| Compute - environments | Default package repositories and workspace base environments | Standardizes Python dependencies and serverless notebook/job environments. |
| Compute - policies | Serverless usage policies | Enforces cost attribution tags for serverless notebooks, jobs, and pipelines. |
| Compute - serverless interactive | Serverless interactive execution timeout | Limits long-running interactive serverless notebook queries. |
| Development - Repos | Git URL allowlist and IPYNB output commit controls | Restricts remote repositories and controls whether notebook outputs can be committed. |
| Development - Apps | Git-only app deployment and app OAuth scope controls | Improves app supply-chain governance and limits what apps can do on behalf of users. |
| Advanced - access control | Databricks personnel access, personal access tokens, and entitlement behavior | Controls support access, legacy API authentication, and workspace entitlement assignment behavior. |
| Advanced - storage | Purge actions and deletion vector defaults | Handles irreversible storage cleanup and default table feature behavior. |
| Advanced - other | Default catalog, partner-powered AI, MLflow settings, and verbose audit logs | Controls workspace defaults for data resolution, AI assistive features, ML tracking/serving, and audit detail. |

## Where To Find Appearance And AI/BI Settings

Workspace admins can open these settings from the Databricks workspace:

1. Click the username in the top bar.
2. Select **Settings**.
3. Open the **Appearance** tab.

The Appearance page can include settings for workspace label, AI/BI themes, Plotly visualization toolbar behavior, language/search behavior, and default date/time formatting.

Source: [Databricks - Manage workspace appearance settings](https://docs.databricks.com/aws/en/admin/workspace-settings/appearance)

## Where To Find Security Settings

Workspace admins can open the security settings from the Databricks workspace:

1. Click the username in the top bar.
2. Select **Settings**.
3. Open the **Security** tab.

The Security page can include settings for job compute access mode, dashboard and Genie Space embedding, collaboration platforms, notebook exports, SQL result downloads, MLflow artifact downloads, upload behavior, clipboard behavior, and Unity Catalog volume file downloads.

## Where To Find Compute Settings

Workspace admins can open compute settings from the Databricks workspace:

1. Click the username in the top bar.
2. Select **Settings**.
3. Open the **Compute** tab.

The Compute page can include settings for default warehouse, SQL warehouses and serverless compute, default package repositories, workspace base environments for serverless compute, serverless usage policies, and serverless interactive execution timeout.

## Where To Find Development Settings

Workspace admins can open development settings from the Databricks workspace:

1. Click the username in the top bar.
2. Select **Settings**.
3. Open the **Development** tab.

The Development page can include settings for Git URL allowlists, repository export behavior, Git-only Databricks App deployments, and allowed OAuth scopes for Databricks Apps.

## Where To Find Advanced Settings

Workspace admins can open advanced settings from the Databricks workspace:

1. Click the username in the top bar.
2. Select **Settings**.
3. Open the **Advanced** tab.

The Advanced page can include settings for access control, personal access tokens, workspace entitlement behavior, storage purge actions, deletion vectors, default catalog, partner-powered AI features, Databricks Autologging, legacy MLflow Model Serving, and verbose audit logs.

## Workspace Label

### What It Does

The workspace label is a short colored label displayed beside the workspace name in the top navigation bar. For example, a development workspace can show a `dev` label, as in the screenshot.

Databricks supports setting this from:

- Workspace admin settings inside the workspace.
- The account console by an account admin.

If both places are used, the most recent update is what displays because a workspace can only have one label at a time. Databricks limits labels to 30 characters.

### Advantages

| Advantage | Why it matters |
| --- | --- |
| Prevents environment confusion | Users can immediately see whether they are in dev, test, staging, or production. |
| Reduces operational mistakes | Admins are less likely to change production objects while thinking they are in a lower environment. |
| Improves support triage | Screenshots and support calls become clearer because the environment is visible. |
| Supports naming standards | Account admins can use consistent labels and colors across multiple workspaces. |

### Recommended Labels

| Environment | Label | Suggested color intent |
| --- | --- | --- |
| Development | `dev` | Low-risk color such as blue or teal |
| Test / QA | `test` or `qa` | Distinct from dev and prod |
| Staging | `stage` | Warning-adjacent but not production-critical |
| Production | `prod` | High-attention color such as red |
| Sandbox | `sandbox` | Neutral color |

Keep labels short. The goal is fast recognition, not a full description.

### How To Configure

As a workspace admin:

1. Open the target workspace.
2. Go to **Settings > Appearance**.
3. Under **Workspace**, edit **Workspace label**.
4. Enter the label name.
5. Select a color.
6. Save.

As an account admin:

1. Open the Databricks account console.
2. Go to **Workspaces**.
3. Open the target workspace.
4. Select **Update workspace**.
5. Under **Configuration**, set the workspace label and color.
6. Save.

## AI/BI Workspace Theme

### What It Does

The AI/BI workspace theme defines the default visual style for AI/BI dashboards in the workspace. In the screenshot, this setting is shown as **AI/BI > Workspace theme**, with the status **Not configured** and an **Add** button.

When a workspace theme is configured:

- New AI/BI dashboards automatically inherit the workspace theme.
- Existing dashboards can opt in by selecting the workspace theme in dashboard settings.
- Dashboard authors can still choose other preset themes or customize a copied theme for a specific dashboard.

Source: [Databricks - Manage AI/BI dashboard workspace themes](https://docs.databricks.com/aws/en/ai-bi/admin/themes)

### What Can Be Standardized

A workspace theme can standardize dashboard presentation elements such as:

- Font family, size, color, weight, and text case
- Canvas background color
- Widget background, borders, selection color, padding, margin, shadow, corner radius, and title alignment
- Visualization axis and grid line colors
- Textbox vertical alignment
- Continuous and categorical color palettes

### Advantages

| Advantage | Why it matters |
| --- | --- |
| Consistent executive reporting | Dashboards across teams look like they belong to the same organization. |
| Faster dashboard creation | Authors start from an approved default instead of rebuilding styles dashboard by dashboard. |
| Better governance | BI owners can define approved fonts, colors, and visual conventions centrally. |
| Easier review and support | Standard presentation makes dashboards easier to scan, compare, and troubleshoot. |
| Improved user trust | Consistent styling helps users recognize official dashboards and reduces ad hoc visual drift. |
| Better embedded experiences | Dashboards embedded or shared externally can maintain a controlled visual identity. |

### Important Behavior For Existing Dashboards

Existing dashboards do not automatically change when an admin creates a workspace theme. Dashboard authors must apply the workspace theme from dashboard settings.

When an existing dashboard applies the workspace theme, the dashboard receives a snapshot of the theme configuration. If the workspace admin later changes or deletes the theme, that dashboard keeps its snapshot until the author reapplies or changes the theme.

Source: [Databricks - Dashboard settings: Apply a workspace theme](https://docs.databricks.com/aws/en/dashboards/manage/settings)

### How To Configure

1. Click the username in the Databricks workspace top bar.
2. Select **Settings**.
3. Go to **Appearance > AI/BI > Theme**.
4. Click **Add** if no theme exists, or **Edit** if a theme already exists.
5. Use preview mode to test light and dark appearance.
6. Configure interface and visualization settings.
7. Save the theme.

### Recommended Theme Governance

Before enabling a workspace theme broadly, agree on:

- Primary and secondary brand colors.
- Approved dashboard background color.
- Categorical palette for business dimensions.
- Continuous gradient for metrics.
- Font and heading hierarchy.
- Minimum contrast expectations.
- Widget spacing, borders, and title alignment.
- Ownership group that can approve changes.

Avoid changing the workspace theme frequently. Treat it like a shared BI design standard.

## Genie One Homepage

### What It Does

The Genie One homepage setting customizes the Genie One landing page for users. In the screenshot, this is shown under **Genie One** with an **Edit** button.

Workspace admins can customize:

- Brand color
- Logo
- Markdown welcome text
- Pinned content such as Genie Spaces, dashboards, or other assets

Source: [Databricks - Customize the Genie One homepage](https://docs.databricks.com/aws/en/genie-one/customize-genie-homepage)

### Advantages

| Advantage | Why it matters |
| --- | --- |
| Guides users to trusted assets | Users see recommended dashboards and Genie Spaces instead of hunting through the workspace. |
| Improves AI/BI adoption | A curated entry point makes Genie One feel intentional and useful for business users. |
| Reduces duplicate questions | Teams can pin canonical dashboards, curated Genie Spaces, and common starting points. |
| Supports announcements | Markdown text can provide workspace-specific guidance, links, or rollout notes. |
| Keeps governance visible | Admins can steer users toward certified or approved content. |

### What To Pin

Good candidates for pinned content include:

- Executive KPI dashboards.
- Security or governance dashboards.
- Frequently used departmental dashboards.
- Curated Genie Spaces with strong table descriptions and example questions.
- Getting-started or support links.

Do not pin content that broad audiences cannot access. Pinned content should align with permissions and data governance expectations.

### How To Configure

1. Click the username in the Databricks workspace top bar.
2. Select **Settings**.
3. Go to **Appearance**.
4. Next to **Genie One home page**, click **Edit**.
5. Configure color, logo, and Markdown text.
6. Enable pinned content if needed.
7. Select the dashboards, Genie Spaces, or other assets to pin.
8. Save.

## Related AI/BI And Genie Considerations

### Dashboard Genie Spaces

Published AI/BI dashboards can include a companion Genie Space so viewers can ask natural-language questions about dashboard data. Databricks notes that the **Enable Genie** toggle is on by default when publishing dashboards.

This is useful because it lets business users explore beyond predefined dashboard visuals. However, admins and dashboard owners must be careful about dataset design: Genie can answer from the full dataset query results, including fields not shown in the visualization. Only include rows and columns that viewers should be able to query.

Source: [Databricks - Genie Spaces with dashboards](https://docs.databricks.com/aws/en/dashboards/genie-spaces)

### Access And Entitlements

AI/BI and Genie access is controlled through workspace entitlements, dashboard permissions, Genie Space permissions, Unity Catalog permissions, and compute access. Appearance settings improve the user experience, but they do not replace access control.

Source: [Databricks - AI/BI administration guide](https://docs.databricks.com/aws/en/ai-bi/admin/)

## Security Settings

The Security tab controls workspace-level defaults that affect compute isolation, external sharing, collaboration integrations, and data movement through the Databricks UI.

Security settings should be treated as workspace governance controls. They do not replace Unity Catalog permissions, workspace object permissions, network controls, private connectivity, identity governance, or audit monitoring.

## Security - Data Security

### Default Access Mode For Job Compute

This setting defines the access mode used for job compute when a job does not explicitly specify an access mode. It is especially important for legacy jobs created before access mode became a normal part of job compute configuration.

The available choices shown in the UI are:

| Option | Meaning | Unity Catalog access |
| --- | --- | --- |
| `Not set` | Shows as `CUSTOM` access mode in the cluster UI. Allows Python, SQL, Scala, and R workloads. | No Unity Catalog access. |
| `Dedicated (formerly: Single user)` | Runs SQL, Python, R, and Scala workloads as a single assigned user. | Supports data secured in Unity Catalog. |
| `Standard (formerly: Shared)` | Multiple users can share the cluster for SQL, Python, and Scala workloads. | Supports data secured in Unity Catalog. |

Source: [Databricks - Compute access modes](https://docs.databricks.com/aws/en/compute/configure.html#access-modes)

### Recommendation

| Setting value | When to use | When not to use |
| --- | --- | --- |
| `Dedicated` | Use for production jobs, sensitive workloads, jobs that need stronger user isolation, jobs with R workloads, and jobs where a single run identity is expected. | Avoid as a blanket default when many users need shared interactive-style collaboration on the same compute, or when Standard mode features are required. |
| `Standard` | Use for shared job patterns where multiple users or workloads can safely use shared compute and the workload is compatible with Standard access mode. | Avoid for highly sensitive workloads that need single-user isolation or for workloads that require access mode features not supported by Standard compute. |
| `Not set` | Use only temporarily during migration if legacy jobs would break immediately and need review. | Do not leave this as the long-term default for governed workspaces because it can keep jobs outside Unity Catalog-compatible access modes. |

### Practical Guidance

For production and governed analytics workspaces, prefer setting a real default instead of leaving it `Not set`. Use `Dedicated` when the workspace has sensitive data, regulated workloads, or many scheduled jobs that should run under a clear job owner or service principal. Use `Standard` when the organization has validated workload compatibility and wants shared compute behavior for job workloads.

Before changing this setting, review legacy jobs that do not define access mode. Databricks notes that changing the default can affect job compute resources that do not have a defined access mode, and some workloads may not execute in the newly selected default mode.

## Security - External Access

### Embed Dashboards And Genie Spaces

This setting controls whether published AI/BI dashboards and Genie Spaces can be embedded in external domains, and which domains are approved.

The UI option shown in the screenshot is **Allow approved domains**, with a **Manage** button for domain allowlisting.

Source: [Databricks - Embed a dashboard](https://docs.databricks.com/aws/en/dashboards/embed)

| Configuration | When to enable | When not to enable |
| --- | --- | --- |
| Deny embedding | Use for internal-only workspaces, regulated data, early pilots, and dashboards not designed for external consumption. | Avoid if approved business applications need to embed trusted Databricks dashboards or Genie Spaces. |
| Allow approved domains | Use when embedding is required in known internal portals, customer portals, or approved applications. | Do not allow until the exact domains, authentication model, dashboard permissions, and data audience are approved. |
| Broad or unmanaged embedding | Generally not recommended. | Do not use for production or sensitive data because it increases the chance of data being surfaced in unapproved places. |

### Practical Guidance

Enable embedding only after confirming:

- The embedding domain is owned or approved by the organization.
- The embedded dashboard or Genie Space has the right workspace permissions.
- The underlying Unity Catalog data permissions match the intended audience.
- The dashboard dataset does not include hidden columns or rows that viewers should not query through Genie.
- The use case has an owner who will review access and content periodically.

### Allowed Collaboration Platforms

This setting controls which external collaboration platforms, such as Slack or Microsoft Teams, workspace members can connect to.

| Configuration | When to enable | When not to enable |
| --- | --- | --- |
| `Deny all` | Recommended default for workspaces that do not have an approved Slack or Teams integration, regulated workloads, or sensitive data. | Avoid only when users have an approved collaboration workflow that depends on Databricks integration. |
| Allow selected platforms | Use after security and platform teams approve Slack, Teams, or another supported platform for the workspace. | Do not enable for ungoverned channels, personal workspaces, or channels where membership is not controlled. |
| Allow all supported platforms | Use only in low-risk sandbox or proof-of-concept workspaces. | Do not use in production or governed environments. |

### Allow Public Messages In Collaboration Platforms

This toggle controls whether bot responses in Slack or Microsoft Teams can be visible to the whole channel. When disabled, responses are forced to be private to the requesting user.

| Setting | When to enable | When not to enable |
| --- | --- | --- |
| Off | Recommended default. Use when responses might include business metrics, customer data, security information, or other sensitive context. | Avoid only if team workflows explicitly require channel-visible answers and the channel membership is tightly governed. |
| On | Use for low-risk, shared-team channels where answers are expected to be public and the data is appropriate for everyone in the channel. | Do not enable in broad channels, external/shared channels, incident channels, or channels with mixed data-access levels. |

## Security - Egress And Ingress

These settings control common ways users move data into or out of Databricks through the UI. Turning a setting off can reduce accidental or intentional data exfiltration, but it can also interrupt normal analyst and data science workflows.

### Egress And Ingress Settings Summary

| Setting | What it controls | Recommended baseline |
| --- | --- | --- |
| Notebook results download | Downloading notebook output/results from the UI | Disable in sensitive production workspaces; enable in dev if needed. |
| Notebook and file exporting | Exporting notebooks and files from the workspace UI | Disable where source code or data leakage is a concern; enable for migration or backup workflows with controls. |
| SQL results download | Downloading query results | Disable for regulated data workspaces unless approved; enable for analytics teams that need governed extracts. |
| MLflow run artifact download | Downloading artifact files from the MLflow run or logged model UI | Disable for sensitive model artifacts; review because Databricks says this setting will be deprecated soon. |
| Upload data using the UI | Uploading local data directly to Delta tables from UI entry points | Enable for self-service ingestion workspaces; disable for controlled ingestion pipelines. |
| Results table clipboard features | Copying tabular result data to the clipboard through the UI | Disable for sensitive data; enable where copy/paste productivity is acceptable. |
| Download files from Unity Catalog Volumes using the UI | UI download feature for files stored in Unity Catalog volumes | Disable for sensitive volumes if UI download is not needed; remember APIs, SDKs, and CLI may still download files. |

Source: [Databricks - Manage workspace settings](https://docs.databricks.com/aws/en/admin/workspace-settings/)

### Notebook Results Download

| Enable when | Do not enable when |
| --- | --- |
| Users need to save notebook outputs for debugging, development, or approved offline analysis. | Notebook outputs may contain customer data, credentials, model output, regulated data, or operational secrets. |

For production workspaces, prefer disabling this unless there is a documented business need. If enabled, rely on Unity Catalog, object permissions, audit logs, and data handling policy to govern usage.

### Notebook And File Exporting

| Enable when | Do not enable when |
| --- | --- |
| Teams need to export notebooks for code review, migration, backup, or cross-workspace promotion. | The workspace contains proprietary notebooks, embedded outputs, credentials, generated files, or sensitive project artifacts. |

If export is required, prefer using source control and deployment workflows instead of manual UI exports.

### SQL Results Download

| Enable when | Do not enable when |
| --- | --- |
| Analysts have approved use cases for CSV/result extracts and the underlying data is appropriate for download. | Queries can return regulated, customer, financial, health, security, or confidential data that should stay in governed storage. |

For governed workspaces, disable by default and allow extracts only through approved workflows, masked views, row filters, clean rooms, or controlled data products.

### MLflow Run Artifact Download

| Enable when | Do not enable when |
| --- | --- |
| Data scientists need to download model artifacts, plots, evaluation files, or experiment outputs for approved development workflows. | Artifacts may contain trained models, training data samples, feature files, prompts, evaluation data, or proprietary IP that should not leave the workspace. |

The UI warns that this setting will be deprecated soon and that artifacts can still be viewed in the UI or accessed using the MLflow client. Treat this as one control in a broader model governance plan, not a complete artifact protection boundary.

### Upload Data Using The UI

| Enable when | Do not enable when |
| --- | --- |
| The workspace supports self-service data onboarding, prototypes, training, or small approved uploads to Delta tables. | Production data ingestion must go through managed pipelines, data quality checks, lineage controls, DLP review, or approved landing zones. |

The UI text notes that this setting does not control file uploads to Unity Catalog volumes. Manage volume access separately through Unity Catalog privileges.

### Results Table Clipboard Features

| Enable when | Do not enable when |
| --- | --- |
| Users frequently copy small result sets for documentation, tickets, or approved operational work. | Result tables may contain sensitive data and clipboard movement would bypass normal export controls. |

For sensitive workspaces, disable this along with SQL result downloads to reduce casual data movement.

### Download Files From Unity Catalog Volumes Using The UI

| Enable when | Do not enable when |
| --- | --- |
| Users need browser-based download of governed files from volumes and those files are approved for local use. | Volumes hold sensitive raw data, regulated files, model artifacts, or data that should only be accessed through governed jobs or applications. |

The UI note is important: this setting only affects downloads through the UI. Users might still download files through APIs, SDKs, or the CLI if their Unity Catalog privileges and network access allow it.

## Recommended Security Baseline

| Workspace type | Recommended baseline |
| --- | --- |
| Production with sensitive data | Use `Dedicated` or validated `Standard` job compute default; deny unmanaged embedding; deny collaboration platforms unless approved; keep public collaboration messages off; disable result downloads, exports, clipboard copy, and volume UI downloads unless approved. |
| Production analytics with approved BI use cases | Use a Unity Catalog-compatible job compute default; allow embedding only for approved domains; allow Teams/Slack only if governed; selectively enable SQL downloads or volume downloads for approved groups and documented use cases. |
| Development workspace | Use `Dedicated` or `Standard` based on workload compatibility; allow limited exports/downloads if developers need them; keep public collaboration messages off unless channel membership is controlled. |
| Sandbox or training workspace | More permissive settings can be acceptable when data is synthetic or non-sensitive, but labels should clearly identify the workspace as sandbox/training. |

## Security Change Checklist

Before changing security settings, confirm:

- Which workspace is being changed: dev, test, staging, production, or sandbox.
- Whether the workspace contains sensitive, regulated, customer, security, or model IP data.
- Which users, groups, service principals, dashboards, jobs, and integrations depend on the setting.
- Whether Unity Catalog permissions, object permissions, and external platform permissions already match the intended behavior.
- Whether audit logs or monitoring are in place to detect unexpected downloads, exports, uploads, or external sharing.
- Whether the change should be tested in a lower environment first.

## Compute Settings

The Compute tab controls workspace-level defaults and governance settings for SQL warehouses, serverless compute, runtime environments, package repositories, cost attribution, and interactive execution limits.

These settings are operational controls. They influence cost, reliability, reproducibility, and governance, but they do not replace Unity Catalog privileges, cluster policies, SQL warehouse permissions, budget policies, or cloud-level controls.

## Compute - SQL

### Default Warehouse

The default warehouse setting chooses the SQL warehouse selected by default for users in the workspace. It applies to SQL workloads only and can be overridden by users.

The screenshot shows the value **Last selected**, which means the UI uses the warehouse a user selected most recently.

Source: [Databricks - SQL warehouse settings](https://docs.databricks.com/aws/en/admin/sql/)

| Configuration | When to use | When not to use |
| --- | --- | --- |
| `Last selected` | Good default for flexible workspaces where users work across multiple warehouses and understand which warehouse to choose. | Avoid for production BI workspaces where users should consistently land on a governed, right-sized warehouse. |
| Specific approved warehouse | Use for BI, dashboard, and SQL analyst workspaces where most users should start on a standard warehouse with known cost, permissions, and performance. | Avoid if teams need very different warehouses by default or if one shared default would create contention. |
| No practical default / unmanaged behavior | Acceptable only in small sandbox workspaces. | Do not use in production analytics workspaces because it increases confusion and can push workloads to the wrong warehouse. |

### Recommendation

For production analytics workspaces, set a specific default warehouse for common SQL users. Choose a warehouse that is:

- Right-sized for expected dashboard and query concurrency.
- Governed through permissions.
- Tagged or named clearly for cost attribution.
- Monitored for utilization and cost.
- Separate from experimental or high-cost warehouses.

Keep `Last selected` for developer-heavy workspaces where users intentionally switch between warehouses.

### SQL Warehouses And Serverless Compute

The **SQL warehouses and serverless compute** setting opens the management area for SQL warehouses and serverless compute configuration. Use it to govern how SQL workloads and serverless compute are available in the workspace.

Source: [Databricks - Manage SQL warehouses](https://docs.databricks.com/aws/en/compute/sql-warehouse/)

| Enable or manage when | Do not enable or keep limited when |
| --- | --- |
| Users run SQL queries, AI/BI dashboards, Genie, alerts, scheduled SQL workloads, or BI tool connections. | The workspace is not intended for SQL analytics or serverless compute has not been approved by platform/security teams. |
| You need autoscaling, quick startup, dashboard reliability, or isolated SQL serving capacity. | Cloud/network/security prerequisites are not ready, or serverless costs cannot yet be monitored and attributed. |

### Practical Guidance

Manage SQL warehouses deliberately:

- Use warehouse permissions so only approved users and groups can attach.
- Use meaningful warehouse names such as `prod-bi-small`, `prod-bi-large`, or `dev-sql`.
- Separate production dashboards from exploratory SQL where practical.
- Monitor warehouse size, auto-stop, scaling, and query history.
- Use tags or serverless usage policies where available for cost attribution.

## Compute - Environments

### Default Package Repositories

Default package repositories configure where workloads install Python packages from. The screenshot states that these settings apply to serverless notebooks, serverless jobs, model serving, classic clusters, and Spark Declarative Pipelines. Timing depends on workload type:

- Serverless compute: applies to new notebook sessions and job runs.
- Model serving: applies to new image build processes.
- Classic clusters: applies to new clusters and existing clusters after restart.
- Spark Declarative Pipelines: applies to new pipeline runs.

Source: [Databricks - Configure default Python package repositories](https://docs.databricks.com/aws/en/admin/workspace-settings/default-python-packages)

| Enable or configure when | Do not configure broadly when |
| --- | --- |
| Your organization requires approved PyPI mirrors, private package repositories, dependency scanning, or reproducible package sources. | Teams need unrestricted public package access for early exploration and the workspace contains only low-risk test data. |
| You want to prevent accidental dependency drift from arbitrary public package sources. | You do not yet have a maintained internal repository or process for approving packages. |

### Recommendation

For production and regulated workspaces, configure approved package repositories. This improves supply-chain control and reproducibility. For sandbox or training workspaces, public defaults can be acceptable if the environment is isolated and does not process sensitive data.

### Workspace Base Environments For Serverless Compute

Workspace base environments define a predefined environment version and Python package set for serverless notebooks. This helps users start serverless notebook work with a consistent environment.

Source: [Databricks - Manage workspace base environments](https://docs.databricks.com/aws/en/admin/workspace-settings/base-environment)

| Enable or manage when | Do not manage aggressively when |
| --- | --- |
| Teams need consistent Python packages, reproducible notebooks, faster onboarding, and fewer per-notebook dependency differences. | Users are doing highly varied research or package experimentation that would be slowed by a strict base environment. |
| The workspace supports production analytics, shared notebooks, training, or standard ML/AI workflows. | A central team cannot maintain and test the environment versions. |

### Recommendation

Create base environments for common personas, such as:

- `analytics-standard`
- `ml-standard`
- `genai-standard`
- `training-standard`

Keep package sets small and intentional. Large base environments can slow environment resolution, increase dependency conflicts, and make troubleshooting harder.

## Compute - Policies

### Serverless Usage Policies

Serverless usage policies allow administrators to enforce cost attribution tags for serverless compute in notebooks, jobs, and Delta Live Tables / Lakeflow Declarative Pipelines. Policies can be assigned to users, groups, or service principals.

Source: [Databricks - Attribute usage with serverless usage policies](https://docs.databricks.com/aws/en/admin/usage/budget-policies)

| Enable or configure when | Do not rely on it alone when |
| --- | --- |
| You need cost allocation by team, project, environment, application, cost center, or owner. | You also need hard spend limits, workload isolation, or chargeback enforcement beyond tags. |
| Finance, platform, or governance teams require consistent tags on serverless usage. | Users or jobs are not yet mapped to clear ownership groups or service principals. |

### Recommendation

Configure serverless usage policies before broad serverless adoption. At minimum, require tags such as:

| Tag | Example values |
| --- | --- |
| `env` | `dev`, `test`, `prod`, `sandbox` |
| `team` | `finance`, `marketing`, `platform`, `data-science` |
| `cost_center` | Organization-specific code |
| `owner` | Team alias or service owner |
| `workload` | `dashboard`, `job`, `notebook`, `pipeline`, `training` |

Assign policies to groups and service principals rather than only individual users where possible. This makes the policy easier to maintain.

## Compute - Serverless Interactive

### Serverless Interactive Execution Timeout

This setting defines the default timeout in seconds for interactive serverless notebook queries. The screenshot shows `9000`, which is 150 minutes.

Source: [Databricks - Serverless compute for notebooks](https://docs.databricks.com/aws/en/compute/serverless/notebooks)

| Timeout strategy | When to use | When not to use |
| --- | --- | --- |
| Shorter timeout | Use when the workspace is cost-sensitive, mostly interactive, or users should move long workloads into jobs. | Avoid if legitimate exploratory queries often need longer runtime. |
| Longer timeout | Use for heavy exploratory analytics, data profiling, or notebooks that need longer interactive execution. | Avoid if users leave expensive queries running or if long-running work should be scheduled as jobs. |
| Very high timeout | Use only for special-purpose workspaces with monitoring and clear ownership. | Do not use as a broad default in production because it can hide inefficient interactive workloads and increase cost. |

### Recommendation

Keep the timeout long enough for normal interactive analysis, but short enough to push durable work into jobs, pipelines, or scheduled workflows. If users frequently hit the timeout, review whether the workload should be optimized, moved to a job, or run on a more appropriate compute target.

## Recommended Compute Baseline

| Workspace type | Recommended baseline |
| --- | --- |
| Production BI / AI/BI workspace | Set a specific governed default warehouse; manage SQL warehouses; configure serverless usage policies; use approved package repositories; keep base environments stable; use a moderate interactive timeout. |
| Production data science workspace | Configure package repositories and base environments; use serverless usage policies; allow longer interactive timeout only if monitored; avoid one shared warehouse for all personas. |
| Development workspace | `Last selected` warehouse can be acceptable; use lighter policies; allow more package flexibility; keep serverless usage tags for cost visibility. |
| Sandbox or training workspace | More permissive package and warehouse defaults can be acceptable if data is non-sensitive and costs are capped or monitored. |

## Compute Change Checklist

Before changing compute settings, confirm:

- Which workloads use SQL warehouses, serverless notebooks, serverless jobs, model serving, classic clusters, or pipelines.
- Whether BI dashboards and Genie Spaces depend on a specific warehouse.
- Whether package repository changes could break notebooks, jobs, model serving image builds, or pipelines.
- Whether base environment changes have been tested with representative notebooks.
- Whether serverless usage policy tags match finance and platform reporting needs.
- Whether the interactive timeout encourages the right split between ad hoc analysis and scheduled jobs.

## Development Settings

The Development tab controls source-code integration and Databricks Apps deployment behavior. These settings matter because development workflows can move code, notebook outputs, credentials, and app permissions across workspace boundaries.

Development settings should be managed with the same care as compute and security settings. They do not replace Git provider permissions, branch protection, code review, secret scanning, Unity Catalog permissions, Databricks App permissions, or CI/CD controls.

## Development - Repos

Databricks Repos are now referred to in many Databricks docs as Git folders. The workspace settings in the UI may still use the Repos label.

Source: [Databricks - Git folders](https://docs.databricks.com/aws/en/repos/)

### Git URL Allow List Permission

This setting controls how restrictive the Git URL allowlist is. In the screenshot, it is set to **Disabled (no restrictions)**, which means users are not restricted by the workspace Git URL allowlist.

The related **Git URL allow list** setting defines the remote repository URLs that users can clone from, commit to, and push to.

Source: [Databricks - Configure Git integration for Git folders](https://docs.databricks.com/aws/en/repos/repos-setup)

| Configuration | When to use | When not to use |
| --- | --- | --- |
| Disabled / no restrictions | Acceptable for sandbox, training, or early development workspaces where users need broad Git access and data/code sensitivity is low. | Avoid in production, regulated, or customer-data workspaces because users can connect arbitrary remote repositories. |
| Restrict clone, commit, and push to allowlisted URLs | Use for governed development where code must come from approved GitHub, Azure DevOps, GitLab, or Bitbucket organizations/projects. | Avoid if the allowlist is not maintained or would block legitimate onboarding before a support process exists. |
| Only restrict commit and push to allowlisted URLs | Use when users may read from broad public sources but must only write code back to approved enterprise repositories. | Avoid when cloning from unapproved repositories is also a data or supply-chain risk. |
| Empty allowlist with restrictions enabled | Use only to temporarily block Git operations during incident response or while governance is being finalized. | Do not use as a normal steady state unless the workspace should not use Git folders. |

### Recommendation

For production and governed development workspaces, enable Git URL allowlist restrictions and allow only approved Git organizations or project paths. Keep the allowlist broad enough to avoid brittle maintenance, but narrow enough to prevent personal repositories and unapproved external destinations.

Good allowlist candidates include:

- Approved enterprise GitHub organization URLs.
- Approved Azure DevOps organization/project URLs.
- Approved GitLab group URLs.
- Approved Bitbucket workspace URLs.

Avoid allowlisting personal repositories, public forks, or broad host-level patterns unless the workspace is explicitly low risk.

### Git URL Allow List

The allowlist should be treated as a source-code supply-chain control. It helps answer: "Which remote Git locations are trusted for this workspace?"

| Enable or populate when | Keep empty or unrestricted when |
| --- | --- |
| The workspace contains production notebooks, jobs, Databricks Asset Bundles, app code, libraries, or sensitive logic. | The workspace is a temporary sandbox with non-sensitive code and no production data. |
| Developers should only pull from or push to enterprise-managed repositories. | Users are still evaluating Git providers and no governance decision has been made. |

### Allow Repos To Export IPYNB Output

This setting controls whether `.ipynb` notebook output can be committed through Databricks Repos / Git folders.

Notebook outputs can contain sample data, query results, charts, model outputs, error messages, environment details, or accidental secrets. Committing outputs to Git can leak data outside the workspace and make repository diffs noisy.

| Configuration | When to enable | When not to enable |
| --- | --- | --- |
| Disable output export | Recommended default for production, regulated, customer-data, and shared analytics workspaces. | Avoid only when teams have a clear reason to version notebook outputs. |
| Allow selected users or groups | Use for teaching, demos, reproducible research, or review workflows where output is intentionally part of the artifact. | Do not use for broad groups that work with sensitive data. |
| Allow broadly | Use only in low-risk training or sandbox workspaces. | Do not use in governed production development. |

### Recommendation

Keep IPYNB output export disabled by default. If outputs must be versioned, require data review, secret scanning, and a repository location approved for that data classification.

## Development - Apps

Databricks Apps let teams build and deploy custom applications in the workspace. Development settings for apps help control where app code comes from and which OAuth scopes app developers can request when acting on behalf of users.

Source: [Databricks - Databricks Apps](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/)

### Only Allow App Deployments From Git

When enabled, apps in the workspace can only be deployed from Git. In the screenshot, this setting is **Off**.

Source: [Databricks - Deploy Databricks Apps](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/deploy)

| Setting | When to enable | When not to enable |
| --- | --- | --- |
| On | Recommended for production apps, regulated workspaces, and teams that require reviewable source, branch protection, pull requests, and CI/CD-style promotion. | Avoid temporarily during prototyping if developers need quick manual deployment and the app/data risk is low. |
| Off | Acceptable for sandbox, proof-of-concept, training, or early development where speed matters more than strict deployment provenance. | Do not leave off for production apps that access sensitive data or serve business users. |

### Recommendation

Turn this on before Databricks Apps become production-facing. Git-only deployment creates a cleaner path for code review, change history, rollback, automated scanning, and separation between development and production app promotion.

### Restrict OAuth Scopes For Apps To Selected Values

This setting limits the OAuth scopes app developers can request when apps act on behalf of users. The UI explains that `*` allows all supported scopes and an empty list effectively disables on-behalf-of-user behavior.

OAuth scopes are important because they define what an app may request permission to do for a user. Broad scopes can be convenient, but they increase the impact of a vulnerable or over-permissioned app.

Source: [Databricks - Configure authorization in a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth)

| Configuration | When to use | When not to use |
| --- | --- | --- |
| `All APIs (*)` | Use only in sandbox or early development where app behavior is being explored and no sensitive data is involved. | Avoid in production because app developers can request any supported user-delegated scope. |
| Selected allowed scopes | Recommended for governed workspaces. Allow only the scopes that approved app patterns require. | Avoid setting too narrowly without testing, because legitimate apps may fail authorization. |
| Empty list | Use when apps should not act on behalf of users, or during a temporary lockdown. | Do not use if production apps require user-delegated actions. |

### Recommendation

For production workspaces, replace `All APIs (*)` with a reviewed list of approved scopes. Start from the minimum scopes needed by approved app templates, test apps in development, and promote the same scope policy to production.

Good governance practices:

- Require app owners for each production app.
- Review requested OAuth scopes during app approval.
- Prefer service-principal or app-specific patterns where user-delegated access is not required.
- Keep app permissions aligned with Unity Catalog and workspace object permissions.
- Reassess scopes when app functionality changes.

## Recommended Development Baseline

| Workspace type | Recommended baseline |
| --- | --- |
| Production app or governed development workspace | Enable Git URL allowlist restrictions; populate approved Git URLs; disable IPYNB output export; require Git-based app deployments; restrict app OAuth scopes to approved values. |
| Production analytics workspace | Restrict Git URLs to enterprise repositories; keep notebook output export disabled; allow app deployment only from Git if apps are used. |
| Development workspace | Use Git allowlists if enterprise repositories are known; allow broader app OAuth scopes only for testing; keep IPYNB outputs disabled unless needed. |
| Sandbox or training workspace | More permissive Git and app settings can be acceptable if data is synthetic, repositories are non-sensitive, and apps are not production-facing. |

## Development Change Checklist

Before changing development settings, confirm:

- Which Git providers, organizations, projects, and repository paths are approved.
- Whether existing Git folders use remote URLs that would be blocked by the allowlist.
- Whether any teams intentionally commit `.ipynb` outputs and what data those outputs contain.
- Whether Databricks Apps are used for production, demos, internal tools, or experiments.
- Whether apps need user-delegated OAuth scopes or can use narrower service-owned access patterns.
- Whether Git-only app deployment would affect existing app release processes.

## Advanced Settings

The Advanced tab contains high-impact workspace controls. Some settings are reversible toggles, while others are irreversible purge actions. Treat this tab as an administrator-only governance area.

Advanced settings can affect support access, API authentication, workspace onboarding behavior, storage recoverability, Delta table defaults, AI feature routing, MLflow behavior, and audit log volume.

## Advanced - Access Control

### Workspace Access For Azure Databricks Personnel

This Azure Databricks setting enables or disables workspace access for Azure Databricks personnel. It is intended for support and operations scenarios where Databricks personnel may need access to help troubleshoot issues.

Source: [Microsoft Learn - Azure Databricks workspace settings](https://learn.microsoft.com/en-us/azure/databricks/admin/workspace-settings/)

| Setting | When to enable | When not to enable |
| --- | --- | --- |
| On | Enable when your support model allows Azure Databricks personnel access for troubleshooting, escalation, or operational support under your organization's policies. | Avoid leaving enabled if your organization requires explicit just-in-time approval for vendor/support access or has strict regulated access controls. |
| Off | Use for highly regulated, sensitive, or restricted workspaces where support access must be disabled by default. | Do not disable without understanding support impact and escalation procedures. |

### Recommendation

For production workspaces, align this setting with your vendor access policy. If enabled, make sure support access is covered by contractual, audit, and incident-response processes. If disabled, document how admins will troubleshoot support cases that require Databricks assistance.

### Personal Access Tokens

Personal access tokens, or PATs, let users authenticate to the Databricks REST API. The screenshot shows PATs enabled, with **Permission Settings** available for finer control.

Source: [Databricks - Manage personal access tokens](https://docs.databricks.com/aws/en/admin/access-control/tokens)

| Setting | When to enable | When not to enable |
| --- | --- | --- |
| On with permission restrictions | Use when users, service principals, tools, or automation still require PAT-based REST API access. Restrict who can create and use tokens. | Avoid broad access where OAuth, service principals, workload identity federation, or short-lived credentials can replace PATs. |
| Off | Use in mature production environments that have migrated automation to stronger auth patterns and no longer need PATs. | Do not disable until existing automation, CI/CD, notebooks, jobs, and integrations have been inventoried and migrated. |

### Recommendation

Avoid unrestricted PAT usage. If PATs are enabled, use permission settings to limit token creation and usage to approved users, groups, or service principals. Prefer service principals and OAuth-based authentication for production automation.

Governance practices:

- Set short token lifetimes where possible.
- Review active tokens periodically.
- Remove tokens for departed users or unused automation.
- Avoid embedding PATs in notebooks, repos, environment variables, or dashboards.
- Monitor token usage through audit logs.

### Choose Entitlements When Adding Principals To Workspaces

This setting controls the rollout behavior for a Databricks change where admins choose each principal's entitlements when adding them to a workspace, instead of automatically inheriting entitlements from the `users` system group. The screenshot shows current behavior as **Legacy behavior (action may be needed)**.

Source: [Databricks - Manage users and groups](https://docs.databricks.com/admin/users-groups/users)

| Behavior | When to use | When not to use |
| --- | --- | --- |
| New behavior | Recommended for governed workspaces because admins explicitly choose entitlements at onboarding time. | Test first if onboarding automation assumes legacy inherited entitlements. |
| Legacy behavior | Use temporarily during rollout if scripts, SCIM provisioning, or operational workflows need time to adapt. | Do not keep long term if it grants broader entitlements than intended. |

### Recommendation

Move to the new behavior after testing user and group provisioning workflows. Explicit entitlement selection reduces accidental workspace access and makes onboarding easier to audit.

Before changing:

- Review SCIM provisioning behavior.
- Review default entitlements assigned through groups.
- Test adding users, groups, and service principals in a non-production workspace.
- Update runbooks so admins know which entitlements to assign.

## Advanced - Storage

### Permanently Purge Workspace Storage

This action permanently purges deleted workspace storage. It is an irreversible cleanup action and should not be treated like normal delete or trash behavior.

Source: [Databricks - Manage workspace storage](https://docs.databricks.com/aws/en/admin/workspace-settings/storage)

| Use when | Do not use when |
| --- | --- |
| Legal, privacy, retention, or cleanup requirements require permanent deletion of workspace storage that is already eligible to purge. | You are unsure whether users may need to recover deleted notebooks, files, or workspace assets. |
| A workspace migration or decommissioning process has been approved and recovery windows are complete. | There is an active incident, investigation, or audit hold that may require the data. |

### Recommendation

Use only with an approved change request. Confirm backups, retention requirements, audit/legal holds, and stakeholder sign-off before purging.

### Permanently Purge All Revision History

This action purges notebook revision history saved before the selected timeframe. The screenshot shows **24 hours and older**. Once purged, revision history is not recoverable.

Source: [Databricks - Manage notebooks](https://docs.databricks.com/notebooks/notebooks-manage)

| Use when | Do not use when |
| --- | --- |
| You need to reduce retained notebook history for privacy, cleanup, or compliance reasons after the recovery window is accepted. | Users may need older revisions for recovery, audit, investigation, or code provenance. |

### Recommendation

Do not purge revision history casually. Prefer source control for long-term code history, and communicate before purging so notebook owners have time to preserve needed work.

### Permanently Purge Cluster Logs

This action permanently purges Spark driver logs and historical metrics snapshots for all clusters in the workspace. Once purged, logs and snapshots are non-recoverable.

Source: [Databricks - Compute logs](https://docs.databricks.com/aws/en/compute/configure.html#compute-logs)

| Use when | Do not use when |
| --- | --- |
| Retention policy, privacy requirements, or workspace decommissioning requires log cleanup and troubleshooting windows are complete. | There is an open support case, incident, performance investigation, security investigation, or audit requirement. |

### Recommendation

Purge cluster logs only after confirming no active troubleshooting or audit need exists. For production workspaces, coordinate with platform, security, and support teams.

### Auto-Enable Deletion Vectors

Deletion vectors are a Delta Lake table feature that can improve performance for row-level operations by tracking deleted rows without rewriting entire data files immediately. The screenshot shows **Default (All new tables)**.

Source: [Databricks - What are deletion vectors?](https://docs.databricks.com/aws/en/delta/deletion-vectors)

| Configuration | When to use | When not to use |
| --- | --- | --- |
| Default / all new tables | Use for modern Databricks-first workloads where runtimes and downstream systems support deletion vectors. | Avoid if external engines, older runtimes, or sharing/compatibility requirements do not support deletion vectors. |
| Disabled or limited | Use when compatibility with older clients, external readers, or strict table feature governance is more important than default performance benefits. | Avoid disabling broadly if most workloads benefit from deletion vectors and compatibility has been validated. |

### Recommendation

Keep the default for new tables only after validating downstream compatibility. If your data is read by external engines, older jobs, Delta Sharing recipients, or non-Databricks clients, test deletion-vector-enabled tables before broad rollout.

## Advanced - Other

### Default Catalog For The Workspace

The default catalog determines which Unity Catalog catalog is used by default when queries or objects do not fully qualify a catalog. The screenshot shows `dbw_test_workspace`.

Source: [Databricks - Manage the default catalog](https://docs.databricks.com/aws/en/catalogs/default)

| Configure when | Do not configure casually when |
| --- | --- |
| You want users, SQL queries, notebooks, dashboards, and jobs to resolve unqualified object names into an approved workspace catalog. | Multiple teams share the workspace and a single default catalog would cause confusion or accidental writes. |
| You are migrating from `hive_metastore` to Unity Catalog and want a safer default target. | Legacy workloads rely on another default catalog and have not been tested. |

### Recommendation

Set a workspace default catalog for governed Unity Catalog workspaces. Choose a catalog aligned with environment and workspace purpose, such as `dev_workspace`, `prod_analytics`, or a dedicated workspace catalog. Encourage fully qualified names for production jobs even when a default catalog exists.

### Partner-Powered AI Features

This setting enables AI product features, such as Genie Code, to use model partner providers for the workspace. The UI notes that model partners do not access or retain your data. If disabled, AI features use Databricks-hosted models when available, and the setting does not disable AI features entirely.

Source: [Databricks - Workspace settings](https://docs.databricks.com/admin/workspace-settings/)

| Setting | When to enable | When not to enable |
| --- | --- | --- |
| Enabled / default | Use when your organization allows Databricks AI features to route to approved model partner providers and wants the best available AI feature coverage. | Avoid if policy requires only Databricks-hosted models or restricts model partner processing. |
| Disabled | Use for strict data governance, regulated workspaces, or organizations that have not approved model partner providers. | Do not assume this disables all AI features; it changes provider routing where Databricks-hosted models are available. |

### Recommendation

Align this setting with AI governance and data processing policy. For regulated production workspaces, review with security, privacy, and legal teams before leaving partner-powered AI enabled.

### Databricks Autologging

Databricks Autologging automatically logs supported interactive machine learning training runs on Databricks Runtime for Machine Learning to MLflow.

Source: [Databricks - Databricks Autologging](https://docs.databricks.com/aws/en/mlflow/databricks-autologging)

| Setting | When to enable | When not to enable |
| --- | --- | --- |
| On | Recommended for ML workspaces where experiment tracking, reproducibility, and model lineage are important. | Avoid if automatic logging could capture sensitive parameters, metrics, artifacts, or model details that should not be stored in MLflow. |
| Off | Use for highly controlled experiments where logging must be explicit, minimized, or approved per project. | Do not disable if teams depend on automatic MLflow tracking for governance and reproducibility. |

### Recommendation

Keep enabled for most ML development workspaces, but train users to avoid logging secrets or sensitive data as parameters, tags, metrics, or artifacts. Use MLflow experiment permissions and retention practices.

### Legacy MLflow Model Serving

This setting enables or disables legacy MLflow Model Serving for the workspace. The UI notes that disabling this option will not disable existing model serving.

Source: [Databricks - Model serving](https://docs.databricks.com/aws/en/machine-learning/model-serving/)

| Setting | When to enable | When not to enable |
| --- | --- | --- |
| On | Use only when legacy MLflow Model Serving is still needed for existing workflows. | Avoid for new production patterns if your organization has moved to current Databricks Model Serving capabilities. |
| Off | Use when legacy serving should no longer be used for new workloads. | Do not disable without confirming current legacy-serving users and migration impact. |

### Recommendation

Plan migration away from legacy serving. Inventory existing served models, confirm owners, and move new deployments to current Databricks Model Serving patterns.

### Verbose Audit Logs

Verbose audit logs increase the detail captured in audit logging. This can improve security investigation and compliance evidence, but it may increase log volume and cost.

Source: [Databricks - Diagnostic log reference](https://docs.databricks.com/aws/en/admin/account-settings/audit-logs)

| Setting | When to enable | When not to enable |
| --- | --- | --- |
| On | Use for regulated workspaces, security investigations, high-sensitivity environments, or when compliance requires more detailed audit records. | Avoid enabling broadly without understanding log volume, storage cost, SIEM ingestion cost, and retention impact. |
| Off | Acceptable for low-risk development or sandbox workspaces where standard audit logging is sufficient. | Do not leave off if security, compliance, or incident-response requirements need the extra detail. |

### Recommendation

Enable verbose audit logs for sensitive production workspaces when monitoring pipelines can handle the additional volume. Coordinate with the team that owns audit log delivery, storage, SIEM ingestion, retention, and alerting.

## Recommended Advanced Baseline

| Workspace type | Recommended baseline |
| --- | --- |
| Production with sensitive data | Disable or tightly govern PATs; use explicit entitlement behavior; avoid purge actions without change approval; validate deletion vector compatibility; set a default UC catalog; review partner-powered AI; enable verbose audit logs if monitoring can handle it. |
| Production ML workspace | Keep Autologging enabled with guidance; review partner-powered AI; migrate from legacy MLflow Model Serving; restrict PATs; enable verbose audit logs based on compliance needs. |
| Development workspace | PATs may remain enabled for approved users; avoid irreversible purges; use a dev default catalog; keep Autologging enabled for ML teams; use verbose logs selectively. |
| Sandbox or training workspace | More permissive settings can be acceptable, but purge actions and broad PAT access still need care. |

## Advanced Change Checklist

Before changing advanced settings, confirm:

- Whether support/vendor access policy allows Azure Databricks personnel access.
- Which users, jobs, tools, or integrations still use personal access tokens.
- Whether SCIM or onboarding automation depends on legacy entitlement behavior.
- Whether purge actions conflict with retention, legal hold, support, audit, or incident needs.
- Whether downstream readers support deletion-vector-enabled Delta tables.
- Whether the workspace has a clear Unity Catalog default catalog strategy.
- Whether partner-powered AI is approved by security, privacy, and legal teams.
- Whether Autologging, legacy model serving, and verbose audit logs align with ML and compliance requirements.

## Recommended Rollout Plan

| Step | Owner | Action |
| --- | --- | --- |
| 1 | Workspace admin | Set workspace label for each environment. |
| 2 | BI owner | Define dashboard theme standards. |
| 3 | Workspace admin | Configure AI/BI workspace theme in a dev or test workspace first. |
| 4 | Dashboard owners | Apply the workspace theme to selected existing dashboards and review readability. |
| 5 | Governance team | Confirm colors, contrast, labels, and naming conventions. |
| 6 | Workspace admin | Promote the same standards to production workspaces. |
| 7 | Genie owner | Configure Genie One homepage and pin trusted assets. |
| 8 | Security / platform owner | Review Security tab settings for compute access mode, embedding, collaboration platforms, downloads, exports, uploads, and clipboard behavior. |
| 9 | Platform / FinOps owner | Review Compute tab settings for default warehouse, serverless usage policies, package repositories, base environments, and interactive timeout. |
| 10 | Development platform owner | Review Development tab settings for Git URL allowlist, IPYNB output export, Git-only app deployment, and app OAuth scopes. |
| 11 | Security / governance owner | Review Advanced tab settings for personnel access, PATs, entitlement behavior, purge actions, deletion vectors, default catalog, AI/ML behavior, and verbose audit logs. |
| 12 | Workspace admin | Test security, compute, development, and advanced changes in a lower environment before applying to production. |
| 13 | Support / enablement | Communicate where users should start, which assets are official, and which compute, Git, app, API token, AI/ML, or data movement behaviors are restricted. |

## Recommended Baseline

For most workspaces, enable or configure these settings:

| Setting | Recommendation |
| --- | --- |
| Workspace label | Configure for every workspace, especially dev/test/prod. |
| AI/BI workspace theme | Configure when dashboards are shared with business users or executives. |
| Genie One homepage | Configure when Genie One is used by more than a small pilot group. |
| Pinned content | Enable only when there are trusted, maintained assets to promote. |
| Existing dashboard theme migration | Migrate important dashboards deliberately; do not assume they update automatically. |
| Default access mode for job compute | Prefer `Dedicated` or validated `Standard`; avoid leaving production workspaces at `Not set`. |
| Embed dashboards and Genie Spaces | Keep disabled unless approved domains and access controls are documented. |
| Allowed collaboration platforms | Keep `Deny all` unless Slack or Teams integration is formally approved. |
| Public collaboration messages | Keep off by default. |
| Notebook, SQL, file, artifact, volume, and clipboard downloads | Disable in sensitive production workspaces unless there is an approved business need. |
| Upload data using the UI | Enable only where self-service ingestion is allowed; disable where ingestion must use governed pipelines. |
| Default warehouse | Use a specific governed warehouse for production BI; `Last selected` is acceptable for flexible dev workspaces. |
| SQL warehouses and serverless compute | Manage deliberately with permissions, naming, sizing, auto-stop, monitoring, and cost attribution. |
| Default package repositories | Configure approved Python package repositories in production and regulated workspaces. |
| Workspace base environments | Use stable base environments for shared serverless notebook work; keep them small and tested. |
| Serverless usage policies | Configure before broad serverless rollout so cost attribution tags are enforced. |
| Serverless interactive execution timeout | Set a timeout that supports normal exploration but pushes durable long-running work into jobs or pipelines. |
| Git URL allow list permission | Restrict Git operations in production and governed workspaces; avoid `Disabled (no restrictions)` for sensitive workspaces. |
| Git URL allow list | Populate with approved enterprise Git organizations, projects, or repository paths. |
| Allow repos to export IPYNB output | Keep disabled by default; allow only for reviewed low-risk workflows. |
| Only allow app deployments from Git | Enable before apps become production-facing. |
| Restrict OAuth scopes for apps | Avoid `All APIs (*)` in production; use selected approved scopes or an empty list when on-behalf-of-user access should be disabled. |
| Workspace access for Azure Databricks personnel | Align with vendor/support access policy; disable by default for highly regulated workspaces unless support access is approved. |
| Personal Access Tokens | Avoid unrestricted PATs; restrict token permissions or disable after automation migrates to stronger auth patterns. |
| Entitlement behavior when adding principals | Move to explicit entitlement selection after testing provisioning workflows. |
| Purge workspace storage, revision history, and cluster logs | Use only through approved change control because these actions are irreversible. |
| Auto-enable deletion vectors | Keep default only after downstream reader compatibility is validated. |
| Default catalog | Set an approved Unity Catalog default for governed workspaces. |
| Partner-powered AI features | Review with security, privacy, and legal before enabling in regulated workspaces. |
| Databricks Autologging | Keep enabled for ML governance unless automatic MLflow logging may capture sensitive data. |
| Legacy MLflow Model Serving | Disable for new legacy serving after migration planning; existing serving is not disabled by the toggle. |
| Verbose Audit Logs | Enable for sensitive production workspaces if log delivery, retention, SIEM, and cost are ready. |

## Risks And Guardrails

| Risk | Guardrail |
| --- | --- |
| Theme changes surprise dashboard owners | Announce theme standards and test in lower environments first. |
| Existing dashboards remain visually inconsistent | Track priority dashboards and apply the workspace theme manually. |
| Pinned Genie content points to stale assets | Assign an owner to review pinned content monthly or quarterly. |
| Pinned content exposes confusing access errors | Pin only assets with appropriate audience permissions. |
| Workspace labels drift across account | Prefer an account-level convention for labels and colors. |
| Genie answers expose more than expected | Limit dashboard datasets to the fields and rows intended for viewers. |
| Security setting changes break legacy jobs | Inventory jobs without explicit access mode before changing the default job compute access mode. |
| Downloads and clipboard copy bypass normal review | Disable UI download, export, and clipboard features in sensitive workspaces and provide approved extract workflows. |
| Collaboration integrations expose answers too broadly | Keep public messages off and allow only approved platforms/channels. |
| Volume UI download setting creates false confidence | Remember that APIs, SDKs, and CLI can still download files when users have the required permissions. |
| Default warehouse sends users to costly or wrong compute | Set a governed production default and monitor warehouse usage. |
| Package repository changes break workloads | Test package repository changes against representative notebooks, jobs, model serving builds, clusters, and pipelines. |
| Base environments become hard to maintain | Keep base environments small, versioned, and owned by a platform team. |
| Serverless costs lack attribution | Require serverless usage policies with team, environment, owner, and cost center tags. |
| Long serverless interactive timeout hides inefficient queries | Monitor long-running notebooks and move repeatable workloads into jobs or pipelines. |
| Unrestricted Git URLs allow unapproved source or destinations | Enable Git URL allowlist restrictions and maintain approved enterprise repository patterns. |
| Notebook outputs leak through Git commits | Disable IPYNB output export unless outputs are intentionally reviewed and approved for version control. |
| Manual app deployments bypass review | Require Git-based app deployments for production app workflows. |
| Apps request overly broad user-delegated permissions | Restrict app OAuth scopes to approved values and review scopes during app approval. |
| Vendor/support access conflicts with policy | Align Azure Databricks personnel access with just-in-time support and audit procedures. |
| PATs become unmanaged long-lived credentials | Restrict token creation, shorten lifetimes, review active tokens, and migrate automation to OAuth or service principals. |
| Entitlement rollout breaks onboarding automation | Test SCIM and provisioning workflows before changing entitlement behavior. |
| Purge actions delete evidence or recoverable work | Require change approval and check legal hold, audit, support, and incident needs before purging. |
| Deletion vectors break downstream compatibility | Test with external engines, older runtimes, sharing recipients, and production jobs before broad enablement. |
| Default catalog causes accidental writes | Choose a catalog aligned to workspace purpose and encourage fully qualified names in production jobs. |
| Partner-powered AI conflicts with data policy | Review model-provider routing with security, privacy, and legal teams. |
| Autologging captures sensitive ML artifacts | Train users and govern MLflow experiment permissions and retention. |
| Verbose audit logs increase cost and noise | Size log storage, SIEM ingestion, retention, and alerting before enabling broadly. |

## Decision Guidance

Enable or configure these settings when the workspace has multiple user groups, multiple environments, business-facing dashboards, Genie One adoption, sensitive data, shared compute, serverless usage, Git-based development, Databricks Apps, API automation, ML workloads, or compliance logging needs. The main benefits are reducing confusion, standardizing presentation, improving discoverability, making trusted analytics easier to recognize, controlling common UI-based data movement paths, improving compute governance, tightening development supply-chain controls, and reducing risk from advanced administrator settings.

For a small sandbox used by one team, a workspace label plus relaxed security, compute, development, and advanced settings may be enough if the data and code are synthetic or low risk. For production analytics, ML, and app workspaces, configure workspace label, AI/BI workspace theme, Genie One homepage, a restrictive security baseline, managed compute settings, governed development settings, and reviewed advanced settings with explicit exceptions for approved downloads, embeds, uploads, collaboration integrations, package sources, serverless policies, Git URLs, app deployment paths, app OAuth scopes, PATs, AI feature routing, purge actions, and audit logging.
