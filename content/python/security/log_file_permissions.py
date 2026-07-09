from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    log_directory = await _log_directory(ctx)
    if not log_directory:
        return _unavailable_result("PostgreSQL log_directory setting is empty or unavailable", "security_log_directory_empty")

    rows = []
    rows.extend(
        _permission_findings(
            log_directory,
            component="postgresql_log_directory",
            expected_mode="not world accessible or writable",
            disallowed_bits=0o007 | 0o020,
            missing_ok=True,
            risk_reason="PostgreSQL log directory permissions are broader than expected",
        )
    )

    try:
        files = sorted((p for p in log_directory.iterdir() if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        files = []
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
    return _result(
        rows,
        ok_title="PostgreSQL log file permissions are restrictive",
        fail_title="PostgreSQL log file permissions are too broad",
        recommendation="Keep PostgreSQL logs readable only by database administrators and avoid world-readable log directories.",
        diagnostic_code="security_log_file_permissions",
    )
