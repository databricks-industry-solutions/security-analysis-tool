# Databricks notebook source
# MAGIC %md
# MAGIC # Code Security Scanner
# MAGIC
# MAGIC Scans workspace notebooks and files for insecure code patterns (Semgrep) and
# MAGIC for known vulnerabilities in the packages they declare (Trivy). Results are
# MAGIC written to `code_scan_findings` and surfaced under Code Security in the SAT app.

# COMMAND ----------

# MAGIC %run ./diagnosis/pre_run_config_check

# COMMAND ----------

# MAGIC %run ./Includes/install_sat_sdk

# COMMAND ----------

# MAGIC %run ./Utils/initialize

# COMMAND ----------

# MAGIC %run ./Utils/common

# COMMAND ----------

# MAGIC %pip install semgrep==1.173.0 --quiet

# COMMAND ----------

import base64
import concurrent.futures
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("sat.code_scan")

SCANNER_DIR = f"{basePath()}/notebooks/Includes/scan_code"
sys.path.insert(0, SCANNER_DIR.replace("/Workspace", "/Workspace", 1))

from dependencies import (  # noqa: E402
    Dependencies,
    from_jobs,
    from_notebook_source,
    from_requirements_file,
)
from runners import (  # noqa: E402
    TRIVY_BINARY,
    TRIVY_CACHE_ENV,
    Finding,
    SemgrepRunner,
    TrivyRunner,
)

# COMMAND ----------

hostname = (
    dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().getOrElse(None)
)
token = (
    dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().getOrElse(None)
)
cloud_type = getCloudType(hostname)
json_.update({"url": hostname, "cloud_type": cloud_type})

SCHEMA = json_["analysis_schema_name"]
FINDINGS_TABLE = f"{SCHEMA}.code_scan_findings"
RUNS_TABLE = f"{SCHEMA}.code_scan_runs"

RULES_PATH = f"/Workspace{SCANNER_DIR}/rules/databricks-notebooks.yaml".replace(
    "/Workspace/Workspace", "/Workspace"
)

MAX_WORKERS = 16
EXPORT_BATCH = 200
SCANNABLE_SUFFIXES = (".py", ".sql", ".r", ".scala", ".sh", ".yaml", ".yml", ".json")
DISCOVERY_ROOTS = ("/Users", "/Shared", "/Repos", "/Workspace/Users", "/Workspace/Shared")

# COMMAND ----------

# MAGIC %md ## Table setup

# COMMAND ----------


def create_tables() -> None:
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {FINDINGS_TABLE} (
          run_id BIGINT,
          workspace_id STRING,
          scanner STRING,
          rule_id STRING,
          severity STRING,
          title STRING,
          description STRING,
          object_path STRING,
          line_start INT,
          package_name STRING,
          installed_version STRING,
          fixed_version STRING,
          reference_url STRING,
          fingerprint STRING,
          scan_time TIMESTAMP
        ) USING DELTA
    """)
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {RUNS_TABLE} (
          run_id BIGINT,
          workspace_id STRING,
          started_at TIMESTAMP,
          finished_at TIMESTAMP,
          objects_scanned INT,
          findings_written INT,
          pinned_packages INT,
          unpinned_packages INT,
          semgrep_status STRING,
          trivy_status STRING,
          notes STRING
        ) USING DELTA
    """)


def generate_run_id() -> int:
    spark.sql(f"INSERT INTO {SCHEMA}.run_number_table (check_time) VALUES (current_timestamp())")
    row = spark.sql(f"SELECT max(runID) AS run_id FROM {SCHEMA}.run_number_table").collect()
    return row[0]["run_id"]


# COMMAND ----------

# MAGIC %md ## Tool bootstrap

# COMMAND ----------


def install_trivy() -> str:
    """Install the Trivy binary and point its cache at a persistent volume.

    Returns a status string recorded on the run. Trivy needs an external download
    for both the binary and its vulnerability database, so on a workspace with
    serverless egress controls this is the step that fails; the failure is
    reported rather than silently producing zero dependency findings.
    """
    if os.path.isfile(TRIVY_BINARY):
        return "ready"

    version = "0.70.0"
    url = (f"https://github.com/aquasecurity/trivy/releases/download/v{version}"
           f"/trivy_{version}_Linux-64bit.tar.gz")
    os.makedirs("/tmp/bin", exist_ok=True)
    try:
        subprocess.run(["bash", "-lc", f"curl -sSfL {url} | tar xz -C /tmp/bin trivy"],
                       check=True, capture_output=True, timeout=600)
        os.chmod(TRIVY_BINARY, 0o755)
    except subprocess.SubprocessError as exc:
        detail = getattr(exc, "stderr", b"") or b""
        return (f"unavailable: could not download the Trivy binary from github.com "
                f"({detail.decode()[:200].strip()})")

    cache_dir = f"/Volumes/{SCHEMA.replace('`', '').replace('.', '/')}/scanner_cache/trivy"
    try:
        os.makedirs(cache_dir, exist_ok=True)
        os.environ[TRIVY_CACHE_ENV] = cache_dir
    except OSError:
        log.info("volume cache unavailable; using the task-local Trivy cache")
    return "ready"


# COMMAND ----------

# MAGIC %md ## Discovery and export

# COMMAND ----------


def _api(path: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        response = requests.get(
            f"{hostname}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=60,
        )
        if response.status_code == 200:
            return response.json()
    except requests.RequestException as exc:
        log.debug("%s failed: %s", path, exc)
    return None


def _list_dir(path: str) -> List[Dict[str, Any]]:
    payload = _api("/api/2.0/workspace/list", {"path": path})
    return (payload or {}).get("objects", []) or []


def discover_objects() -> List[Dict[str, Any]]:
    """Every notebook and scannable file in the workspace.

    Traversal is fanned out one directory level at a time; recursing serially
    times out on workspaces with thousands of notebooks.
    """
    leaves: List[Dict[str, Any]] = []
    seen_dirs: set[str] = set()
    pending = [root for root in DISCOVERY_ROOTS]

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        while pending:
            batch = [p for p in pending if p not in seen_dirs]
            seen_dirs.update(batch)
            pending = []
            for objects in pool.map(_list_dir, batch):
                for obj in objects:
                    path = obj.get("path")
                    if not path:
                        continue
                    kind = obj.get("object_type")
                    if kind in ("DIRECTORY", "REPO"):
                        pending.append(path)
                    elif kind == "NOTEBOOK":
                        leaves.append(obj)
                    elif kind == "FILE" and path.lower().endswith(SCANNABLE_SUFFIXES):
                        leaves.append(obj)

    unique = {obj["path"]: obj for obj in leaves}
    return list(unique.values())


def export_source(path: str) -> Optional[str]:
    payload = _api("/api/2.0/workspace/export", {"path": path, "format": "SOURCE"})
    if not payload or "content" not in payload:
        return None
    try:
        return base64.b64decode(payload["content"]).decode("utf-8", errors="replace")
    except (ValueError, TypeError):
        return None


# COMMAND ----------

# MAGIC %md ## Scan

# COMMAND ----------


def scan_workspace(workspace_id: str, run_id: int) -> Dict[str, Any]:
    started = datetime.now(timezone.utc)
    create_tables()

    semgrep = SemgrepRunner(RULES_PATH)
    trivy = TrivyRunner()

    semgrep_status = "ready"
    if not semgrep.is_available():
        semgrep_status = "unavailable: semgrep is not installed on this compute"
    else:
        try:
            semgrep.validate_rules()
        except RuntimeError as exc:
            semgrep_status = f"unavailable: {exc}"

    trivy_status = install_trivy()
    if trivy_status == "ready" and not trivy.is_available():
        trivy_status = "unavailable: the Trivy binary is not executable"

    objects = discover_objects()
    log.info("discovered %d scannable objects", len(objects))

    deps = Dependencies()
    findings: List[Finding] = []
    scanned = 0

    for start in range(0, len(objects), EXPORT_BATCH):
        batch = objects[start:start + EXPORT_BATCH]
        scan_dir = tempfile.mkdtemp(prefix="sat_code_")
        path_map: Dict[str, str] = {}
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
                sources = list(pool.map(lambda o: export_source(o["path"]), batch))

            for obj, source in zip(batch, sources):
                if source is None:
                    continue
                scanned += 1
                workspace_path = obj["path"]
                from_notebook_source(source, workspace_path, deps)
                if workspace_path.lower().endswith("requirements.txt"):
                    from_requirements_file(source, workspace_path, deps)

                local = os.path.join(scan_dir, f"{scanned}.py")
                with open(local, "w", encoding="utf-8") as handle:
                    handle.write(source)
                path_map[local] = workspace_path

            if semgrep_status == "ready" and path_map:
                try:
                    findings.extend(semgrep.run(scan_dir, path_map))
                except (RuntimeError, subprocess.SubprocessError, ValueError) as exc:
                    semgrep_status = f"failed: {str(exc)[:200]}"
                    log.warning("semgrep batch failed: %s", exc)
        finally:
            shutil.rmtree(scan_dir, ignore_errors=True)

    try:
        from_jobs(WorkspaceClient(), deps)
    except Exception as exc:  # noqa: BLE001 - job listing is supplementary
        log.info("could not read job libraries: %s", exc)

    if trivy_status == "ready":
        if deps.is_empty:
            trivy_status = "no pinned dependencies found to scan"
        else:
            manifest_dir = tempfile.mkdtemp(prefix="sat_deps_")
            try:
                with open(os.path.join(manifest_dir, "requirements.txt"), "w") as handle:
                    handle.write(deps.requirements_txt())
                dependency_findings = trivy.run(manifest_dir)
                # Trivy reports the manifest it read, which is a temporary file.
                # Re-point each finding at the notebook or job that declared the
                # package, so the result names something the reader can act on.
                for finding in dependency_findings:
                    key = f"{finding.package_name}=={finding.installed_version}"
                    finding.object_path = deps.sources.get(key, finding.object_path)
                findings.extend(dependency_findings)
            except (RuntimeError, subprocess.SubprocessError, ValueError) as exc:
                trivy_status = f"failed: {str(exc)[:200]}"
                log.warning("trivy failed: %s", exc)
            finally:
                shutil.rmtree(manifest_dir, ignore_errors=True)

    written = write_findings(workspace_id, run_id, findings)
    finished = datetime.now(timezone.utc)

    notes = ""
    if deps.unpinned:
        notes = (f"{len(deps.unpinned)} package(s) are declared without an exact "
                 f"version and cannot be checked for vulnerabilities: "
                 f"{', '.join(sorted(deps.unpinned)[:10])}")

    record_run(run_id, workspace_id, started, finished, scanned, written,
               len(deps.pinned), len(deps.unpinned), semgrep_status, trivy_status, notes)

    return {
        "run_id": run_id,
        "objects_scanned": scanned,
        "findings": written,
        "semgrep": semgrep_status,
        "trivy": trivy_status,
    }


def write_findings(workspace_id: str, run_id: int, findings: List[Finding]) -> int:
    """Write findings in one statement per batch.

    A statement per finding is the difference between a scan that completes and
    one that is still running hours later; on serverless each statement costs
    several seconds regardless of how little it writes.
    """
    if not findings:
        return 0

    def literal(value: Any) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, int):
            return str(value)
        # Rule messages and CVE descriptions contain quotes and newlines. Quotes
        # are doubled per SQL string rules; newlines are collapsed so a value
        # cannot break the single-statement INSERT this batches into.
        text = " ".join(str(value).split())
        return "'" + text.replace("'", "''") + "'"

    written = 0
    for start in range(0, len(findings), 500):
        rows = []
        for finding in findings[start:start + 500]:
            rows.append(
                "(" + ", ".join([
                    str(run_id),
                    literal(workspace_id),
                    literal(finding.scanner),
                    literal(finding.rule_id),
                    literal(finding.severity),
                    literal(finding.title[:500]),
                    literal(finding.description[:2000]),
                    literal(finding.object_path),
                    literal(finding.line_start),
                    literal(finding.package_name),
                    literal(finding.installed_version),
                    literal(finding.fixed_version),
                    literal(finding.reference_url),
                    literal(finding.fingerprint),
                    f"cast('{finding.detected_at.isoformat()}' as timestamp)",
                ]) + ")"
            )
        spark.sql(f"INSERT INTO {FINDINGS_TABLE} VALUES {', '.join(rows)}")
        written += len(rows)
    return written


def record_run(run_id, workspace_id, started, finished, scanned, written,
               pinned, unpinned, semgrep_status, trivy_status, notes) -> None:
    def literal(value: str) -> str:
        return "'" + str(value).replace("'", "''") + "'"

    spark.sql(f"""
        INSERT INTO {RUNS_TABLE} VALUES (
          {run_id}, {literal(workspace_id)},
          cast('{started.isoformat()}' as timestamp),
          cast('{finished.isoformat()}' as timestamp),
          {scanned}, {written}, {pinned}, {unpinned},
          {literal(semgrep_status)}, {literal(trivy_status)}, {literal(notes)}
        )
    """)


# COMMAND ----------

# MAGIC %md ## Run

# COMMAND ----------

from databricks.sdk import WorkspaceClient  # noqa: E402

workspace_id = str(WorkspaceClient().get_workspace_id())
run_id = generate_run_id()

result = scan_workspace(workspace_id, run_id)

print(f"Run {result['run_id']}")
print(f"  objects scanned : {result['objects_scanned']}")
print(f"  findings written: {result['findings']}")
print(f"  semgrep         : {result['semgrep']}")
print(f"  trivy           : {result['trivy']}")

if result["semgrep"].startswith(("unavailable", "failed")) and \
        result["trivy"].startswith(("unavailable", "failed")):
    raise RuntimeError(
        "Both scanners were unavailable, so this run proves nothing about the "
        f"security of workspace code. Semgrep: {result['semgrep']}. "
        f"Trivy: {result['trivy']}."
    )

dbutils.notebook.exit(json.dumps(result))
