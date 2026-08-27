from __future__ import annotations

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result


INSUFFICIENT_PRIVILEGE_SQLSTATE = "42501"
SUBSCRIPTION_LIMIT = 1000

# Only publicly readable columns are selected; the connection string column can contain a password
# and is never read.
SQL = f"""
    with subscriptions_bounded as (
      select
        s.oid,
        s.subdbid,
        s.subname,
        s.subowner,
        s.subenabled,
        s.subslotname,
        s.subpublications
      from pg_catalog.pg_subscription s
      order by s.subdbid, s.subname, s.oid
      limit {SUBSCRIPTION_LIMIT + 1}
    )
    select
      d.datname::text as database_name,
      s.subname::text as subscription_name,
      pg_catalog.pg_get_userbyid(s.subowner)::text as owner_name,
      coalesce(r.rolcanlogin, false) as owner_can_login,
      coalesce(r.rolsuper, false) as owner_is_superuser,
      s.subenabled as enabled,
      s.subslotname::text as slot_name,
      array_to_string(s.subpublications, ', ') as publications,
      (d.datname = current_database()) as in_current_database
    from subscriptions_bounded s
    left join pg_catalog.pg_database d on d.oid = s.subdbid
    left join pg_catalog.pg_roles r on r.oid = s.subowner
    order by database_name, subscription_name
"""


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    try:
        records = await ctx.conn.fetch(SQL)
    except Exception as exc:
        if getattr(exc, "sqlstate", None) != INSUFFICIENT_PRIVILEGE_SQLSTATE:
            raise
        reason = (
            "pg_subscription is readable only by superusers on PostgreSQL 14 and older; "
            "grant SELECT on its public columns or use PostgreSQL 15 and newer"
        )
        code = "roles_subscription_ownership_permission_denied"
        return PythonSourceResult(
            collection_status="unsupported",
            reason=reason,
            result=table_result([]),
            severity_level="unknown",
            diagnostics=[{"level": "warning", "code": code, "message": reason}],
        )

    truncated = len(records) > SUBSCRIPTION_LIMIT
    rows = []
    for record in records[:SUBSCRIPTION_LIMIT]:
        row = dict(record)
        row["result_truncated"] = truncated
        rows.append(row)

    severity_level = "unknown" if truncated else "ok"
    issues = {}
    if truncated:
        issues = {
            "summary": {
                "severity": severity_level,
                "status": "review",
                "title": "Subscription ownership coverage requires review",
                "description": (
                    f"More than {SUBSCRIPTION_LIMIT} subscriptions exist; "
                    f"only the first {SUBSCRIPTION_LIMIT} are shown."
                ),
                "recommendation": "Inspect pg_subscription directly for the complete list.",
            },
            "items": [],
        }
    return PythonSourceResult(
        collection_status="ok" if rows else "empty",
        result=table_result(rows),
        issues=issues,
        severity_level=severity_level,
    )
