from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    archive_mode = str(await _setting(ctx, "archive_mode") or "").lower()
    archive_command = str(await _setting(ctx, "archive_command") or "")
    archive_library = str(await _setting(ctx, "archive_library") or "")
    if archive_mode in {"off", "false", "0"}:
        return _not_applicable_result(
            "WAL archiving is disabled, so no active archive destination can be checked",
            "security_wal_archive_not_applicable",
        )
    if archive_library:
        return _unavailable_result(
            "WAL archiving uses archive_library; this filesystem path check cannot infer its destination",
            "security_wal_archive_library_destination",
        )
    if not archive_command:
        return _unavailable_result(
            "WAL archiving is enabled but archive_command exposes no destination to inspect",
            "security_wal_archive_command_empty",
        )

    archive_paths = _paths_from_command(archive_command)
    if not archive_paths:
        return _unavailable_result(
            "No absolute filesystem destination could be derived from archive_command",
            "security_wal_archive_path_unknown",
        )

    rows = []
    for path in archive_paths:
        target = path if await ctx.host.is_dir(path) else path.parent
        rows.extend(
            await _host_permission_findings(
                ctx.host,
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
