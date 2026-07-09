from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    roots = await _sensitive_roots(ctx)
    rows = []
    for root in roots:
        rows.extend(_world_writable_tree_findings(root, max_depth=4, max_rows=100))
    rows = _dedupe_rows(rows, ("path", "file_mode", "risk_reason"))
    return _result(
        rows[:200],
        ok_title="No world-writable paths found in PostgreSQL-sensitive trees",
        fail_title="World-writable PostgreSQL-sensitive paths found",
        recommendation="Remove world-write permissions from PGDATA, log, tablespace, and archive trees.",
        diagnostic_code="security_world_writable_paths_in_pg_tree",
    )
