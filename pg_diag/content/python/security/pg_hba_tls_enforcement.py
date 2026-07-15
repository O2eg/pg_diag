from __future__ import annotations

from _pg_hba_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    try:
        hba_entries, hba_path = await _read_hba_from_context(ctx)
    except (FileNotFoundError, PermissionError) as exc:
        return _unavailable_result(str(exc), _unavailable_code(exc))
    ssl_setting = await ctx.conn.fetchval("select setting from pg_settings where name = 'ssl'")
    rows = []
    for entry in hba_entries:
        row = _entry_row(entry)
        if row is None or row["connection_type"] not in {"host", "hostnossl"} or row["auth_method"] == "reject":
            continue
        network_scope = _network_scope(str(row["address"]))
        if network_scope in {"loopback", "samehost", "unknown"}:
            continue
        row["network_scope"] = network_scope
        row["server_ssl"] = str(ssl_setting or "")
        row["risk_level"] = "high"
        row["risk_reason"] = "non-loopback host rule does not enforce TLS/GSS encryption"
        rows.append(row)
    return _result(
        rows,
        hba_path,
        ok_title="No non-loopback pg_hba.conf rules bypassing TLS enforcement found",
        fail_title="Non-loopback pg_hba.conf rules do not enforce TLS",
        recommendation=(
            "Use hostssl or hostgssenc for remote client rules and reject or remove plain host/hostnossl rules "
            "that can match non-loopback clients."
        ),
    )
