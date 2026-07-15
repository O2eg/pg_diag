from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    socket_permissions = await ctx.conn.fetchval(
        "select setting from pg_settings where name = 'unix_socket_permissions'"
    )
    socket_directories = await ctx.conn.fetchval(
        "select setting from pg_settings where name = 'unix_socket_directories'"
    )
    port = await ctx.conn.fetchval("select setting from pg_settings where name = 'port'")

    rows: list[dict[str, Any]] = []
    configured_mode = _parse_octal(str(socket_permissions or ""))
    configured_mode_is_broad = configured_mode is not None and bool(configured_mode & 0o007)

    for socket_dir in _split_socket_directories(str(socket_directories or "")):
        if socket_dir.startswith("@") or not port:
            continue
        socket_path = Path(socket_dir) / f".s.PGSQL.{port}"
        try:
            socket_stat = await ctx.host.stat(socket_path)
        except FileNotFoundError:
            continue
        except PermissionError:
            rows.append(
                {
                    "socket_file": str(socket_path),
                    "configured_permissions": str(socket_permissions or ""),
                    "actual_mode": "",
                    "risk_level": "medium",
                    "risk_reason": "collector cannot stat PostgreSQL Unix socket",
                }
            )
            continue
        actual_mode = stat.S_IMODE(socket_stat.mode)
        if actual_mode & 0o007:
            rows.append(
                {
                    "socket_file": str(socket_path),
                    "configured_permissions": str(socket_permissions or ""),
                    "actual_mode": _octal(actual_mode),
                    "risk_level": "medium",
                    "risk_reason": "PostgreSQL Unix socket accepts connection attempts from other OS users; pg_hba authentication still applies",
                }
            )

    if configured_mode_is_broad and not rows:
        rows.append(
            {
                "socket_file": "",
                "configured_permissions": _octal(configured_mode),
                "actual_mode": "",
                "risk_level": "medium",
                "risk_reason": "unix_socket_permissions permits connection attempts by other OS users; pg_hba authentication still applies",
            }
        )

    unique_rows = _dedupe_rows(rows, ("socket_file", "configured_permissions", "actual_mode", "risk_reason"))
    return _result(
        unique_rows,
        ok_title="PostgreSQL Unix socket permissions are restrictive",
        fail_title="PostgreSQL Unix socket permissions are too broad",
        recommendation="Use unix_socket_permissions 0700 or 0770 unless all local OS users are trusted for socket access.",
        diagnostic_code="security_unix_socket_permissions",
    )
