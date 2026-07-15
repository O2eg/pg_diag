from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    rows = []
    for path in await _host_candidate_history_files(ctx):
        rows.extend(await _host_inspect_history_file(ctx.host, path))
    rows = _dedupe_rows(rows, ("file_path", "finding_type", "line_number", "risk_reason"))
    return _result(
        rows,
        ok_title="No PostgreSQL history file security findings found",
        fail_title="PostgreSQL history file security findings found",
        recommendation="Disable psql history for privileged maintenance sessions or protect and scrub history files that may contain secrets or DDL.",
        diagnostic_code="security_postgres_history_files",
    )
