from __future__ import annotations

from _pg_hba_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    try:
        hba_entries, hba_path = await _read_hba_from_context(ctx)
    except (FileNotFoundError, PermissionError) as exc:
        return _unavailable_result(str(exc), _unavailable_code(exc))
    rows = []
    for entry in hba_entries:
        row = _entry_row(entry)
        if row is None or row["auth_method"] == "reject":
            continue
        generic_fields = []
        if "all" in _split_csv(row["database"]):
            generic_fields.append("database")
        if "all" in _split_csv(row["user"]):
            generic_fields.append("user")
        if not generic_fields:
            continue
        row["generic_fields"] = ", ".join(generic_fields)
        row["network_scope"] = _network_scope(str(row["address"]))
        row["risk_level"] = "high" if (
            row["connection_type"] in HOST_TYPES
            and row["network_scope"] not in {"loopback", "samehost", "unknown"}
            and len(generic_fields) == 2
        ) else "medium"
        row["risk_reason"] = "pg_hba.conf rule uses broad database/user matching"
        rows.append(row)
    return _result(
        rows,
        hba_path,
        ok_title="No generic pg_hba.conf database/user fields found",
        fail_title="Generic pg_hba.conf database/user fields found",
        recommendation=(
            "Prefer explicit database and user fields in pg_hba.conf rules. Use all/all only when the access policy "
            "is intentionally broad and compensated by a narrow address range and strong authentication."
        ),
    )
