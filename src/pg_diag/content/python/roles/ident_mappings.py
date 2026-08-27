from __future__ import annotations

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result


INSUFFICIENT_PRIVILEGE_SQLSTATE = "42501"
MAPPING_LIMIT = 3000
# pg_ident_file_mappings exists since PostgreSQL 15; map_number and file_name were
# added together with include directives in PostgreSQL 16.
MIN_SUPPORTED_VERSION = 150000
INCLUDE_AWARE_VERSION = 160000


def build_sql(server_version_num: int) -> str:
    if server_version_num >= INCLUDE_AWARE_VERSION:
        order_columns = (
            "m.map_number::int8 as evaluation_order, m.file_name::text as file_name, "
            "m.map_number::int8 as map_number,"
        )
        order_by = "m.map_number nulls last, m.line_number"
    else:
        order_columns = (
            "m.line_number::int8 as evaluation_order, null::text as file_name, "
            "null::int8 as map_number,"
        )
        order_by = "m.line_number"
    return f"""
        select
          {order_columns}
          m.line_number::int8 as line_number,
          m.map_name::text as map_name,
          m.sys_name::text as system_user_name,
          m.pg_username::text as role_name,
          m.error::text as error
        from pg_catalog.pg_ident_file_mappings m
        order by {order_by}
        limit {MAPPING_LIMIT + 1}
    """


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    server_version_num = int(await ctx.conn.fetchval("show server_version_num"))
    if server_version_num < MIN_SUPPORTED_VERSION:
        reason = "pg_ident_file_mappings exists only on PostgreSQL 15 and newer"
        return PythonSourceResult(
            collection_status="unsupported",
            reason=reason,
            result=table_result([]),
            severity_level="unknown",
            diagnostics=[
                {"level": "warning", "code": "roles_ident_mappings_unsupported", "message": reason}
            ],
        )
    try:
        records = await ctx.conn.fetch(build_sql(server_version_num))
    except Exception as exc:
        if getattr(exc, "sqlstate", None) != INSUFFICIENT_PRIVILEGE_SQLSTATE:
            raise
        reason = (
            "pg_ident_file_mappings requires superuser or an explicit SELECT grant "
            "for the collector role"
        )
        return PythonSourceResult(
            collection_status="unsupported",
            reason=reason,
            result=table_result([]),
            severity_level="unknown",
            diagnostics=[
                {
                    "level": "warning",
                    "code": "roles_ident_mappings_permission_denied",
                    "message": reason,
                }
            ],
        )

    truncated = len(records) > MAPPING_LIMIT
    rows = []
    for record in records[:MAPPING_LIMIT]:
        row = dict(record)
        if row.get("error"):
            row["risk_level"] = "high"
            row["risk_reason"] = "The server could not parse this pg_ident.conf line; it is ignored until the file is corrected"
        else:
            row["risk_level"] = "ok"
            row["risk_reason"] = ""
        row["result_truncated"] = truncated
        rows.append(row)
    if truncated:
        rows.append(
            {
                **{key: None for key in rows[0] if key not in ("risk_level", "risk_reason", "result_truncated")},
                "map_name": "[coverage]",
                "risk_level": "unknown",
                "risk_reason": (
                    f"More than {MAPPING_LIMIT} pg_ident.conf mappings exist; findings above are proven "
                    "but the list is incomplete"
                ),
                "result_truncated": True,
            }
        )

    error_rows = [row for row in rows if row["risk_level"] == "high"]
    severity_level = "high" if error_rows else ("unknown" if truncated else "ok")
    issues = {}
    if error_rows or truncated:
        issues = {
            "summary": {
                "severity": severity_level,
                "status": "fail" if error_rows else "review",
                "title": (
                    "pg_ident.conf contains lines the server cannot parse"
                    if error_rows
                    else "pg_ident.conf mapping list is partial"
                ),
                "description": (
                    f"{len(error_rows)} mapping(s) carry a server-side parse error and are ignored by PostgreSQL."
                    if error_rows
                    else f"More than {MAPPING_LIMIT} mappings exist; only the first {MAPPING_LIMIT} are shown."
                ),
                "recommendation": (
                    "Fix the reported lines and reload PostgreSQL so the intended user-name maps apply."
                    if error_rows
                    else "Review the complete pg_ident.conf on the host."
                ),
            },
            "items": [],
        }
    return PythonSourceResult(
        collection_status="ok" if rows else "empty",
        result=table_result(rows),
        issues=issues,
        severity_level=severity_level,
    )
