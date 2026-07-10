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
        root_rows, root_coverage = await run_blocking(
            _world_writable_tree_findings,
            root,
            max_depth=4,
            max_rows=100,
            max_entries=50000,
        )
        rows.extend(root_rows)
        coverage.append(root_coverage)
    rows = _dedupe_rows(rows, ("path", "file_mode", "risk_reason"))
    incomplete = [entry for entry in coverage if not entry["complete"]]
    return _result(
        rows[:200],
        ok_title="No world-writable paths found in PostgreSQL-sensitive trees",
        fail_title="World-writable PostgreSQL-sensitive paths found",
        recommendation="Remove world-write permissions from PGDATA, log, tablespace, and archive trees.",
        diagnostic_code="security_world_writable_paths_in_pg_tree",
        coverage_complete=not incomplete,
        coverage_note="; ".join(str(entry.get("reason") or "scan incomplete") for entry in incomplete[:3]),
    )
