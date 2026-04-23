"""Validators for network security and account-level checks.

These use account-level API tokens and the accounts base URL.
Reference: notebooks/Includes/workspace_analysis.py (checks 3, 35-39, 103, 110-112, 122, 124)
"""

from tests.automated.checks.base_validator import BaseValidator
from tests.automated.checks.registry import register


def _get_account_workspaces(validator: BaseValidator) -> list[dict]:
    """Fetch workspace list from accounts API."""
    token = validator.token_provider.get_account_token()
    acct_id = validator.config.account_console_id
    acct_client = validator.account_rest or validator.rest
    resp = acct_client.get(f"/accounts/{acct_id}/workspaces", token=token)
    # Account API may return list directly or under a key
    if isinstance(resp, list):
        return resp
    for key, val in resp.items():
        if isinstance(val, list):
            return val
    return []


def _get_this_workspace(validator: BaseValidator) -> dict | None:
    """Get the workspace record for the configured workspace_id."""
    workspaces = _get_account_workspaces(validator)
    return next(
        (
            w
            for w in workspaces
            if str(w.get("workspace_id")) == validator.config.workspace_id
        ),
        None,
    )


@register("3")
class Check3_CustomerManagedKeys(BaseValidator):
    """DP-3: Customer-managed keys for managed services and workspace storage."""

    CHECK_ID = "DP-3"
    CHECK_NAME = "Customer-managed keys"
    CLOUDS = ["aws"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        ws = _get_this_workspace(self)
        if ws is None:
            return 1, {"error": "Workspace not found in account"}
        storage_cmk = ws.get("storage_customer_managed_key_id")
        managed_cmk = ws.get("managed_services_customer_managed_key_id")
        if storage_cmk is None and managed_cmk is None:
            return 1, {
                "storage_cmk": storage_cmk,
                "managed_services_cmk": managed_cmk,
            }
        return 0, {
            "storage_cmk": storage_cmk,
            "managed_services_cmk": managed_cmk,
        }


@register("35")
class Check35_PrivateLink(BaseValidator):
    """NS-3: Front-end private connectivity configured."""

    CHECK_ID = "NS-3"
    CHECK_NAME = "Front-end private connectivity"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        ws = _get_this_workspace(self)
        if ws and ws.get("private_access_settings_id"):
            return 0, {
                "private_access_settings_id": ws["private_access_settings_id"]
            }
        return 1, {"workspaceId": self.config.workspace_id}


@register("36")
class Check36_BYOVPC(BaseValidator):
    """NS-4: Workspace uses a customer-managed VPC/VNet."""

    CHECK_ID = "NS-4"
    CHECK_NAME = "Customer-managed VPC"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        ws = _get_this_workspace(self)
        if ws:
            network_id = ws.get("network_id", "")
            if network_id:
                return 0, {"network_id": network_id}
        return 1, {"workspaceId": self.config.workspace_id}


@register("37")
class Check37_WorkspaceIPAccessList(BaseValidator):
    """NS-5: Workspace-level IP access lists configured."""

    CHECK_ID = "NS-5"
    CHECK_NAME = "Workspace IP access lists"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_workspace_token()
        try:
            resp = self.rest.get(
                "/ip-access-lists", token=token, version="2.0"
            )
            ip_lists = resp.get("ip_access_lists", [])
            enabled = [l for l in ip_lists if l.get("enabled")]
            if enabled:
                return 0, {"enabled_ip_lists": len(enabled)}
            return 1, {"workspaceId": self.config.workspace_id}
        except Exception:
            return 1, {"note": "IP access list API not available"}


@register("39")
class Check39_SecureClusterConnectivity(BaseValidator):
    """NS-6: Secure cluster connectivity (No Public IP / Azure SCC)."""

    CHECK_ID = "NS-6"
    CHECK_NAME = "Secure cluster connectivity"
    CLOUDS = ["azure"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        ws = _get_this_workspace(self)
        if ws and ws.get("enableNoPublicIp", False):
            return 0, {"enableNoPublicIp": True}
        return 1, {"workspaceId": self.config.workspace_id}


@register("103")
class Check103_CSPAccount(BaseValidator):
    """INFO-37: Compliance security profile for new workspaces (account-level)."""

    CHECK_ID = "INFO-37"
    CHECK_NAME = "Account CSP for new workspaces"
    CLOUDS = ["aws"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_account_token()
        acct_id = self.config.account_console_id
        acct_client = self.account_rest or self.rest
        try:
            resp = acct_client.get(
                f"/accounts/{acct_id}/settings/types/shield_csp_enablement_ac/names/default",
                token=token,
            )
            is_enforced = (
                resp.get("csp_enablement_account", {}).get("is_enforced", False)
            )
            if is_enforced:
                return 0, {"csp_enforced": True}
            return 1, {"csp_enforced": False}
        except Exception as e:
            return 1, {"error": str(e)}


@register("110")
class Check110_AccountIPAccessList(BaseValidator):
    """NS-8: Account console IP access lists configured."""

    CHECK_ID = "NS-8"
    CHECK_NAME = "Account console IP access lists"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_account_token()
        acct_id = self.config.account_console_id
        acct_client = self.account_rest or self.rest
        resp = acct_client.get(
            f"/accounts/{acct_id}/ip-access-lists", token=token
        )
        ip_lists = resp.get("ip_access_lists", [])
        enabled = [l for l in ip_lists if l.get("enabled")]
        if enabled:
            return 0, {"enabled_ip_lists": len(enabled)}
        return 1, {"enabled_ip_lists": 0}


@register("111")
class Check111_NetworkPolicy(BaseValidator):
    """NS-9: Workspace has proper network policy (egress) configuration."""

    CHECK_ID = "NS-9"
    CHECK_NAME = "Network policy configuration"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_account_token()
        acct_id = self.config.account_console_id
        ws_id = self.config.workspace_id
        acct_client = self.account_rest or self.rest

        # Get network policies
        try:
            policies_resp = acct_client.get(
                f"/accounts/{acct_id}/network-policies", token=token
            )
        except Exception:
            return 1, {"reason": "CANNOT_FETCH_POLICIES"}

        policies = policies_resp.get("items", policies_resp.get("network_policies", []))

        # Workspace → policy lookup. /network (NOT /network-connectivity-config,
        # which is the unrelated NCC API that returns ENDPOINT_NOT_FOUND here).
        try:
            ws_config = acct_client.get(
                f"/accounts/{acct_id}/workspaces/{ws_id}/network",
                token=token,
            )
        except Exception:
            ws_config = {}

        policy_id = None
        if isinstance(ws_config, dict):
            policy_id = ws_config.get("network_policy_id")

        if not policy_id:
            return 1, {"reason": "NO_POLICY_ASSIGNED"}

        # Find the policy details
        policy = next(
            (p for p in policies if p.get("network_policy_id") == policy_id),
            None,
        )
        if not policy:
            return 1, {"reason": "POLICY_NOT_FOUND", "policy_id": policy_id}

        # Evaluate policy
        egress = policy.get("egress", {})
        net_access = egress.get("network_access", {})
        restriction_mode = net_access.get("restriction_mode", "")
        enforcement = net_access.get("policy_enforcement", {})
        enforcement_mode = enforcement.get("enforcement_mode", "")

        if restriction_mode == "FULL_ACCESS":
            return 1, {"reason": "FULL_ACCESS_MODE", "policy_id": policy_id}
        if enforcement_mode == "ENFORCED":
            return 0, {"policy_id": policy_id, "mode": "ENFORCED"}
        if enforcement_mode == "DRY_RUN":
            return 1, {"reason": f"DRY_RUN_MODE", "policy_id": policy_id}
        return 1, {
            "reason": f"UNKNOWN_MODE ({enforcement_mode})",
            "policy_id": policy_id,
        }


@register("112")
class Check112_DisableLegacyFeaturesAccount(BaseValidator):
    """GOV-37: Disable legacy features for new workspaces (account setting)."""

    CHECK_ID = "GOV-37"
    CHECK_NAME = "Disable legacy features (account)"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_account_token()
        acct_id = self.config.account_console_id
        acct_client = self.account_rest or self.rest
        try:
            resp = acct_client.get(
                f"/accounts/{acct_id}/settings/types/disable_legacy_features/names/default",
                token=token,
            )
            dlf = resp.get("disable_legacy_features", {})
            value = dlf.get("value", False)
            if value is True:
                return 0, {"disable_legacy_features": True}
            return 1, {"disable_legacy_features": value}
        except Exception as e:
            return 1, {"error": str(e)}


@register("122")
class Check122_ContextBasedIngress(BaseValidator):
    """NS-12: Context-Based Ingress (CBI) policy configured.

    Mirrors the fix applied to notebooks/Includes/workspace_analysis.py during
    0.8.0 verification:
      - Workspace → policy mapping comes from `/accounts/.../workspaces/{id}/network`,
        NOT `/network-connectivity-config` (that's the unrelated NCC API).
      - CBI restriction lives at `ingress.public_access.restriction_mode`,
        not `ingress.restriction_mode`.
      - When the enforcement mode is "Dry run for all products" the API moves the
        entire ingress block to a top-level `ingress_dry_run` key (same nested
        shape). Check both paths. Dry-run counts as adopted.
    """

    CHECK_ID = "NS-12"
    CHECK_NAME = "Context-Based Ingress policy"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_account_token()
        acct_id = self.config.account_console_id
        ws_id = self.config.workspace_id
        acct_client = self.account_rest or self.rest

        try:
            policies_resp = acct_client.get(
                f"/accounts/{acct_id}/network-policies", token=token
            )
        except Exception:
            return 1, {"reason": "CANNOT_FETCH_POLICIES"}
        policies = policies_resp.get("items", policies_resp.get("network_policies", []))

        policy_id = None
        try:
            ws_config = acct_client.get(
                f"/accounts/{acct_id}/workspaces/{ws_id}/network",
                token=token,
            )
            if isinstance(ws_config, dict):
                policy_id = ws_config.get("network_policy_id")
        except Exception:
            pass

        if not policy_id:
            return 1, {"reason": "NO_POLICY_ASSIGNED"}

        policy = next(
            (p for p in policies if p.get("network_policy_id") == policy_id),
            None,
        )
        if not policy:
            return 1, {"reason": "POLICY_NOT_FOUND", "policy_id": policy_id}

        enforced_mode = (
            policy.get("ingress", {}).get("public_access", {}).get("restriction_mode")
        )
        dryrun_mode = (
            policy.get("ingress_dry_run", {})
            .get("public_access", {})
            .get("restriction_mode")
        )
        restriction_mode = enforced_mode or dryrun_mode
        enforcement = (
            "ENFORCED" if enforced_mode else ("DRY_RUN" if dryrun_mode else None)
        )

        if restriction_mode == "RESTRICTED_ACCESS":
            return 0, {
                "policy_id": policy_id,
                "ingress_mode": restriction_mode,
                "enforcement": enforcement,
            }
        return 1, {
            "reason": "CBI_NOT_CONFIGURED",
            "policy_id": policy_id,
            "ingress_mode": restriction_mode or "none",
        }


@register("124")
class Check124_AccountIPAllowList(BaseValidator):
    """NS-13: Account console has at least one enabled ALLOW-type IP access list."""

    CHECK_ID = "NS-13"
    CHECK_NAME = "Account ALLOW-type IP access list"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_account_token()
        acct_id = self.config.account_console_id
        acct_client = self.account_rest or self.rest
        resp = acct_client.get(
            f"/accounts/{acct_id}/ip-access-lists", token=token
        )
        ip_lists = resp.get("ip_access_lists", [])
        allow_lists = [
            l
            for l in ip_lists
            if l.get("enabled") and l.get("list_type") == "ALLOW"
        ]
        if allow_lists:
            return 0, {"enabled_allow_lists": len(allow_lists)}
        return 1, {"enabled_allow_lists": 0}


@register("125")
class Check125_EgressControl(BaseValidator):
    """NS-14: Egress control from compute — live connectivity test.

    Mirrors the SDK fix applied to clientpkgs/egress_test_client.py during 0.8.0:
      - Probe with GET + stream=True (not HEAD). Some destinations — notably
        ifconfig.me — return 405 to HEAD while serving GET, which would
        misread as "blocked" under status<400 heuristics.
      - Any HTTP response counts as reachable. Real egress block manifests as
        requests.Timeout / ConnectionError in the except branches.
      - Any reachable public destination ⇒ public internet is accessible from
        this compute ⇒ violation. A truly air-gapped workspace fails every
        probe and passes.

    Caveat: this validator runs on whatever compute executes the test (the
    test runner host). That matches SAT's current NS-14 semantics — it also
    tests from the driver's cluster. Per-workspace egress introspection is a
    post-0.8.0 redesign.
    """

    CHECK_ID = "NS-14"
    CHECK_NAME = "Egress control from compute"
    CLOUDS = ["aws", "azure", "gcp"]

    DESTINATIONS = [
        {"name": "google", "url": "https://www.google.com"},
        {"name": "ifconfig", "url": "https://ifconfig.me"},
        {"name": "cloudflare", "url": "https://www.cloudflare.com"},
    ]

    def evaluate_from_api(self) -> tuple[int, dict]:
        import requests

        results = []
        reachable = []
        for dest in self.DESTINATIONS:
            entry = {"name": dest["name"], "url": dest["url"]}
            try:
                resp = requests.get(
                    dest["url"], timeout=10, allow_redirects=True, stream=True
                )
                entry["status_code"] = resp.status_code
                entry["reachable"] = True
                resp.close()
                reachable.append(dest["name"])
            except requests.exceptions.Timeout:
                entry["reachable"] = False
                entry["error"] = "TIMEOUT"
            except requests.exceptions.ConnectionError as e:
                entry["reachable"] = False
                entry["error"] = f"CONNECTION_ERROR: {str(e)[:200]}"
            except Exception as e:
                entry["reachable"] = False
                entry["error"] = f"{type(e).__name__}: {str(e)[:200]}"
            results.append(entry)

        score = 1 if reachable else 0
        return score, {
            "reachable": reachable,
            "total": len(self.DESTINATIONS),
            "results": results,
        }
