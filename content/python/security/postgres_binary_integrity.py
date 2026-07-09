from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    del ctx
    paths: list[Path] = []
    for binary in ("postgres", "psql", "pg_ctl", "pg_dump", "pg_restore"):
        found = shutil.which(binary)
        if found:
            paths.append(Path(found))
    for pattern in ("/usr/lib/postgresql/*/bin/postgres", "/usr/lib/postgresql/*/bin/psql"):
        paths.extend(Path("/").glob(pattern.lstrip("/")))

    rows = []
    for path in _dedupe_paths(paths):
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
    return _result(
        rows,
        ok_title="PostgreSQL executable paths are not writable by untrusted OS users",
        fail_title="PostgreSQL executable path integrity findings found",
        recommendation="Keep PostgreSQL binaries owned by root or postgres and remove group/world write permissions.",
        diagnostic_code="security_postgres_binary_integrity",
    )
