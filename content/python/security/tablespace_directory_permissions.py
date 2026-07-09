from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    rows = []
    for tablespace in await _tablespaces(ctx):
        path = Path(str(tablespace["path"]))
        for row in _permission_findings(
            path,
            component="tablespace_directory",
            expected_mode="not group/world writable and not world accessible",
            disallowed_bits=0o027,
            missing_ok=False,
            risk_reason="Tablespace directory permissions are broader than expected",
        ):
            row["tablespace"] = tablespace["name"]
            rows.append(row)
    return _result(
        rows,
        ok_title="Tablespace directory permissions are restrictive",
        fail_title="Tablespace directory permission findings found",
        recommendation="Keep tablespace directories owned by postgres and inaccessible to untrusted OS users.",
        diagnostic_code="security_tablespace_directory_permissions",
    )
