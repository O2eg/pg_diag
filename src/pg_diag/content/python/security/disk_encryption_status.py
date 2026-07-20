from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    roots = await _sensitive_roots(ctx)
    if not roots:
        return _unavailable_result(
            "No PostgreSQL-sensitive local root could be derived from server settings",
            "security_sensitive_roots_unavailable",
        )
    rows = []
    mounts = await _host_mount_table(ctx)
    encrypted_sources = await _host_encrypted_block_sources(ctx)
    if not mounts:
        return _unavailable_result(
            "The local mount table could not be read",
            "security_mount_table_unavailable",
        )
    if encrypted_sources is None:
        return _unavailable_result(
            "lsblk evidence is unavailable; device-mapper names alone do not prove encryption",
            "security_block_encryption_evidence_unavailable",
        )
    for root in roots:
        mount = await _host_mount_for_path(ctx, root, mounts)
        if not mount:
            rows.append(
                {
                    "path": str(root),
                    "mount_point": "",
                    "source": "",
                    "fstype": "",
                    "risk_level": "medium",
                    "risk_reason": "No containing mount could be identified for a PostgreSQL-sensitive path",
                }
            )
            continue
        source = mount["source"]
        fstype = mount["fstype"]
        if _source_is_confirmed_encrypted(source, fstype, encrypted_sources):
            continue
        rows.append(
            {
                "path": str(root),
                "mount_point": mount["mount"],
                "source": source,
                "fstype": fstype,
                "risk_level": "medium",
                "risk_reason": "Encryption was not confirmed for the PostgreSQL-sensitive mount",
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
