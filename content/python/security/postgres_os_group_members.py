from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    del ctx
    rows = []
    try:
        group_text = Path("/etc/group").read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return _unavailable_result(f"The collector cannot read /etc/group: {exc}", "security_group_file_unavailable")
    for line in group_text.splitlines():
        parts = line.split(":")
        if len(parts) < 4 or parts[0] != "postgres":
            continue
        members = [member for member in parts[3].split(",") if member]
        for member in members:
            if member in {"postgres", "root"}:
                continue
            rows.append(
                {
                    "group_name": "postgres",
                    "member": member,
                    "risk_level": "high",
                    "risk_reason": "Non-service OS user is a member of the postgres group",
                }
            )
    return _result(
        rows,
        ok_title="No unexpected members found in the postgres OS group",
        fail_title="Unexpected postgres OS group members found",
        recommendation="Keep membership in the postgres OS group limited to the PostgreSQL service account and tightly controlled administrators.",
        diagnostic_code="security_postgres_os_group_members",
    )
