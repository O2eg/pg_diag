from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    del ctx
    def inspect() -> tuple[list[dict[str, Any]], bool]:
        rows = []
        suid_dumpable = _read_text(Path("/proc/sys/fs/suid_dumpable")).strip()
        if suid_dumpable and suid_dumpable != "0":
            rows.append(
                {
                    "setting": "fs.suid_dumpable",
                    "value": suid_dumpable,
                    "expected": "0",
                    "risk_level": "high",
                    "risk_reason": "setuid-style core dumps are enabled",
                }
            )
        core_pattern = _read_text(Path("/proc/sys/kernel/core_pattern")).strip()
        if core_pattern and core_pattern not in {"|/bin/false", "none"}:
            rows.append(
                {
                    "setting": "kernel.core_pattern",
                    "value": core_pattern[:240],
                    "expected": "disabled or routed to a protected collector",
                    "risk_level": "medium",
                    "risk_reason": "core dumps may capture PostgreSQL memory contents",
                }
            )
        return rows, bool(suid_dumpable or core_pattern)

    rows, evidence_available = await run_blocking(inspect)
    if not evidence_available:
        return _unavailable_result(
            "Core dump sysctl evidence could not be read from /proc",
            "security_core_dump_evidence_unavailable",
        )
    return _result(
        rows,
        ok_title="Core dump policy does not expose PostgreSQL memory contents",
        fail_title="Core dump policy findings found",
        recommendation="Disable core dumps for PostgreSQL or route them to a protected, access-controlled collector.",
        diagnostic_code="security_core_dump_policy",
    )
