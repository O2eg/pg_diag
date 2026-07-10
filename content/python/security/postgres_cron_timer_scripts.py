from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    del ctx
    def inspect() -> tuple[int, list[dict[str, Any]]]:
        cron_files = _cron_files()
        systemd_files = _postgres_systemd_files(include_timers=True)
        rows = []
        for path in cron_files:
            rows.extend(_inspect_cron_file(path))
        for path in systemd_files:
            rows.extend(_inspect_systemd_exec_paths(path))
        rows = _dedupe_rows(rows, ("file_path", "line_number", "script_path", "risk_reason"))
        return len(cron_files) + len(systemd_files), rows

    evidence_count, rows = await run_blocking(inspect)
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
