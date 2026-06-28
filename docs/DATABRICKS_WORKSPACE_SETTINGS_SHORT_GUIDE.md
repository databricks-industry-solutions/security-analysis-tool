# Databricks Workspace Settings Short Guide

Reviewed: 2026-06-28

This is the short decision guide for Databricks workspace settings. Keep the longer reference guide for detailed setting-by-setting instructions:

[Databricks Workspace Appearance, AI/BI, Security, Compute, Development, And Advanced Settings](DATABRICKS_WORKSPACE_APPEARANCE_AIBI_SETTINGS.md)

## Executive Summary

Workspace settings should be treated as governance controls, not cosmetic preferences. The right baseline reduces environment confusion, prevents casual data movement, improves dashboard trust, controls compute cost, and limits risky development and API access patterns.

The most important decision is the workspace type:

| Workspace type | Recommended posture |
| --- | --- |
| Production with sensitive data | Restrictive security, governed compute, approved Git/app paths, restricted PATs, audited changes, no casual downloads. |
| Production BI / AI/BI | Standard theme, curated Genie homepage, governed SQL warehouse, approved embedding only, controlled downloads. |
| Production ML | Govern PATs, package sources, Autologging, model serving, partner AI, and artifact downloads carefully. |
| Development | More flexible, but still use labels, Git allowlists, cost tags, and tested package/base environments. |
| Sandbox / training | More permissive is acceptable only when data and code are low risk and costs are monitored. |

## Top Recommendations

| Area | Recommended default | Why it matters |
| --- | --- | --- |
| Workspace label | Configure every workspace as `dev`, `test`, `stage`, `prod`, or `sandbox`. | Prevents work in the wrong environment. |
| AI/BI theme | Configure for shared BI workspaces. | Makes official dashboards recognizable and consistent. |
| Genie One homepage | Configure when Genie is used beyond a pilot. | Sends users to trusted dashboards and Genie Spaces. |
| Job compute access mode | Use `Dedicated` or validated `Standard`; avoid `Not set` in production. | Keeps jobs aligned with Unity Catalog-compatible access modes. |
| Downloads, exports, clipboard | Disable in sensitive production unless approved. | Reduces common UI-based exfiltration paths. |
| External embedding | Allow only approved domains. | Prevents dashboards and Genie Spaces from appearing in unapproved apps. |
| Collaboration platforms | Deny by default; allow Slack/Teams only after approval. | Avoids leaking answers into broad channels. |
| Default warehouse | Set a governed production BI warehouse. | Reduces cost surprises and wrong-compute usage. |
| Package repositories | Use approved Python package repositories in production. | Improves supply-chain control and reproducibility. |
| Serverless usage policies | Require tags before broad serverless rollout. | Enables cost attribution by team/project/environment. |
| Git URL allowlist | Restrict production workspaces to enterprise repos. | Controls code source and destination. |
| IPYNB output export | Disable by default. | Notebook outputs can contain data, secrets, and noisy artifacts. |
| App deployments | Require Git for production apps. | Gives reviewable app provenance and rollback. |
| App OAuth scopes | Use selected scopes, not `All APIs (*)`, in production. | Limits blast radius for apps acting on behalf of users. |
| Personal Access Tokens | Restrict or migrate away from PATs. | PATs are long-lived credentials if not governed tightly. |
| Purge actions | Use only through approved change control. | Storage, revision history, and log purges are irreversible. |
| Default catalog | Set an approved Unity Catalog default. | Reduces accidental use of the wrong catalog. |
| Verbose audit logs | Enable for sensitive production if log pipelines are ready. | Improves investigation evidence, but increases log volume. |

## Highest-Risk Decisions

Decide these first for any production workspace:

1. Should users be allowed to download/export/copy data from the UI?
2. Should PATs be enabled, and who can create them?
3. Which Git repositories are trusted?
4. Can apps act on behalf of users, and with which OAuth scopes?
5. Are partner-powered AI features approved by security, privacy, and legal?
6. Can dashboards or Genie Spaces be embedded, and on which domains?
7. Are purge actions blocked behind change approval?
8. Is verbose audit logging required, and can the SIEM/log pipeline handle it?

## Production Baseline

For production workspaces, use this baseline unless there is an approved exception:

| Category | Baseline |
| --- | --- |
| Appearance | Workspace label, AI/BI theme, and curated Genie homepage configured. |
| Security | Restrict downloads, exports, clipboard, public collaboration messages, and unmanaged embedding. |
| Compute | Govern SQL warehouses, serverless policies, package repositories, base environments, and timeout. |
| Development | Restrict Git URLs, disable IPYNB output export, require Git app deployment, restrict OAuth scopes. |
| Advanced | Restrict PATs, use explicit entitlements, avoid purges without approval, validate deletion vectors, set default catalog, review partner AI, enable audit detail if needed. |

## When Not To Lock Everything Down

Do not make sandbox and early development workspaces feel like production unless the data requires it. Over-restricting low-risk workspaces slows learning and creates shadow workflows.

Relax controls when:

- Data is synthetic or non-sensitive.
- The workspace is temporary.
- Costs are capped or closely monitored.
- Users are prototyping and not serving business users.
- Outputs, apps, and repositories are not production-facing.

Still keep labels, basic cost attribution, and clear ownership even in sandboxes.

## Rollout Order

1. Label every workspace and classify it as production, development, sandbox, BI, ML, or app-focused.
2. Apply security controls for data movement and external access.
3. Standardize compute defaults, warehouse ownership, and serverless cost tags.
4. Govern Git repositories, app deployment, and OAuth scopes.
5. Review advanced controls: PATs, personnel access, entitlements, purge actions, default catalog, AI routing, MLflow, and audit logs.
6. Test changes in dev before production.
7. Publish exceptions with owner, reason, review date, and rollback plan.

## Simple Rule

If a setting can move data out, run code from an untrusted place, grant API access, expose AI/BI content externally, increase cost silently, or delete evidence permanently, treat it as a governance decision with an owner and an exception process.
