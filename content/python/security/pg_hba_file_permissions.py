from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    hba_file = await ctx.conn.fetchval("select setting from pg_settings where name = 'hba_file'")
    if not hba_file:
        return _unavailable_result("PostgreSQL hba_file setting is empty or unavailable", "security_hba_file_empty")
    hba_path = Path(str(hba_file))
    try:
        file_stat = hba_path.stat()
    except FileNotFoundError:
        return _unavailable_result(
            f"PostgreSQL reports hba_file as {hba_path}, but the file is not visible locally",
            "security_hba_file_missing",
        )
    except PermissionError:
        return _unavailable_result(
            f"The collector cannot stat PostgreSQL hba_file {hba_path}",
            "security_hba_file_permission",
        )

    file_mode = stat.S_IMODE(file_stat.st_mode)
    parent_mode = None
    try:
        parent_mode = stat.S_IMODE(hba_path.parent.stat().st_mode)
    except OSError:
        parent_mode = None

    rows = []
    if file_mode not in {0o600, 0o640}:
        rows.append(
            {
                "file_path": str(hba_path),
                "file_mode": _octal(file_mode),
                "expected_file_mode": "0600 or 0640",
                "parent_directory": str(hba_path.parent),
                "parent_mode": _octal(parent_mode),
                "risk_level": "high" if file_mode & 0o007 else "medium",
                "risk_reason": "pg_hba.conf file permissions are broader than expected",
            }
        )
    return _result(
        rows,
        ok_title="pg_hba.conf file permissions are restrictive",
        fail_title="pg_hba.conf file permissions are too broad",
        recommendation="Set pg_hba.conf permissions to 0600 or 0640 and keep write access limited to PostgreSQL administrators.",
        diagnostic_code="security_pg_hba_file_permissions",
    )
