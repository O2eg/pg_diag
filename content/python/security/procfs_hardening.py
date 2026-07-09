from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    del ctx
    rows = []
    ptrace_scope = _read_text(Path("/proc/sys/kernel/yama/ptrace_scope")).strip()
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
    proc_opts = _mount_options_for("/proc")
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
    return _result(
        rows,
        ok_title="procfs process-inspection hardening is enabled",
        fail_title="procfs hardening findings found",
        recommendation="Use ptrace_scope and hidepid to reduce accidental exposure of process command lines and environments.",
        diagnostic_code="security_procfs_hardening",
    )
