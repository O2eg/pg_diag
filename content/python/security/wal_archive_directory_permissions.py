from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    archive_mode = str(await _setting(ctx, "archive_mode") or "").lower()
    archive_command = str(await _setting(ctx, "archive_command") or "")
    if archive_mode in {"off", "false", "0"} or not archive_command:
        return _result(
            [],
            ok_title="WAL archiving is disabled or archive_command is empty",
            fail_title="WAL archive path permission findings found",
            recommendation="Keep WAL archive destinations writable only by PostgreSQL backup automation.",
            diagnostic_code="security_wal_archive_directory_permissions",
        )

    rows = []
    for path in _paths_from_command(archive_command):
        target = path if path.exists() and path.is_dir() else path.parent
        rows.extend(
            _permission_findings(
                target,
                component="wal_archive_path",
                expected_mode="not group/world writable and not world accessible",
                disallowed_bits=0o027,
                missing_ok=True,
                risk_reason="WAL archive path permissions are broader than expected",
            )
        )
    return _result(
        rows,
        ok_title="No broad WAL archive path permissions detected",
        fail_title="WAL archive path permission findings found",
        recommendation="Keep WAL archive directories protected because archived WAL can expose data and enable replay attacks.",
        diagnostic_code="security_wal_archive_directory_permissions",
    )
