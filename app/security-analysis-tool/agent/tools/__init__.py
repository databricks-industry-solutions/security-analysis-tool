"""Tool registry for the SAT agent.

Every tool is read-only. There is intentionally no tool that grants, revokes,
or reconfigures anything — remediation is described to the operator, never
performed.
"""

from . import audit, genie, permissions, secret_scans


def register_all() -> None:
    permissions.register()
    secret_scans.register()
    audit.register()
    genie.register()
