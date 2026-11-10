"""
Tests for dabs/sat/config.py — non-interactive, no workspace connection needed.

Coverage
--------
- Prompt rendering safety: no message/default may contain bare { } braces.
  inquirer calls str.format(**answers) on both strings.
- Question ordering: every question that gates on a prior answer must appear
  after that prior question.
- ignore-callable coverage: invoke every ignore lambda against realistic
  answer dicts (full, partial, manage_secrets=False) and assert behaviour.
- build_secret_key_names: checkbox selections + key answers -> expected dict.
- _resolve_key_overrides: blank / empty JSON / valid JSON / bad JSON.
- _resolve_app_config_scope: all three resolution branches.
- validate_secrets: correct SDK call signature (scope=, key=) not path=;
  reports all missing keys at once.
"""
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Path setup — must happen before any sat.* imports
# ---------------------------------------------------------------------------
_DABS_DIR = Path(__file__).parent.parent
if str(_DABS_DIR) not in sys.path:
    sys.path.insert(0, str(_DABS_DIR))

# ---------------------------------------------------------------------------
# Minimal stubs — must match the real module contracts
# ---------------------------------------------------------------------------

def _make_stub_module(name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


# Third-party stubs
for _name in ("rich", "rich.progress", "databricks", "databricks.sdk"):
    sys.modules.setdefault(_name, _make_stub_module(_name))

_inquirer = sys.modules.setdefault("inquirer", _make_stub_module("inquirer"))

for _cls_name in ("Text", "Password", "Confirm", "List", "Checkbox"):
    if not hasattr(_inquirer, _cls_name):
        def _make_cls(n):
            class _Q:
                kind = n.lower()
                def __init__(self, name, message="", default=None,
                             ignore=None, choices=None, locked=None,
                             validate=True, echo="*", **kw):
                    self.name    = name
                    self._message = message
                    self._default = default
                    self._ignore  = ignore
                    self.choices  = choices
                    self.locked   = locked
            _Q.__name__ = n
            return _Q
        setattr(_inquirer, _cls_name, _make_cls(_cls_name))

if not hasattr(_inquirer, "list_input"):
    _inquirer.list_input = lambda message="", choices=None, **kw: ""
if not hasattr(_inquirer, "prompt"):
    _inquirer.prompt = lambda questions, **kw: {}

_progress_cls = type("Progress", (), {
    "__init__": lambda self, *a, **k: None,
    "__enter__": lambda self: self,
    "__exit__": lambda self, *a: None,
    "add_task": lambda self, *a, **k: 0,
    "start": lambda self: None,
    "stop": lambda self: None,
})
sys.modules["rich.progress"].__dict__.update({
    "Progress": _progress_cls,
    "SpinnerColumn": object,
    "TextColumn": object,
})

_ws_stub = type("WorkspaceClient", (), {"__init__": lambda self, **kw: None})
sys.modules["databricks.sdk"].__dict__["WorkspaceClient"] = _ws_stub

# A3 fix: cloud_validation returns a BOOL (True = skip / not this cloud).
# Simulate an AWS workspace so azure/gcp are skipped, aws is active.
_utils_stub = _make_stub_module(
    "sat.utils",
    cloud_validation=lambda client, cloud: cloud != "aws",  # bool, not callable
    get_catalogs=lambda **kw: [],
    get_profiles=lambda: [],
    get_warehouses=lambda **kw: [],
    loading=lambda f, *a, **k: [],
    uc_enabled=lambda client: False,
    cloud_type=lambda client: "aws",
)
sys.modules["sat.utils"] = _utils_stub

from sat import config  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fixture — representative answer dict for an AWS workspace
# ---------------------------------------------------------------------------

FULL_ANSWERS_MANAGE = {
    "secret_scope": "sat_scope",
    "manage_secrets": True,
    "scope_contains": [],
    "key_name__client_secret": "client-secret",
    "key_name__account_id": "account-console-id",
    "key_name__client_id": "client-id",
    "key_name__proxies": "proxies",
    "account_id": "12345678-1234-1234-1234-123456789abc",
    "catalog": "main",
    "security_analysis_schema": "security_analysis",
    "enable_serverless": True,
    "warehouse": {"id": "abcd1234abcd1234", "name": "SAT WH"},
    "aws-client-id": "sp-client-id",
    "aws-client-secret": "sp-client-secret",
    "azure-tenant-id": "",
    "azure-subscription-id": "",
    "azure-client-id": "",
    "azure-client-secret": "",
    "gcp-client-id": "",
    "gcp-client-secret": "",
    "use_proxy": False,
    "http": "",
    "https": "",
    "driver_schedule": "0 0 8 ? * Mon,Wed,Fri",
    "secrets_scanner_schedule": "0 0 8 ? * *",
    "job_timezone": "UTC",
    "enable_brickhound": True,
    "brickhound_schedule": "0 0 2 ? * *",
    "app_config_scope": "",
}

# BYO path: manage_secrets=False, account_id and client_id deferred to scope
FULL_ANSWERS_BYO = {
    **FULL_ANSWERS_MANAGE,
    "manage_secrets": False,
    "scope_contains": ["client_secret", "account_id", "client_id"],
    "account_id": "",   # suppressed by ignore, so blank
}


def _build():
    """Build the real question list against a mock AWS client."""
    client = MagicMock()
    client.config = MagicMock()
    client.config.host = "https://adb-test.cloud.databricks.com"
    return config.build_questions(client)


# ---------------------------------------------------------------------------
# Helper: invoke an ignore (bool or callable) safely
# ---------------------------------------------------------------------------

def _eval_ignore(q, answers):
    ig = q._ignore
    if ig is None:
        return False
    if callable(ig):
        return ig(answers)
    return bool(ig)


def _eval_default(q, answers):
    """Resolve a question's default, handling callables (like app_config_scope)."""
    d = q._default
    if callable(d):
        return d(answers)
    return d


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestPromptRenderingSafety(unittest.TestCase):
    """inquirer calls str.format(**answers) on every string message and default.
    Callable messages/defaults bypass str.format entirely — skip those.
    """

    # Max message length before inquirer truncates at width-9 chars on an
    # 80-column terminal.  _print_header truncates when len(base) > width-6.
    MAX_MSG_LEN = 74

    def _render(self, s, label, answers):
        try:
            s.format(**answers)
        except (IndexError, KeyError) as exc:
            self.fail(
                f"Question '{label}' has unsafe braces in {s!r}: {exc}\n"
                "Escape literal braces as {{{{ / }}}}, or remove them."
            )

    def test_all_string_messages_and_defaults_are_format_safe(self):
        for answers in (FULL_ANSWERS_MANAGE, FULL_ANSWERS_BYO):
            for q in _build():
                for attr, label in (("_message", "message"), ("_default", "default")):
                    val = getattr(q, attr, None)
                    if isinstance(val, str):
                        self._render(val, f"{q.name}.{label}", answers)

    def test_all_messages_under_truncation_width(self):
        """No string message may exceed MAX_MSG_LEN chars.

        inquirer._print_header truncates at width-9 on an 80-col terminal
        (effective threshold ≈ 74 chars). A truncated message mid-word
        signals a wording problem.  Callable messages are exempt — their
        return value is checked separately.
        """
        for q in _build():
            msg = q._message
            if not isinstance(msg, str):
                continue
            self.assertLessEqual(
                len(msg), self.MAX_MSG_LEN,
                f"Question '{q.name}' message is {len(msg)} chars (max {self.MAX_MSG_LEN}): {msg!r}"
            )


class TestQuestionOrdering(unittest.TestCase):
    """Gating questions must precede the questions that depend on them."""

    def _names(self):
        return [q.name for q in _build()]

    def _assert_before(self, earlier, later):
        names = self._names()
        ei = names.index(earlier)
        li = names.index(later)
        self.assertLess(
            ei, li,
            f"'{earlier}' (pos {ei}) must precede '{later}' (pos {li})"
        )

    def test_manage_secrets_before_scope_contains(self):
        self._assert_before("manage_secrets", "scope_contains")

    def test_scope_contains_before_key_name_prompts(self):
        names = self._names()
        sc_idx = names.index("scope_contains")
        key_prompts = [n for n in names if n.startswith("key_name__")]
        self.assertTrue(key_prompts, "No key_name__ prompts found")
        for kp in key_prompts:
            self.assertLess(sc_idx, names.index(kp),
                            f"scope_contains must precede {kp}")

    def test_scope_contains_before_account_id(self):
        self._assert_before("scope_contains", "account_id")

    def test_enable_brickhound_before_app_config_scope(self):
        self._assert_before("enable_brickhound", "app_config_scope")

    def test_secret_scope_before_manage_secrets(self):
        self._assert_before("secret_scope", "manage_secrets")


class TestIgnoreCallables(unittest.TestCase):
    """A4: invoke every ignore against real answer dicts; assert behaviour."""

    def test_no_ignore_raises_on_full_answers(self):
        """No ignore callable should crash on either full answer set."""
        for answers in (FULL_ANSWERS_MANAGE, FULL_ANSWERS_BYO):
            for q in _build():
                try:
                    _eval_ignore(q, answers)
                except Exception as exc:
                    self.fail(
                        f"ignore for '{q.name}' raised with answers: {exc}"
                    )

    def test_no_ignore_raises_on_partial_answers(self):
        """Simulate mid-prompt state: only the first N answers are populated."""
        questions = _build()
        partial = {}
        for q in questions:
            try:
                _eval_ignore(q, partial)
            except Exception as exc:
                self.fail(
                    f"ignore for '{q.name}' raised on partial answers {partial}: {exc}"
                )
            # Simulate answering this question (resolve callable defaults too).
            default_val = _eval_default(q, partial)
            if default_val is not None:
                partial[q.name] = default_val
            elif q.name == "scope_contains":
                partial[q.name] = []
            elif q.name == "warehouse":
                partial[q.name] = {"id": "abcd1234abcd1234"}
            else:
                partial[q.name] = ""

    def test_client_secret_hidden_when_byo(self):
        """aws-client-secret must be ignored when manage_secrets=False."""
        questions = {q.name: q for q in _build()}
        q = questions["aws-client-secret"]
        self.assertTrue(
            _eval_ignore(q, FULL_ANSWERS_BYO),
            "aws-client-secret should be ignored when manage_secrets=False"
        )

    def test_client_secret_shown_when_managed(self):
        """aws-client-secret must NOT be ignored when manage_secrets=True."""
        questions = {q.name: q for q in _build()}
        q = questions["aws-client-secret"]
        self.assertFalse(
            _eval_ignore(q, FULL_ANSWERS_MANAGE),
            "aws-client-secret should NOT be ignored when manage_secrets=True"
        )

    def test_account_id_hidden_when_in_scope(self):
        questions = {q.name: q for q in _build()}
        q = questions["account_id"]
        answers = {**FULL_ANSWERS_BYO, "scope_contains": ["client_secret", "account_id"]}
        self.assertTrue(_eval_ignore(q, answers))

    def test_account_id_shown_when_not_in_scope(self):
        questions = {q.name: q for q in _build()}
        q = questions["account_id"]
        answers = {**FULL_ANSWERS_BYO, "scope_contains": ["client_secret"]}
        self.assertFalse(_eval_ignore(q, answers))

    def test_scope_contains_shown_when_byo(self):
        questions = {q.name: q for q in _build()}
        q = questions["scope_contains"]
        self.assertFalse(_eval_ignore(q, FULL_ANSWERS_BYO))

    def test_scope_contains_hidden_when_managed(self):
        questions = {q.name: q for q in _build()}
        q = questions["scope_contains"]
        self.assertTrue(_eval_ignore(q, FULL_ANSWERS_MANAGE))

    def test_azure_questions_hidden_on_aws(self):
        """All azure-* questions must be ignored on an AWS workspace."""
        questions = _build()
        azure_qs = [q for q in questions if q.name.startswith("azure-")]
        self.assertTrue(azure_qs, "No azure-* questions found")
        for q in azure_qs:
            self.assertTrue(
                _eval_ignore(q, FULL_ANSWERS_MANAGE),
                f"azure question '{q.name}' should be ignored on AWS"
            )

    def test_key_name_hidden_when_not_in_scope(self):
        """key_name__account_id must be ignored when account_id not in scope_contains."""
        questions = {q.name: q for q in _build()}
        q = questions.get("key_name__account_id")
        if q is None:
            self.skipTest("key_name__account_id not in question list (cloud filtered)")
        answers = {**FULL_ANSWERS_MANAGE, "scope_contains": ["client_secret"]}
        self.assertTrue(_eval_ignore(q, answers))

    def test_key_name_shown_when_in_scope(self):
        questions = {q.name: q for q in _build()}
        q = questions.get("key_name__account_id")
        if q is None:
            self.skipTest("key_name__account_id not in question list (cloud filtered)")
        answers = {**FULL_ANSWERS_MANAGE, "scope_contains": ["client_secret", "account_id"]}
        self.assertFalse(_eval_ignore(q, answers))

    # ---- app_config_scope visibility and default ----

    def test_app_config_scope_hidden_when_managed(self):
        """Managed installs never need this prompt; SAT uses the main scope."""
        questions = {q.name: q for q in _build()}
        q = questions["app_config_scope"]
        answers = {**FULL_ANSWERS_MANAGE, "enable_brickhound": True}
        self.assertTrue(
            _eval_ignore(q, answers),
            "app_config_scope should be hidden when manage_secrets=True"
        )

    def test_app_config_scope_shown_when_byo_with_brickhound(self):
        """BYO + BrickHound: user needs to confirm or change the scope name."""
        questions = {q.name: q for q in _build()}
        q = questions["app_config_scope"]
        answers = {**FULL_ANSWERS_BYO, "enable_brickhound": True}
        self.assertFalse(
            _eval_ignore(q, answers),
            "app_config_scope should be shown when manage_secrets=False and enable_brickhound=True"
        )

    def test_app_config_scope_hidden_when_brickhound_off(self):
        """No BrickHound deployed means no app and no scope needed."""
        questions = {q.name: q for q in _build()}
        q = questions["app_config_scope"]
        for answers in (
            {**FULL_ANSWERS_MANAGE, "enable_brickhound": False},
            {**FULL_ANSWERS_BYO,    "enable_brickhound": False},
        ):
            self.assertTrue(
                _eval_ignore(q, answers),
                "app_config_scope should be hidden when enable_brickhound=False"
            )

    def test_app_config_scope_default_blank_when_managed(self):
        """Regression guard: ignored managed questions must return '' not 'sat_app_scope'.

        ConsoleRender.render() (console/__init__.py:29-30) stores question.default
        even for ignored questions.  A static 'sat_app_scope' default would make
        managed installs create a second scope silently.
        """
        questions = {q.name: q for q in _build()}
        q = questions["app_config_scope"]
        default = _eval_default(q, {**FULL_ANSWERS_MANAGE, "enable_brickhound": True})
        self.assertEqual(
            default, "",
            f"Managed install default must be '' not {default!r}"
        )

    def test_app_config_scope_default_is_sat_app_scope_when_byo(self):
        """BYO: pre-filled value must be 'sat_app_scope' so user can accept or edit."""
        questions = {q.name: q for q in _build()}
        q = questions["app_config_scope"]
        default = _eval_default(q, {**FULL_ANSWERS_BYO, "enable_brickhound": True})
        self.assertEqual(
            default, "sat_app_scope",
            f"BYO default must be 'sat_app_scope' not {default!r}"
        )


class TestBuildSecretKeyNames(unittest.TestCase):
    """A2/B: build_secret_key_names assembles key map from checkbox answers."""

    def test_empty_scope_contains_returns_empty(self):
        answers = {**FULL_ANSWERS_MANAGE, "scope_contains": []}
        result = config.build_secret_key_names(answers, "aws")
        self.assertEqual(result, {})

    def test_locked_entry_uses_answered_key(self):
        answers = {
            **FULL_ANSWERS_MANAGE,
            "scope_contains": ["client_secret"],
            "key_name__client_secret": "my-sp-secret",
        }
        result = config.build_secret_key_names(answers, "aws")
        self.assertEqual(result["client_secret"], "my-sp-secret")

    def test_default_key_used_when_no_override(self):
        answers = {
            **FULL_ANSWERS_MANAGE,
            "scope_contains": ["client_secret"],
            # no key_name__client_secret
        }
        result = config.build_secret_key_names(answers, "aws")
        self.assertEqual(result["client_secret"], "client-secret")

    def test_multiple_selections(self):
        answers = {
            **FULL_ANSWERS_BYO,
            "scope_contains": ["client_secret", "account_id", "client_id"],
            "key_name__client_secret": "sp-secret",
            "key_name__account_id": "acct-id",
            "key_name__client_id": "sp-app-id",
        }
        result = config.build_secret_key_names(answers, "aws")
        self.assertEqual(result["client_secret"], "sp-secret")
        self.assertEqual(result["account_id"], "acct-id")
        self.assertEqual(result["client_id"], "sp-app-id")

    def test_azure_only_keys_excluded_on_aws(self):
        answers = {
            **FULL_ANSWERS_MANAGE,
            "scope_contains": ["client_secret", "tenant_id"],
        }
        result = config.build_secret_key_names(answers, "aws")
        # tenant_id is azure-only; must not appear for an AWS cloud
        self.assertNotIn("tenant_id", result)

    def test_azure_only_keys_included_on_azure(self):
        answers = {
            **FULL_ANSWERS_MANAGE,
            "scope_contains": ["client_secret", "tenant_id", "subscription_id"],
            "key_name__tenant_id": "my-tenant",
            "key_name__subscription_id": "my-sub",
        }
        result = config.build_secret_key_names(answers, "azure")
        self.assertEqual(result["tenant_id"], "my-tenant")
        self.assertEqual(result["subscription_id"], "my-sub")


class TestAnalysisSchemaDeferral(unittest.TestCase):
    """analysis_schema_name in scope_contains suppresses catalog/schema prompts
    and prevents ensure_app_config_secrets from writing to the scope.
    """

    def test_analysis_schema_name_in_checkbox_choices(self):
        """analysis_schema_name must appear as a deferrable option."""
        questions = _build()
        cb = next(q for q in questions if q.name == "scope_contains")
        # choices is list of (label, logical) tuples
        logicals = [v for _, v in (cb.choices or [])]
        self.assertIn(
            "analysis_schema_name", logicals,
            "analysis_schema_name must be a checkbox option so users can defer it"
        )

    def test_catalog_hidden_when_schema_deferred(self):
        questions = {q.name: q for q in _build()}
        q = questions["catalog"]
        answers = {**FULL_ANSWERS_BYO, "scope_contains": ["client_secret", "analysis_schema_name"]}
        self.assertTrue(
            _eval_ignore(q, answers),
            "catalog prompt should be hidden when analysis_schema_name is deferred"
        )

    def test_catalog_shown_when_schema_not_deferred(self):
        questions = {q.name: q for q in _build()}
        q = questions["catalog"]
        answers = {**FULL_ANSWERS_BYO, "scope_contains": ["client_secret"]}
        self.assertFalse(
            _eval_ignore(q, answers),
            "catalog prompt should be shown when analysis_schema_name is not deferred"
        )

    def test_schema_prompt_hidden_when_deferred(self):
        questions = {q.name: q for q in _build()}
        q = questions["security_analysis_schema"]
        answers = {**FULL_ANSWERS_BYO, "scope_contains": ["client_secret", "analysis_schema_name"]}
        self.assertTrue(_eval_ignore(q, answers))

    def test_schema_prompt_shown_when_not_deferred(self):
        questions = {q.name: q for q in _build()}
        q = questions["security_analysis_schema"]
        answers = {**FULL_ANSWERS_MANAGE, "scope_contains": []}
        self.assertFalse(_eval_ignore(q, answers))

    def test_resolve_app_config_scope_schema_deferred_returns_credential_scope(self):
        """When analysis_schema_name is in scope_contains the app binds to the
        credential scope directly — no sat_app_scope created.
        """
        answers = {
            "app_config_scope": "",
            "scope_contains": ["client_secret", "analysis_schema_name"],
        }
        result = config._resolve_app_config_scope(answers, "my-vault-scope", manage_secrets=False)
        self.assertEqual(
            result, "my-vault-scope",
            "Should return the credential scope, not sat_app_scope"
        )

    def test_resolve_app_config_scope_schema_not_deferred_byo_returns_sat_app_scope(self):
        """When analysis_schema_name is NOT deferred and manage_secrets=False,
        sat_app_scope is still the fallback."""
        answers = {
            "app_config_scope": "",
            "scope_contains": ["client_secret"],
        }
        result = config._resolve_app_config_scope(answers, "my-vault-scope", manage_secrets=False)
        self.assertEqual(result, "sat_app_scope")

    def test_ensure_app_config_skips_write_when_schema_deferred(self):
        """ensure_app_config_secrets must not call put_secret when
        analysis_schema_name is in scope_contains."""
        client = MagicMock()
        client.secrets.list_scopes.return_value = []
        answers = {
            **FULL_ANSWERS_BYO,
            "enable_brickhound": True,
            "scope_contains": ["client_secret", "analysis_schema_name"],
        }
        config.ensure_app_config_secrets(
            client, answers, "my-vault-scope", False, {}, set()
        )
        client.secrets.put_secret.assert_not_called()
        client.secrets.create_scope.assert_not_called()

    def test_ensure_app_config_writes_when_schema_not_deferred(self):
        """ensure_app_config_secrets must write when analysis_schema_name
        is not in scope_contains."""
        client = MagicMock()
        answers = {
            **FULL_ANSWERS_MANAGE,
            "enable_brickhound": True,
            "scope_contains": ["client_secret"],
            "catalog": "main",
            "security_analysis_schema": "security_analysis",
        }
        existing = {"sat_scope"}
        config.ensure_app_config_secrets(
            client, answers, "sat_scope", True, {}, existing
        )
        client.secrets.put_secret.assert_called_once()
        call_kwargs = client.secrets.put_secret.call_args
        self.assertEqual(call_kwargs.kwargs.get("key") or call_kwargs[1].get("key"),
                         "analysis_schema_name")


class TestResolveKeyOverrides(unittest.TestCase):
    """_resolve_key_overrides: blank / structured / JSON / bad."""

    def test_blank_returns_empty(self):
        self.assertEqual(config._resolve_key_overrides({"secret_key_names": ""}), {})

    def test_missing_key_returns_empty(self):
        self.assertEqual(config._resolve_key_overrides({}), {})

    def test_structured_dict_wins(self):
        answers = {
            "secret_key_names_dict": {"client_secret": "my-secret"},
            "secret_key_names": '{"client_secret": "wrong"}',
        }
        self.assertEqual(
            config._resolve_key_overrides(answers),
            {"client_secret": "my-secret"}
        )

    def test_legacy_json_string_parsed(self):
        answers = {"secret_key_names": '{"client_secret": "my-sp-secret"}'}
        self.assertEqual(
            config._resolve_key_overrides(answers),
            {"client_secret": "my-sp-secret"}
        )

    def test_invalid_json_returns_empty(self):
        self.assertEqual(
            config._resolve_key_overrides({"secret_key_names": "not-json"}),
            {}
        )


class TestResolveAppConfigScope(unittest.TestCase):

    def _a(self, app_config_scope=""):
        return {"app_config_scope": app_config_scope}

    def test_explicit_name_wins(self):
        self.assertEqual(
            config._resolve_app_config_scope(self._a("my-app-scope"), "sat_scope", False),
            "my-app-scope",
        )

    def test_manage_true_falls_back_to_main_scope(self):
        self.assertEqual(
            config._resolve_app_config_scope(self._a(), "sat_scope", True),
            "sat_scope",
        )

    def test_manage_false_falls_back_to_sat_app_scope(self):
        self.assertEqual(
            config._resolve_app_config_scope(self._a(), "sat_scope", False),
            "sat_app_scope",
        )


class TestValidateSecrets(unittest.TestCase):
    """A4: validate_secrets uses scope= key= signature; reports all missing at once."""

    def _make_client(self, secret_value="s3cr3t", scope_names=None):
        client = MagicMock()
        scope = MagicMock()
        scope.name = scope_names[0] if scope_names else "my-scope"
        client.secrets.list_scopes.return_value = [scope]
        secret_resp = MagicMock()
        secret_resp.value = secret_value
        client.secrets.get_secret.return_value = secret_resp
        return client

    def _byo_answers(self, scope="my-scope", key="client-secret", scope_contains=None):
        return {
            "secret_scope": scope,
            "secret_key_names_dict": (
                {"client_secret": key} if key != "client-secret" else {}
            ),
            "scope_contains": scope_contains or ["client_secret"],
            "enable_brickhound": False,
        }

    def test_uses_scope_and_key_kwargs(self):
        """Must call get_secret(scope=..., key=...) not get_secret(path=...)."""
        client = self._make_client()
        config.validate_secrets(client, self._byo_answers(), "aws")
        client.secrets.get_secret.assert_called_once_with(
            scope="my-scope", key="client-secret"
        )

    def test_key_override_respected(self):
        client = self._make_client()
        config.validate_secrets(
            client, self._byo_answers(key="my-custom-key"), "aws"
        )
        client.secrets.get_secret.assert_called_once_with(
            scope="my-scope", key="my-custom-key"
        )

    def test_missing_scope_raises(self):
        client = MagicMock()
        client.secrets.list_scopes.return_value = []
        with self.assertRaises(ValueError) as ctx:
            config.validate_secrets(
                client, self._byo_answers(scope="nonexistent"), "aws"
            )
        self.assertIn("nonexistent", str(ctx.exception))

    def test_missing_secret_raises(self):
        client = self._make_client()
        client.secrets.get_secret.side_effect = Exception("secret not found")
        with self.assertRaises(ValueError) as ctx:
            config.validate_secrets(client, self._byo_answers(), "aws")
        self.assertIn("client_secret", str(ctx.exception))

    def test_reports_all_missing_at_once(self):
        """Both missing keys must appear in a single error message."""
        client = MagicMock()
        scope = MagicMock(); scope.name = "my-scope"
        client.secrets.list_scopes.return_value = [scope]
        client.secrets.get_secret.side_effect = Exception("not found")

        answers = self._byo_answers(
            scope_contains=["client_secret", "account_id"]
        )
        with self.assertRaises(ValueError) as ctx:
            config.validate_secrets(client, answers, "aws")
        msg = str(ctx.exception)
        self.assertIn("client_secret", msg)
        self.assertIn("account_id", msg)

    def test_empty_scope_contains_still_validates_client_secret(self):
        """scope_contains=[] is treated as ['client_secret'] because client_secret
        is locked — it is always in the scope on the BYO path.  validate_secrets
        must still check it is readable even when the list is otherwise empty."""
        client = self._make_client()
        answers = self._byo_answers(scope_contains=[])
        # scope_contains=[] → resolves to ["client_secret"] via `or` default
        config.validate_secrets(client, answers, "aws")
        client.secrets.get_secret.assert_called_once_with(
            scope="my-scope", key="client-secret"
        )


class TestPromptFlowSimulation(unittest.TestCase):
    """Simulate the actual inquirer render loop to catch wiring bugs.

    Previous crashes were caused by unit-testing pure helper functions with
    synthetic inputs that couldn't occur in the real flow.  This class models
    what ConsoleRender.render() actually does:

        if question.ignore:
            answers[q.name] = question.default  # stored even when hidden
        else:
            answers[q.name] = user_input        # or default if user presses Enter

    For each scenario the "user" accepts every pre-filled default (presses Enter
    on every shown prompt), mirroring the exact behaviour that caused the
    sat_app_scope 404 crash.

    The key assertion in every case: the final _resolve_app_config_scope()
    output must be a scope that SAT actually wrote to or that the user pre-populated
    — never a scope that was neither created nor written.
    """

    # Warehouse sentinel — all scenarios have a warehouse.
    _WH = {"id": "abcd1234abcd1234", "name": "SAT WH"}

    def _simulate(self, user_inputs: dict) -> dict:
        """Walk build_questions() in order, populating answers the way
        inquirer does: store default for hidden questions, user_input for shown.

        user_inputs: {question_name: value} for questions where the simulated
        user would type something other than the default.  Every other shown
        question resolves to its default.
        """
        questions = _build()
        answers = {}
        for q in questions:
            ignored = _eval_ignore(q, answers)
            default = _eval_default(q, answers)
            if ignored:
                # inquirer stores the default even for ignored questions.
                answers[q.name] = default
            elif q.name in user_inputs:
                answers[q.name] = user_inputs[q.name]
            else:
                # User pressed Enter — accept the pre-filled default.
                answers[q.name] = default if default is not None else ""
        return answers

    # -----------------------------------------------------------------------
    # Scenario 1: managed install, press Enter on everything
    # -----------------------------------------------------------------------
    def test_managed_install_accept_all_defaults(self):
        """Regression: app_config_scope default must be '' for managed installs
        so _resolve_app_config_scope returns the main scope, not sat_app_scope."""
        answers = self._simulate({
            "account_id": "12345678-1234-1234-1234-123456789abc",
            "catalog": "main",
            "warehouse": self._WH,
            "aws-client-id": "sp-client-id",
            "aws-client-secret": "sp-secret",
        })
        scope = config._resolve_app_config_scope(answers, "sat_scope", True)
        self.assertEqual(scope, "sat_scope",
                         "Managed install must use main scope, not sat_app_scope")

    # -----------------------------------------------------------------------
    # Scenario 2: BYO scope, no BrickHound
    # -----------------------------------------------------------------------
    def test_byo_no_brickhound_no_app_scope_prompt(self):
        """No BrickHound → app_config_scope prompt hidden → scope irrelevant."""
        answers = self._simulate({
            "account_id": "12345678-1234-1234-1234-123456789abc",
            "catalog": "main",
            "warehouse": self._WH,
            "secret_scope": "key-vault-secrets",
            "manage_secrets": False,
            "scope_contains": ["client_secret"],
            "enable_brickhound": False,
        })
        # prompt must be hidden
        q = {q.name: q for q in _build()}["app_config_scope"]
        self.assertTrue(_eval_ignore(q, answers))

    # -----------------------------------------------------------------------
    # Scenario 3: BYO scope, analysis_schema_name deferred, user presses Enter
    # (THE CRASH SCENARIO — user accepted the pre-filled "sat_app_scope" default)
    # -----------------------------------------------------------------------
    def test_byo_schema_deferred_enter_on_prompt_gives_credential_scope(self):
        """When analysis_schema_name is in scope_contains the prompt must be
        hidden — pressing Enter must not route the app binding to sat_app_scope."""
        answers = self._simulate({
            "account_id": "12345678-1234-1234-1234-123456789abc",
            "catalog": "main",          # skipped by ignore but kept in inputs
            "warehouse": self._WH,
            "secret_scope": "key-vault-secrets",
            "manage_secrets": False,
            "scope_contains": ["client_secret", "analysis_schema_name"],
            "key_name__analysis_schema_name": "sat-analysis-schema-name",
            "enable_brickhound": True,
            # Deliberately do NOT supply app_config_scope — the simulation
            # will store the default the same way inquirer does.
        })
        # 1. The prompt must be hidden.
        q = {q.name: q for q in _build()}["app_config_scope"]
        self.assertTrue(
            _eval_ignore(q, answers),
            "app_config_scope prompt must be hidden when schema is deferred"
        )
        # 2. The stored default must be blank (not "sat_app_scope").
        self.assertEqual(
            answers.get("app_config_scope"), "",
            f"app_config_scope stored as {answers.get('app_config_scope')!r}; "
            f"must be '' when prompt is hidden"
        )
        # 3. The resolved scope must be the credential scope, not sat_app_scope.
        scope = config._resolve_app_config_scope(answers, "key-vault-secrets", False)
        self.assertEqual(
            scope, "key-vault-secrets",
            f"App should bind to credential scope; got {scope!r}"
        )
        # 4. ensure_app_config_secrets must not write or create anything.
        client = MagicMock()
        config.ensure_app_config_secrets(
            client, answers, "key-vault-secrets", False, {}, {"key-vault-secrets"}
        )
        client.secrets.put_secret.assert_not_called()
        client.secrets.create_scope.assert_not_called()

    # -----------------------------------------------------------------------
    # Scenario 4: BYO scope, schema NOT deferred, user accepts sat_app_scope
    # -----------------------------------------------------------------------
    def test_byo_schema_not_deferred_enter_gives_sat_app_scope(self):
        """When schema is not deferred, sat_app_scope must be both shown and
        used as the write target — the scope SAT creates."""
        answers = self._simulate({
            "account_id": "12345678-1234-1234-1234-123456789abc",
            "catalog": "main",
            "security_analysis_schema": "security_analysis",
            "warehouse": self._WH,
            "secret_scope": "key-vault-secrets",
            "manage_secrets": False,
            "scope_contains": ["client_secret"],  # schema NOT deferred
            "enable_brickhound": True,
            # Accept the pre-filled default for app_config_scope.
        })
        # 1. Prompt must be shown.
        q = {q.name: q for q in _build()}["app_config_scope"]
        self.assertFalse(
            _eval_ignore(q, answers),
            "app_config_scope prompt must be shown when schema is not deferred"
        )
        # 2. The resolved scope must be sat_app_scope (user pressed Enter).
        scope = config._resolve_app_config_scope(answers, "key-vault-secrets", False)
        self.assertEqual(scope, "sat_app_scope")

    # -----------------------------------------------------------------------
    # Scenario 5: BYO scope, schema NOT deferred, user types custom scope
    # -----------------------------------------------------------------------
    def test_byo_schema_not_deferred_custom_scope_respected(self):
        """Explicit non-default app_config_scope must be honoured."""
        answers = self._simulate({
            "account_id": "12345678-1234-1234-1234-123456789abc",
            "catalog": "main",
            "security_analysis_schema": "security_analysis",
            "warehouse": self._WH,
            "secret_scope": "key-vault-secrets",
            "manage_secrets": False,
            "scope_contains": ["client_secret"],
            "enable_brickhound": True,
            "app_config_scope": "my-app-config-scope",
        })
        scope = config._resolve_app_config_scope(answers, "key-vault-secrets", False)
        self.assertEqual(scope, "my-app-config-scope")


if __name__ == "__main__":
    unittest.main()
