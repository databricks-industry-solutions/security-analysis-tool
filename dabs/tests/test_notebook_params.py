"""
Drift guards for SAT notebook parameter forwarding.

These tests run offline (no Databricks workspace needed) and catch two
classes of bug that have each shipped once:

1. A widget added to initialize.py without a matching key in SAT_CHILD_PARAMS
   → child notebooks spawned via dbutils.notebook.run() silently miss the value.

2. A base_parameters block in a DABS .yml.tmpl that is missing one or more of
   the 10 required SAT widget names → the child's initialize.py falls back to
   scope reads that fail for installs where values travel as job parameters.
"""
import re
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent  # repo root


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read(rel: str) -> str:
    return (_ROOT / rel).read_text()


def _widget_names_from_initialize() -> set:
    """Extract every name declared by dbutils.widgets.text("name", ...) in initialize.py."""
    src = _read("notebooks/Utils/initialize.py")
    return set(re.findall(r'dbutils\.widgets\.text\(\s*["\']([^"\']+)["\']', src))


def _child_param_keys_from_initialize() -> set:
    """Extract the dict keys declared in SAT_CHILD_PARAMS = { ... }.

    Uses a simple brace-counter rather than [^}]+ to handle nested braces
    in values like json.dumps(...) if _key_overrides else "{}".
    """
    src = _read("notebooks/Utils/initialize.py")
    start = src.find("SAT_CHILD_PARAMS")
    if start == -1:
        return set()
    brace_start = src.find("{", start)
    if brace_start == -1:
        return set()
    depth, i = 0, brace_start
    while i < len(src):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    block_text = src[brace_start + 1:i]
    return set(re.findall(r'"([^"]+)"\s*:', block_text))


def _base_param_keys_from_tmpl(path: str) -> list[set]:
    """Return a list of key-sets, one per base_parameters block in the file."""
    src = _read(path)
    blocks = []
    # Split on base_parameters: then grab all key: value lines until a blank line
    for match in re.finditer(r'base_parameters:\s*\n((?:[ \t]+\S[^\n]*\n)+)', src):
        block_text = match.group(1)
        keys = set(re.findall(r'[ \t]+([a-zA-Z_][a-zA-Z0-9_]*)\s*:', block_text))
        blocks.append(keys)
    return blocks


# The 10 SAT widget names that every notebook_task's base_parameters must include.
# Derived from the dbutils.widgets.text() declarations in initialize.py rather than
# hardcoded so the test stays in sync automatically.
_REQUIRED_PARAMS = frozenset({
    "secret_scope",
    "secret_key_names",
    "account_id_param",
    "client_id_param",
    "tenant_id_param",
    "subscription_id_param",
    "sql_warehouse_id_param",
    "analysis_schema_name_param",
    "proxies_param",
    "use_sp_auth_param",
})

# DABS .yml.tmpl files that contain notebook_task blocks
_TMPL_FILES = [
    "dabs/dabs_template/template/tmp/resources/sat_initiliazer_job.yml.tmpl",
    "dabs/dabs_template/template/tmp/resources/sat_driver_job.yml.tmpl",
    "dabs/dabs_template/template/tmp/resources/sat_secrets_scanner_job.yml.tmpl",
    "dabs/dabs_template/template/tmp/resources/brickhound_job.yml.tmpl",
]


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestSatChildParamsCoversAllWidgets(unittest.TestCase):
    """Every widget declared in initialize.py must have a matching key in
    SAT_CHILD_PARAMS, otherwise child notebooks spawned via
    dbutils.notebook.run() silently miss the value.
    """

    def test_child_params_covers_all_widgets(self):
        widgets = _widget_names_from_initialize()
        self.assertTrue(widgets, "No widgets found in initialize.py — regex broken?")

        child_keys = _child_param_keys_from_initialize()
        self.assertTrue(child_keys, "SAT_CHILD_PARAMS not found in initialize.py")

        missing = widgets - child_keys
        self.assertFalse(
            missing,
            f"Widgets declared in initialize.py but missing from SAT_CHILD_PARAMS:\n"
            + "\n".join(f"  {k}" for k in sorted(missing))
            + "\nAdd them so child notebooks receive the value."
        )

    def test_no_extra_unknown_keys_in_child_params(self):
        """SAT_CHILD_PARAMS should not contain keys that aren't widget names
        (guards against typos in the key names)."""
        widgets = _widget_names_from_initialize()
        child_keys = _child_param_keys_from_initialize()
        extra = child_keys - widgets
        self.assertFalse(
            extra,
            f"Keys in SAT_CHILD_PARAMS that are not widget names in initialize.py:\n"
            + "\n".join(f"  {k}" for k in sorted(extra))
            + "\nEither add the widget or remove the key."
        )


class TestRunNotebookForwardsChildParams(unittest.TestCase):
    """security_analysis_initializer.py's run_notebook() must reference
    SAT_CHILD_PARAMS so children receive the full widget context.
    """

    def test_run_notebook_passes_sat_child_params(self):
        src = _read("notebooks/security_analysis_initializer.py")
        # Find the run_notebook function body
        fn = re.search(
            r'def run_notebook\(.*?\):(.*?)(?=\ndef |\Z)', src, re.DOTALL
        )
        self.assertIsNotNone(fn, "run_notebook function not found")
        body = fn.group(1)
        self.assertIn(
            "SAT_CHILD_PARAMS", body,
            "run_notebook() must pass SAT_CHILD_PARAMS to dbutils.notebook.run(). "
            "Without it, child notebooks' initialize.py falls back to scope reads "
            "that fail for installs where values travel as job parameters."
        )


class TestAllTmplTasksHaveFullParamSet(unittest.TestCase):
    """Every base_parameters block in every DABS .yml.tmpl must contain all
    10 required SAT widget names.  Task-specific extras are allowed.
    """

    def test_required_widget_names_consistent_with_initialize(self):
        """The _REQUIRED_PARAMS constant in this test must match the actual
        widget names in initialize.py."""
        widgets = _widget_names_from_initialize()
        missing_from_test = widgets - _REQUIRED_PARAMS
        self.assertFalse(
            missing_from_test,
            f"Widgets in initialize.py not in _REQUIRED_PARAMS test constant:\n"
            + "\n".join(f"  {k}" for k in sorted(missing_from_test))
            + "\nUpdate _REQUIRED_PARAMS in this test file."
        )

    def test_all_notebook_tasks_pass_full_param_set(self):
        failures = []
        for tmpl in _TMPL_FILES:
            blocks = _base_param_keys_from_tmpl(tmpl)
            if not blocks:
                failures.append(f"{tmpl}: no base_parameters blocks found")
                continue
            for i, keys in enumerate(blocks):
                missing = _REQUIRED_PARAMS - keys
                if missing:
                    failures.append(
                        f"{tmpl} block #{i+1} missing: {', '.join(sorted(missing))}"
                    )
        self.assertFalse(
            failures,
            "base_parameters blocks missing required SAT widget names:\n"
            + "\n".join(f"  {f}" for f in failures)
            + "\nEvery notebook_task must forward all SAT widget names so "
            "initialize.py can populate its widgets in the child context."
        )


if __name__ == "__main__":
    unittest.main()
