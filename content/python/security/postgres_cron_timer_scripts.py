from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    del ctx
    rows = []
    for path in _cron_files():
        rows.extend(_inspect_cron_file(path))
    for path in _postgres_systemd_files(include_timers=True):
        rows.extend(_inspect_systemd_exec_paths(path))
    rows = _dedupe_rows(rows, ("file_path", "line_number", "script_path", "risk_reason"))
    return _result(
        rows,
        ok_title="No writable PostgreSQL cron or timer script paths found",
        fail_title="PostgreSQL cron or timer script findings found",
        recommendation="Keep PostgreSQL maintenance cron files, timers, and referenced scripts writable only by trusted administrators.",
        diagnostic_code="security_postgres_cron_timer_scripts",
    )
