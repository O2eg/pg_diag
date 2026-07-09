from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    roots = await _sensitive_roots(ctx)
    rows = []
    for root in roots:
        rows.extend(_symlink_findings(root, max_depth=2, max_rows=100))
    rows = _dedupe_rows(rows, ("path", "target", "risk_reason"))
    return _result(
        rows[:200],
        ok_title="No symlinks found in PostgreSQL-sensitive top-level paths",
        fail_title="Symlinks found in PostgreSQL-sensitive paths",
        recommendation="Review symlinks in PGDATA, log, tablespace, and archive paths; keep only intentional targets with restrictive ownership.",
        diagnostic_code="security_symlinks_in_sensitive_paths",
    )
