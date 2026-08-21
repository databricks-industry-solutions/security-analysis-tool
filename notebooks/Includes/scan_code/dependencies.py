"""Dependency manifest extraction for Databricks workspaces.

Trivy reports a CVE only when it can read a package name and an exact version
from a manifest file. Notebooks have no manifest, so the versions have to be
recovered from where they are actually declared:

* ``%pip install`` and ``!pip install`` magics inside notebook source
* PyPI and Maven libraries on job tasks
* ``dependencies`` on serverless environment specs
* real ``requirements.txt`` / ``pyproject.toml`` files stored in the workspace

Unpinned requirements are collected but reported separately rather than written
to the manifest. Trivy silently returns nothing for ``pandas`` with no version,
so including them would inflate the manifest while adding no coverage, and would
make an empty result look like a clean bill of health.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Matches pip magics in exported notebook source. Databricks writes magics as
# "# MAGIC %pip install ..." in SOURCE format and as bare "%pip install ..." in
# .py files, so the comment prefix is optional.
_PIP_MAGIC = re.compile(
    r"^\s*(?:#\s*MAGIC\s+)?[%!]\s*pip\s+install\s+(?P<args>.+?)\s*$",
    re.MULTILINE,
)

# PEP 508 requirement pinned to an exact version. Only "==" is treated as pinned:
# ">=1.0" describes a range Trivy cannot resolve to a single package.
_PINNED = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]+\])?\s*==\s*"
    r"(?P<version>[A-Za-z0-9][A-Za-z0-9.+!-]*)$"
)

_PIP_FLAGS_WITH_VALUE = {"-r", "-c", "--index-url", "-i", "--extra-index-url",
                         "--find-links", "-f", "--trusted-host"}


@dataclass
class Dependencies:
    """Packages discovered across a workspace, split by whether Trivy can use them."""

    pinned: dict[str, str] = field(default_factory=dict)
    unpinned: set[str] = field(default_factory=set)
    maven: set[str] = field(default_factory=set)
    sources: dict[str, str] = field(default_factory=dict)

    def add_pinned(self, name: str, version: str, source: str) -> None:
        key = _normalise(name)
        self.pinned[key] = version
        self.sources.setdefault(f"{key}=={version}", source)

    def add_unpinned(self, name: str) -> None:
        self.unpinned.add(_normalise(name))

    def requirements_txt(self) -> str:
        return "".join(
            f"{name}=={version}\n" for name, version in sorted(self.pinned.items())
        )

    @property
    def is_empty(self) -> bool:
        return not self.pinned


def _normalise(name: str) -> str:
    """Normalise a distribution name per PEP 503."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _split_requirements(args: str) -> list[str]:
    """Requirement tokens from a pip command line, with flags removed."""
    tokens = args.replace(";", " ").split()
    requirements: list[str] = []
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
            continue
        if token in _PIP_FLAGS_WITH_VALUE:
            skip_next = True
            continue
        if token.startswith("-"):
            continue
        # Local paths, URLs and VCS references carry no resolvable version.
        if token.startswith(("http://", "https://", "git+", "/", ".")):
            continue
        requirements.append(token.strip("\"'"))
    return requirements


def from_notebook_source(source: str, path: str, deps: Dependencies) -> None:
    """Collect requirements declared by pip magics in one notebook."""
    for match in _PIP_MAGIC.finditer(source):
        for requirement in _split_requirements(match.group("args")):
            pinned = _PINNED.match(requirement)
            if pinned:
                deps.add_pinned(pinned.group("name"), pinned.group("version"), path)
            else:
                deps.add_unpinned(re.split(r"[<>=!~\[]", requirement, 1)[0])


def from_requirements_file(content: str, path: str, deps: Dependencies) -> None:
    """Collect requirements from a requirements.txt stored in the workspace."""
    for line in content.splitlines():
        line = line.split("#", 1)[0].split(";", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        pinned = _PINNED.match(line)
        if pinned:
            deps.add_pinned(pinned.group("name"), pinned.group("version"), path)
        else:
            deps.add_unpinned(re.split(r"[<>=!~\[;]", line, 1)[0])


def from_jobs(workspace_client, deps: Dependencies) -> None:
    """Collect libraries declared on job tasks and serverless environments.

    Job libraries are where pinned versions reliably exist: a task that installs
    ``requests==2.31.0`` states its version, where a notebook magic often does
    not. Maven coordinates are recorded separately because Trivy resolves them
    from a build file rather than a requirements list.
    """
    for job in workspace_client.jobs.list():
        settings = getattr(job, "settings", None)
        if settings is None:
            continue
        source = f"job:{job.job_id}"

        for task in getattr(settings, "tasks", None) or []:
            for library in getattr(task, "libraries", None) or []:
                pypi = getattr(library, "pypi", None)
                if pypi and getattr(pypi, "package", None):
                    _add_requirement(pypi.package, source, deps)
                maven = getattr(library, "maven", None)
                if maven and getattr(maven, "coordinates", None):
                    deps.maven.add(maven.coordinates)

        for environment in getattr(settings, "environments", None) or []:
            spec = getattr(environment, "spec", None)
            for requirement in getattr(spec, "dependencies", None) or []:
                _add_requirement(str(requirement), source, deps)


def _add_requirement(requirement: str, source: str, deps: Dependencies) -> None:
    pinned = _PINNED.match(requirement.strip())
    if pinned:
        deps.add_pinned(pinned.group("name"), pinned.group("version"), source)
    else:
        name = re.split(r"[<>=!~\[]", requirement.strip(), 1)[0].strip()
        if name:
            deps.add_unpinned(name)
