from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    del ctx
    def inspect() -> tuple[int, list[dict[str, Any]]]:
        paths: list[Path] = []
        for binary in ("postgres", "psql", "pg_ctl", "pg_dump", "pg_restore"):
            found = shutil.which(binary)
            if found:
                paths.append(Path(found))
        for pattern in (
            "/usr/lib/postgresql/*/bin/postgres",
            "/usr/lib/postgresql/*/bin/psql",
            "/usr/pgsql-*/bin/postgres",
            "/usr/pgsql-*/bin/psql",
            "/usr/local/pgsql/bin/postgres",
            "/usr/local/pgsql/bin/psql",
        ):
            paths.extend(Path("/").glob(pattern.lstrip("/")))

        resolved_paths = _dedupe_paths(paths)
        rows = []
        for path in resolved_paths:
            rows.extend(
                _permission_findings(
                    path,
                    component="postgresql_binary",
                    expected_mode="not group/world writable",
                    disallowed_bits=0o022,
                    missing_ok=True,
                    risk_reason="PostgreSQL executable is writable by group or other OS users",
                )
            )
            owner = _owner_name(path)
            if owner and owner not in {"root", "postgres"}:
                rows.append(
                    {
                        "path": str(path),
                        "component": "postgresql_binary",
                        "file_mode": _mode_for_path(path),
                        "owner": owner,
                        "expected_owner": "root or postgres",
                        "risk_level": "medium",
                        "risk_reason": "PostgreSQL executable is owned by an unexpected OS account",
                    }
                )
        return len(resolved_paths), rows

    path_count, rows = await run_blocking(inspect)
    if not path_count:
        return _unavailable_result(
            "No PostgreSQL executable path could be discovered on the local host",
            "security_postgres_binary_unavailable",
        )
    return _result(
        rows,
        ok_title="PostgreSQL executable paths are not writable by untrusted OS users",
        fail_title="PostgreSQL executable path integrity findings found",
        recommendation="Keep PostgreSQL binaries owned by root or postgres and remove group/world write permissions.",
        diagnostic_code="security_postgres_binary_integrity",
    )
