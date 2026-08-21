"""Scanner runners for workspace code.

Two tools with no overlap. Semgrep finds flaws in code written in this workspace;
Trivy finds published CVEs in the packages that code depends on. Neither can find
what the other finds, so a finding from either is reported under its own scanner
name.

Both are invoked as subprocesses against a local directory, so the same code runs
on serverless and on a classic cluster.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256

log = logging.getLogger("sat.code_scan")

SEMGREP_TIMEOUT_SECONDS = 1800
TRIVY_TIMEOUT_SECONDS = 900
TRIVY_BINARY = "/tmp/bin/trivy"

# Trivy caches its vulnerability database here. Pointing it at a Unity Catalog
# volume keeps the ~600 MB download to once per day rather than once per task.
TRIVY_CACHE_ENV = "SAT_TRIVY_CACHE_DIR"

_SEMGREP_SEVERITY = {"ERROR": "HIGH", "WARNING": "MEDIUM", "INFO": "LOW"}


@dataclass
class Finding:
    """One security finding, from either scanner."""

    scanner: str
    rule_id: str
    severity: str
    title: str
    description: str
    object_path: str
    line_start: int | None = None
    package_name: str = ""
    installed_version: str = ""
    fixed_version: str = ""
    reference_url: str = ""
    matched_code: str = ""
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def fingerprint(self) -> str:
        """Stable identity for a finding across scans.

        Built from the matched source text rather than the line number: editing a
        notebook shifts every line below the change, so a line-based fingerprint
        would report unchanged findings as new. The matched text also keeps
        separate occurrences of one rule in the same file distinct, which a
        rule-and-path fingerprint alone would collapse into a single finding.
        """
        parts = (self.scanner, self.rule_id, self.object_path, self.package_name,
                 self.installed_version, " ".join(self.matched_code.split()))
        return sha256("|".join(parts).encode()).hexdigest()


def _severity_at_least(severity: str, threshold: str) -> bool:
    order = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    try:
        return order.index(severity) >= order.index(threshold)
    except ValueError:
        return True


class SemgrepRunner:
    """Static analysis of notebook and workspace file source."""

    name = "semgrep"

    def __init__(self, rules_path: str):
        self.rules_path = rules_path

    def is_available(self) -> bool:
        try:
            subprocess.run(["semgrep", "--version"], capture_output=True,
                           check=True, timeout=60, env=self._env())
            return True
        except (subprocess.SubprocessError, FileNotFoundError, OSError):
            return False

    def _env(self) -> dict[str, str]:
        return {**os.environ,
                "SEMGREP_ENABLE_VERSION_CHECK": "0",
                "SEMGREP_SEND_METRICS": "off"}

    def validate_rules(self) -> None:
        """Raise if the ruleset is invalid.

        Semgrep reports zero findings for a malformed ruleset and puts the parse
        error on stderr, so an unvalidated scan cannot distinguish "no problems
        found" from "no rules ran".
        """
        result = subprocess.run(
            ["semgrep", "--validate", "--config", self.rules_path],
            capture_output=True, text=True, timeout=120, env=self._env(),
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Semgrep ruleset {self.rules_path} is invalid: "
                f"{(result.stderr or result.stdout)[:500]}"
            )

    def run(self, source_dir: str, path_map: dict[str, str]) -> list[Finding]:
        result = subprocess.run(
            ["semgrep", "scan", "--json", "--quiet", "--no-git-ignore",
             "--config", self.rules_path, source_dir],
            capture_output=True, text=True, timeout=SEMGREP_TIMEOUT_SECONDS,
            env=self._env(),
        )
        if not result.stdout.strip():
            raise RuntimeError(f"Semgrep produced no output: {result.stderr[:500]}")

        report = json.loads(result.stdout)
        for error in report.get("errors", []):
            log.warning("semgrep: %s", str(error.get("message", error))[:300])

        findings = []
        for entry in report.get("results", []):
            extra = entry.get("extra", {})
            metadata = extra.get("metadata", {})
            rule_id = entry.get("check_id", "").rsplit(".", 1)[-1]
            local = entry.get("path", "")
            findings.append(Finding(
                scanner=self.name,
                rule_id=rule_id,
                severity=_SEMGREP_SEVERITY.get(extra.get("severity", ""), "MEDIUM"),
                title=metadata.get("cwe") or rule_id.replace("-", " ").capitalize(),
                description=" ".join((extra.get("message") or "").split()),
                object_path=path_map.get(local, local),
                line_start=(entry.get("start") or {}).get("line"),
                reference_url=(metadata.get("references") or [""])[0],
                matched_code=(extra.get("lines") or "")[:300],
            ))
        return findings


class TrivyRunner:
    """Known vulnerabilities in declared dependencies."""

    name = "trivy"

    def is_available(self) -> bool:
        return os.path.isfile(TRIVY_BINARY) and os.access(TRIVY_BINARY, os.X_OK)

    def run(self, manifest_dir: str, severity_threshold: str = "LOW") -> list[Finding]:
        env = {**os.environ}
        cache_dir = os.environ.get(TRIVY_CACHE_ENV)
        if cache_dir:
            env["TRIVY_CACHE_DIR"] = cache_dir

        result = subprocess.run(
            [TRIVY_BINARY, "fs", "--scanners", "vuln", "--format", "json",
             "--quiet", "--exit-code", "0", manifest_dir],
            capture_output=True, text=True, timeout=TRIVY_TIMEOUT_SECONDS, env=env,
        )
        if not result.stdout.strip():
            raise RuntimeError(f"Trivy produced no output: {result.stderr[:500]}")

        report = json.loads(result.stdout)
        findings = []
        for target in report.get("Results") or []:
            for vuln in target.get("Vulnerabilities") or []:
                severity = (vuln.get("Severity") or "UNKNOWN").upper()
                if not _severity_at_least(severity, severity_threshold):
                    continue
                findings.append(Finding(
                    scanner=self.name,
                    rule_id=vuln.get("VulnerabilityID", ""),
                    severity=severity,
                    title=vuln.get("Title") or vuln.get("VulnerabilityID", ""),
                    description=" ".join((vuln.get("Description") or "").split())[:1000],
                    object_path=target.get("Target", ""),
                    package_name=vuln.get("PkgName", ""),
                    installed_version=vuln.get("InstalledVersion", ""),
                    fixed_version=vuln.get("FixedVersion", ""),
                    reference_url=vuln.get("PrimaryURL", ""),
                ))
        return findings
