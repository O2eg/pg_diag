from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    cron_files = await _host_cron_files(ctx)
    systemd_files = await _host_postgres_systemd_files(ctx, include_timers=True)
    rows = []
    for path in cron_files:
        rows.extend(await _host_inspect_cron_file(ctx, path))
    for path in systemd_files:
        rows.extend(await _host_inspect_systemd_exec_paths(ctx, path))
    rows = _dedupe_rows(rows, ("file_path", "line_number", "script_path", "risk_reason"))
    evidence_count = len(cron_files) + len(systemd_files)
    if not evidence_count:
        return _unavailable_result(
            "No readable cron or systemd scheduling evidence was discovered",
            "security_scheduler_evidence_unavailable",
        )
    return _result(
        rows,
        ok_title="No writable PostgreSQL cron or timer script paths found",
        fail_title="PostgreSQL cron or timer script findings found",
        recommendation="Keep PostgreSQL maintenance cron files, timers, and referenced scripts writable only by trusted administrators.",
        diagnostic_code="security_postgres_cron_timer_scripts",
    )
