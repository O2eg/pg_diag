from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    rows = []
    try:
        ptrace_scope = (await ctx.host.read_text("/proc/sys/kernel/yama/ptrace_scope")).strip()
    except OSError:
        ptrace_scope = ""
    if ptrace_scope == "0":
        rows.append(
            {
                "setting": "kernel.yama.ptrace_scope",
                "value": ptrace_scope,
                "expected": "1 or stricter",
                "risk_level": "medium",
                "risk_reason": "ptrace_scope allows broad same-user process inspection",
            }
        )
    mounts = await _host_mount_table(ctx)
    proc_opts = next((row["options"] for row in mounts if row["mount"] == "/proc"), "")
    if "hidepid=1" not in proc_opts and "hidepid=2" not in proc_opts:
        rows.append(
            {
                "setting": "/proc mount options",
                "value": proc_opts,
                "expected": "hidepid=1 or hidepid=2",
                "risk_level": "medium",
                "risk_reason": "/proc is not mounted with hidepid protection",
            }
        )
    if not (ptrace_scope or proc_opts):
        return _unavailable_result(
            "Neither ptrace_scope nor /proc mount options could be inspected",
            "security_procfs_evidence_unavailable",
        )
    return _result(
        rows,
        ok_title="procfs process-inspection hardening is enabled",
        fail_title="procfs hardening findings found",
        recommendation="Use ptrace_scope and hidepid to reduce accidental exposure of process command lines and environments.",
        diagnostic_code="security_procfs_hardening",
    )
