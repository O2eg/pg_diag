from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    logging_collector = str(await _setting(ctx, "logging_collector") or "").lower()
    if logging_collector not in {"on", "true", "1"}:
        return _not_applicable_result(
            "PostgreSQL logging_collector is disabled; validate the active external or journald destination separately",
            "security_log_files_not_applicable",
        )

    log_directory = await _log_directory(ctx)
    if not log_directory:
        return _unavailable_result("PostgreSQL log_directory setting is empty or unavailable", "security_log_directory_empty")

    def inspect() -> tuple[list[dict[str, Any]], bool, str]:
        rows = _permission_findings(
            log_directory,
            component="postgresql_log_directory",
            expected_mode="not world accessible or writable",
            disallowed_bits=0o007 | 0o020,
            missing_ok=False,
            risk_reason="PostgreSQL log directory permissions are broader than expected",
        )
        try:
            files = sorted(
                (path for path in log_directory.iterdir() if path.is_file()),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError as exc:
            return rows, False, f"cannot enumerate {log_directory}: {exc}"
        for path in files[:100]:
            rows.extend(
                _permission_findings(
                    path,
                    component="postgresql_log_file",
                    expected_mode="0640 or stricter",
                    disallowed_bits=0o027,
                    missing_ok=True,
                    risk_reason="PostgreSQL log file permissions expose operational or SQL details",
                )
            )
        if len(files) > 100:
            return rows, False, f"only the 100 newest of {len(files)} log files were inspected"
        return rows, True, ""

    rows, coverage_complete, coverage_note = await run_blocking(inspect)
    return _result(
        rows,
        ok_title="PostgreSQL log file permissions are restrictive",
        fail_title="PostgreSQL log file permissions are too broad",
        recommendation="Keep PostgreSQL logs readable only by database administrators and avoid world-readable log directories.",
        diagnostic_code="security_log_file_permissions",
        coverage_complete=coverage_complete,
        coverage_note=coverage_note,
    )
