from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    del ctx
    rows = []
    for path in _candidate_history_files():
        rows.extend(_inspect_history_file(path))
    rows = _dedupe_rows(rows, ("file_path", "finding_type", "line_number", "risk_reason"))
    return _result(
        rows,
        ok_title="No PostgreSQL history file security findings found",
        fail_title="PostgreSQL history file security findings found",
        recommendation="Disable psql history for privileged maintenance sessions or protect and scrub history files that may contain secrets or DDL.",
        diagnostic_code="security_postgres_history_files",
    )
