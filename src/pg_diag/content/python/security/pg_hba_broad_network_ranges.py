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
        if row is None or row["connection_type"] not in HOST_TYPES or row["auth_method"] == "reject":
            continue
        classification = _network_range_risk(str(row["address"]))
        if classification is None:
            continue
        risk_level, risk_reason = classification
        row["network_scope"] = _network_scope(str(row["address"]))
        row["risk_level"] = risk_level
        row["risk_reason"] = risk_reason
        rows.append(row)
    return _result(
        rows,
        hba_path,
        ok_title="No overly broad pg_hba.conf network ranges found",
        fail_title="Overly broad pg_hba.conf network ranges found",
        recommendation=(
            "Replace universal or very broad host ranges with the smallest required CIDR ranges "
            "and keep loopback-only rules separate from remote client rules."
        ),
    )
