from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    del ctx
    def inspect() -> tuple[int, list[dict[str, Any]]]:
        paths: list[Path] = []
        for pattern in (
            "/usr/share/postgresql/*/extension",
            "/usr/lib/postgresql/*/lib",
            "/usr/lib/*/postgresql/*/lib",
            "/usr/pgsql-*/share/extension",
            "/usr/pgsql-*/lib",
            "/usr/lib64/pgsql",
            "/usr/local/pgsql/share/extension",
            "/usr/local/pgsql/lib",
        ):
            paths.extend(Path("/").glob(pattern.lstrip("/")))
        resolved_paths = _dedupe_paths(paths)
        rows = []
        for path in resolved_paths:
            rows.extend(
                _permission_findings(
                    path,
                    component="postgresql_extension_directory",
                    expected_mode="not group/world writable",
                    disallowed_bits=0o022,
                    missing_ok=True,
                    risk_reason="PostgreSQL extension directory is writable by group or other OS users",
                )
            )
        return len(resolved_paths), rows

    path_count, rows = await run_blocking(inspect)
    if not path_count:
        return _unavailable_result(
            "No PostgreSQL extension directory could be discovered on the local host",
            "security_extension_directory_unavailable",
        )
    return _result(
        rows,
        ok_title="PostgreSQL extension directories are not group/world writable",
        fail_title="PostgreSQL extension directory permission findings found",
        recommendation="Keep extension control files and shared libraries writable only by trusted package or PostgreSQL administrators.",
        diagnostic_code="security_extension_directory_permissions",
    )
