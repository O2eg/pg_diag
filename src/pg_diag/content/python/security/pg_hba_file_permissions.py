from __future__ import annotations

from _local_security_common import *
from _pg_hba_common import _host_read_hba_paths


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    hba_file = await ctx.conn.fetchval("select setting from pg_settings where name = 'hba_file'")
    if not hba_file:
        return _unavailable_result("PostgreSQL hba_file setting is empty or unavailable", "security_hba_file_empty")
    hba_path = Path(str(hba_file))
    try:
        files, directories = await _host_read_hba_paths(ctx.host, hba_path)
    except FileNotFoundError:
        return _unavailable_result(
            f"An HBA file included from {hba_path} is not visible locally",
            "security_hba_file_missing",
        )
    except PermissionError:
        return _unavailable_result(
            f"The collector cannot read an HBA file or include directory from {hba_path}",
            "security_hba_file_permission",
        )

    rows = []
    for path in sorted(files):
        rows.extend(await _permission_rows(ctx, path, object_type="file"))
    for path in sorted(directories):
        rows.extend(await _permission_rows(ctx, path, object_type="include_directory"))

    return _result(
        rows,
        ok_title="HBA file and include permissions are restrictive",
        fail_title="HBA file or include permissions are too broad",
        recommendation=(
            "Prevent group/other writes to every HBA file and include directory, disallow other-user file access, "
            "and keep administration ownership explicit."
        ),
        diagnostic_code="security_pg_hba_file_permissions",
    )


async def _permission_rows(
    ctx: PythonSourceContext,
    path: Path,
    *,
    object_type: str,
) -> list[dict[str, Any]]:
    try:
        mode = stat.S_IMODE((await ctx.host.stat(path)).mode)
    except (FileNotFoundError, PermissionError, OSError) as exc:
        return [
            {
                "file_path": str(path),
                "object_type": object_type,
                "file_mode": "",
                "expected_file_mode": "locally visible and stat-able",
                "risk_level": "unknown",
                "risk_reason": f"cannot verify HBA path permissions: {exc}",
            }
        ]

    unsafe_write = bool(mode & 0o022)
    unexpected_access = bool(mode & (0o007 if object_type == "file" else 0o002))
    group_execute_on_file = object_type == "file" and bool(mode & 0o010)
    if not (unsafe_write or unexpected_access or group_execute_on_file):
        return []
    return [
        {
            "file_path": str(path),
            "object_type": object_type,
            "file_mode": _octal(mode),
            "expected_file_mode": (
                "no group/other write and no other file access; 0600/0640 are typical"
                if object_type == "file"
                else "include directory not writable by group/other"
            ),
            "risk_level": "high" if unsafe_write else "medium",
            "risk_reason": (
                "HBA path is writable outside its owner"
                if unsafe_write else "HBA file grants unexpected group execute or other access"
            ),
        }
    ]
