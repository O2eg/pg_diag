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
            # 0777 is the PostgreSQL default and pg_hba local rules still decide access.
            # It becomes a real finding only when the socket directory itself lets any
            # OS user replace the socket (world-writable without the sticky bit).
            directory_exposed = await _socket_directory_is_exposed(ctx, Path(socket_dir))
            rows.append(
                {
                    "socket_file": str(socket_path),
                    "configured_permissions": str(socket_permissions or ""),
                    "actual_mode": _octal(actual_mode),
                    "risk_level": "medium" if directory_exposed else "unknown",
                    "risk_reason": (
                        "PostgreSQL Unix socket is world-accessible inside a world-writable socket directory; other OS users could replace the socket path"
                        if directory_exposed
                        else "PostgreSQL Unix socket keeps the default 0777 mode; other OS users can attempt a connection, and local pg_hba rules decide whether it succeeds"
                    ),
                }
            )

    if configured_mode_is_broad and not rows:
        rows.append(
            {
                "socket_file": "",
                "configured_permissions": _octal(configured_mode),
                "actual_mode": "",
                "risk_level": "unknown",
                "risk_reason": "unix_socket_permissions keeps the default 0777 mode; other OS users can attempt a connection, and local pg_hba rules decide whether it succeeds",
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


async def _socket_directory_is_exposed(ctx: PythonSourceContext, directory: Path) -> bool:
    try:
        mode = stat.S_IMODE((await ctx.host.stat(directory)).mode)
    except OSError:
        return False
    return bool(mode & 0o002) and not mode & 0o1000
