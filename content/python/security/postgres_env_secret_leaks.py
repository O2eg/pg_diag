from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    del ctx
    def inspect() -> tuple[list[dict[str, Any]], int, int]:
        rows = []
        readable = 0
        unreadable = 0
        try:
            proc_dirs = list(Path("/proc").iterdir())
        except OSError:
            return rows, readable, 1
        for proc_dir in proc_dirs:
            if not proc_dir.name.isdigit():
                continue
            try:
                environ = proc_dir.joinpath("environ").read_bytes()
            except OSError:
                unreadable += 1
                continue
            readable += 1
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
        return rows, readable, unreadable

    rows, readable, unreadable = await run_blocking(inspect)
    if not readable:
        return _unavailable_result(
            "No process environment could be read from /proc",
            "security_proc_environ_unavailable",
        )
    return _result(
        rows,
        ok_title="No PostgreSQL credentials detected in readable process environments",
        fail_title="PostgreSQL credentials detected in process environments",
        recommendation="Avoid PGPASSWORD and URI passwords in long-lived process environments; prefer protected service files, peer auth, or secret managers.",
        diagnostic_code="security_postgres_env_secret_leaks",
        coverage_complete=unreadable == 0,
        coverage_note=(
            f"read {readable} process environment(s); {unreadable} were inaccessible or disappeared"
            if unreadable else ""
        ),
    )
