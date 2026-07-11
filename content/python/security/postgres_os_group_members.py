from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    group_result = await ctx.host.run(("getent", "group", "postgres"))
    group_lines = group_result.stdout.strip().splitlines()
    if group_result.returncode != 0 or not group_lines:
        group_exists = False
        rows = []
    else:
        fields = group_lines[0].split(":")
        group_exists = len(fields) >= 4
        members = set(fields[3].split(",")) if group_exists and fields[3] else set()
        gid = fields[2] if group_exists else ""
        passwd_result = await ctx.host.run(("getent", "passwd"))
        if passwd_result.returncode == 0:
            for line in passwd_result.stdout.splitlines():
                passwd_fields = line.split(":")
                if len(passwd_fields) >= 4 and passwd_fields[3] == gid:
                    members.add(passwd_fields[0])
        rows = [
            {
                "group_name": "postgres",
                "member": member,
                "risk_level": "medium",
                "risk_reason": "Additional OS account is a member of the postgres group and requires policy review",
            }
            for member in sorted(members - {"postgres", "root"})
        ]

    if not group_exists:
        return _not_applicable_result(
            "The database host has no postgres OS group; review the actual service account group separately",
            "security_postgres_group_not_applicable",
        )
    return _result(
        rows,
        ok_title="No unexpected members found in the postgres OS group",
        fail_title="Additional postgres OS group members require review",
        recommendation="Keep membership in the postgres OS group limited to the PostgreSQL service account and tightly controlled administrators.",
        diagnostic_code="security_postgres_os_group_members",
    )
