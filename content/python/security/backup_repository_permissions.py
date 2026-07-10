from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    del ctx
    candidates = [
        Path("/var/lib/pgbackrest"),
        Path("/var/log/pgbackrest"),
        Path("/var/lib/postgresql/backup"),
        Path("/var/backups/postgresql"),
        Path("/backup"),
        Path("/backups"),
    ]
    def inspect() -> tuple[int, list[dict[str, Any]]]:
        existing = [path for path in candidates if path.exists()]
        rows = []
        for path in existing:
            rows.extend(
                _permission_findings(
                    path,
                    component="backup_repository",
                    expected_mode="not group/world writable and not world accessible",
                    disallowed_bits=0o027,
                    missing_ok=True,
                    risk_reason="PostgreSQL backup repository path permissions are broader than expected",
                )
            )
        return len(existing), rows

    path_count, rows = await run_blocking(inspect)
    if not path_count:
        return _unavailable_result(
            "No known local PostgreSQL backup repository path was discovered; custom and remote repositories are not covered",
            "security_backup_repository_not_discovered",
        )
    return _result(
        rows,
        ok_title="No broad PostgreSQL backup repository permissions detected",
        fail_title="PostgreSQL backup repository permission findings found",
        recommendation="Backups contain recoverable database contents; keep repositories readable only by trusted backup operators.",
        diagnostic_code="security_backup_repository_permissions",
    )
