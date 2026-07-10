from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    del ctx
    def inspect() -> tuple[bool, list[dict[str, Any]]]:
        import grp
        import pwd

        try:
            postgres_group = grp.getgrnam("postgres")
        except KeyError:
            return False, []
        members = set(postgres_group.gr_mem)
        members.update(
            account.pw_name
            for account in pwd.getpwall()
            if account.pw_gid == postgres_group.gr_gid
        )
        rows = [
            {
                "group_name": "postgres",
                "member": member,
                "risk_level": "medium",
                "risk_reason": "Additional OS account is a member of the postgres group and requires policy review",
            }
            for member in sorted(members - {"postgres", "root"})
        ]
        return True, rows

    group_exists, rows = await run_blocking(inspect)
    if not group_exists:
        return _not_applicable_result(
            "The local host has no postgres OS group; review the actual service account group separately",
            "security_postgres_group_not_applicable",
        )
    return _result(
        rows,
        ok_title="No unexpected members found in the postgres OS group",
        fail_title="Additional postgres OS group members require review",
        recommendation="Keep membership in the postgres OS group limited to the PostgreSQL service account and tightly controlled administrators.",
        diagnostic_code="security_postgres_os_group_members",
    )
