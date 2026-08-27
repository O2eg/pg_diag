from __future__ import annotations

from typing import Any

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result


INSUFFICIENT_PRIVILEGE_SQLSTATE = "42501"
RULE_LIMIT = 3000
# rule_number and file_name were added together with include directives in PostgreSQL 16.
INCLUDE_AWARE_VERSION = 160000


def build_sql(server_version_num: int) -> str:
    if server_version_num >= INCLUDE_AWARE_VERSION:
        order_columns = (
            "r.rule_number::int8 as evaluation_order, r.file_name::text as file_name, "
            "r.rule_number::int8 as rule_number,"
        )
        order_by = "r.rule_number nulls last, r.line_number"
    else:
        order_columns = (
            "r.line_number::int8 as evaluation_order, null::text as file_name, "
            "null::int8 as rule_number,"
        )
        order_by = "r.line_number"
    return f"""
        select
          {order_columns}
          r.line_number::int8 as line_number,
          r.type::text as connection_type,
          array_to_string(r.database, ', ') as databases,
          array_to_string(r.user_name, ', ') as user_names,
          r.address::text as address,
          r.netmask::text as netmask,
          r.auth_method::text as auth_method,
          array_to_string(r.options, ', ') as options,
          r.error::text as error
        from pg_catalog.pg_hba_file_rules r
        order by {order_by}
        limit {RULE_LIMIT + 1}
    """


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    server_version_num = int(await ctx.conn.fetchval("show server_version_num"))
    try:
        records = await ctx.conn.fetch(build_sql(server_version_num))
    except Exception as exc:
        if getattr(exc, "sqlstate", None) != INSUFFICIENT_PRIVILEGE_SQLSTATE:
            raise
        reason = (
            "pg_hba_file_rules requires superuser or an explicit SELECT grant "
            "for the collector role"
        )
        return PythonSourceResult(
            collection_status="unsupported",
            reason=reason,
            result=table_result([]),
            severity_level="unknown",
            diagnostics=[
                {"level": "warning", "code": "roles_hba_rules_permission_denied", "message": reason}
            ],
        )

    truncated = len(records) > RULE_LIMIT
    rows = []
    for record in records[:RULE_LIMIT]:
        row = dict(record)
        error = row.get("error")
        if error:
            row["risk_level"] = "high"
            row["risk_reason"] = "The server could not parse this pg_hba.conf line; it is ignored until the file is corrected"
        elif truncated:
            row["risk_level"] = "unknown"
            row["risk_reason"] = f"More than {RULE_LIMIT} pg_hba.conf rules exist; the rule list is partial"
        else:
            row["risk_level"] = "ok"
            row["risk_reason"] = ""
        row["result_truncated"] = truncated
        rows.append(row)

    error_rows = [row for row in rows if row["risk_level"] == "high"]
    severity_level = "high" if error_rows else ("unknown" if truncated else "ok")
    issues: dict[str, Any] = {}
    if error_rows or truncated:
        issues = {
            "summary": {
                "severity": severity_level,
                "status": "fail" if error_rows else "review",
                "title": (
                    "pg_hba.conf contains lines the server cannot parse"
                    if error_rows
                    else "pg_hba.conf rule list is partial"
                ),
                "description": (
                    f"{len(error_rows)} rule(s) carry a server-side parse error and are ignored by PostgreSQL."
                    if error_rows
                    else f"More than {RULE_LIMIT} rules exist; only the first {RULE_LIMIT} are shown."
                ),
                "recommendation": (
                    "Fix the reported lines and reload PostgreSQL so the intended authentication rules apply."
                    if error_rows
                    else "Review the complete pg_hba.conf on the host."
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
