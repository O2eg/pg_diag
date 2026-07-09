from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    del ctx
    rows = []
    for proc_dir in Path("/proc").iterdir():
        if not proc_dir.name.isdigit():
            continue
        environ_path = proc_dir / "environ"
        try:
            environ = environ_path.read_bytes()
        except OSError:
            continue
        if not _environment_contains_pg_secret(environ):
            continue
        cmdline = _read_proc_cmdline(proc_dir)
        rows.append(
            {
                "pid": proc_dir.name,
                "process": cmdline[:240],
                "finding_type": "environment_secret",
                "risk_level": "high",
                "risk_reason": "Process environment appears to contain PostgreSQL credentials",
            }
        )
    return _result(
        rows,
        ok_title="No PostgreSQL credentials detected in readable process environments",
        fail_title="PostgreSQL credentials detected in process environments",
        recommendation="Avoid PGPASSWORD and URI passwords in long-lived process environments; prefer protected service files, peer auth, or secret managers.",
        diagnostic_code="security_postgres_env_secret_leaks",
    )
