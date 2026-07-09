from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    roots = await _sensitive_roots(ctx)
    rows = []
    mounts = _mount_table()
    for root in roots:
        mount = _mount_for_path(root, mounts)
        if not mount:
            continue
        source = mount["source"]
        fstype = mount["fstype"]
        if _mount_looks_encrypted(source, fstype):
            continue
        rows.append(
            {
                "path": str(root),
                "mount_point": mount["mount"],
                "source": source,
                "fstype": fstype,
                "risk_level": "medium",
                "risk_reason": "PostgreSQL-sensitive path is not obviously backed by an encrypted block device",
            }
        )
    rows = _dedupe_rows(rows, ("mount_point", "source", "fstype", "risk_reason"))
    return _result(
        rows,
        ok_title="PostgreSQL-sensitive paths appear to use encrypted storage",
        fail_title="Disk encryption posture findings found",
        recommendation="Use OS or volume encryption for PGDATA, tablespaces, WAL archives, and backups where physical media exposure is in scope.",
        diagnostic_code="security_disk_encryption_status",
    )
