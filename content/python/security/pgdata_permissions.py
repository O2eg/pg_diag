from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    data_directory = await ctx.conn.fetchval("select setting from pg_settings where name = 'data_directory'")
    if not data_directory:
        return _unavailable_result(
            "PostgreSQL data_directory setting is empty or unavailable",
            "security_pgdata_directory_empty",
        )
    data_path = Path(str(data_directory))
    try:
        data_stat = data_path.stat()
    except FileNotFoundError:
        return _unavailable_result(
            f"PostgreSQL reports data_directory as {data_path}, but the directory is not visible locally",
            "security_pgdata_directory_missing",
        )
    except PermissionError:
        return _unavailable_result(
            f"The collector cannot stat PostgreSQL data_directory {data_path}",
            "security_pgdata_directory_permission",
        )

    mode = stat.S_IMODE(data_stat.st_mode)
    rows = []
    if mode & 0o027:
        rows.append(
            {
                "data_directory": str(data_path),
                "directory_mode": _octal(mode),
                "expected_mode": "0700 or 0750",
                "risk_level": "high" if mode & 0o007 else "medium",
                "risk_reason": "PGDATA directory permissions are broader than expected",
            }
        )
    return _result(
        rows,
        ok_title="PGDATA directory permissions are restrictive",
        fail_title="PGDATA directory permissions are too broad",
        recommendation="Keep PGDATA permissions at 0700 or 0750 and restrict access to the PostgreSQL OS account.",
        diagnostic_code="security_pgdata_permissions",
    )
