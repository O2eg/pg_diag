from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    rows = []
    for path in await _host_candidate_client_secret_files(ctx):
        rows.extend(await _host_inspect_client_secret_file(ctx.host, path))

    rows = _dedupe_rows(rows, ("file_path", "finding_type", "risk_reason"))
    return _result(
        rows,
        ok_title="No PostgreSQL client secret file findings found",
        fail_title="PostgreSQL client secret file findings found",
        recommendation=(
            "Avoid storing cleartext passwords in service files where possible. "
            "Protect .pgpass and service files with owner-only permissions."
        ),
        diagnostic_code="security_client_secret_files",
    )
