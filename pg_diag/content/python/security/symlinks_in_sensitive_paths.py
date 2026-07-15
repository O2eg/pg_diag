from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    roots = await _sensitive_roots(ctx)
    if not roots:
        return _unavailable_result(
            "No PostgreSQL-sensitive local root could be derived from server settings",
            "security_sensitive_roots_unavailable",
        )
    rows = []
    coverage = []
    for root in roots:
        root_rows, root_coverage = await _host_symlink_findings(
            ctx,
            root,
            max_depth=2,
            max_rows=100,
            max_entries=50000,
        )
        rows.extend(root_rows)
        coverage.append(root_coverage)
    rows = _dedupe_rows(rows, ("path", "target", "risk_reason"))
    incomplete = [entry for entry in coverage if not entry["complete"]]
    return _result(
        rows[:200],
        ok_title="No symlinks found in PostgreSQL-sensitive top-level paths",
        fail_title="Symlinks found in PostgreSQL-sensitive paths",
        recommendation="Review symlinks in PGDATA, log, tablespace, and archive paths; keep only intentional targets with restrictive ownership.",
        diagnostic_code="security_symlinks_in_sensitive_paths",
        coverage_complete=not incomplete,
        coverage_note="; ".join(str(entry.get("reason") or "scan incomplete") for entry in incomplete[:3]),
    )
