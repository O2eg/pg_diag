from __future__ import annotations

import asyncio
from typing import Any

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result


DATABASE_SIZE_TIMEOUT_SECONDS = 10.0
DATABASE_SIZE_TIMEOUT_REASON = "Database size calculation exceeded 10 seconds"

DATABASES_SQL = """
select
  oid::int8 as database_oid,
  datname::text as database_name,
  datallowconn as allows_connections,
  pg_catalog.has_database_privilege(current_user, datname, 'CONNECT') as can_connect
from pg_catalog.pg_database
order by datname
"""

ENTITY_COUNTS_SQL = """
with user_namespaces as (
  select oid
  from pg_catalog.pg_namespace
  where nspname <> 'information_schema'
    and nspname <> 'pg_catalog'
    and nspname not like 'pg_toast%'
    and nspname not like 'pg_temp_%'
),
relation_counts as (
  select
    count(*) filter (
      where c.relkind in ('r', 'p') and not c.relispartition
    )::int8 as tables,
    count(*) filter (
      where c.relkind = 'p' and not c.relispartition
    )::int8 as partitioned_tables,
    count(*) filter (
      where c.relkind in ('r', 'p') and c.relispartition
    )::int8 as partitions,
    count(*) filter (
      where c.relkind in ('i', 'I') and not c.relispartition
    )::int8 as indexes,
    count(*) filter (
      where c.relkind = 'I' and not c.relispartition
    )::int8 as partitioned_indexes,
    count(*) filter (
      where c.relkind in ('i', 'I') and c.relispartition
    )::int8 as index_partitions,
    count(*) filter (where c.relkind = 'v')::int8 as views,
    count(*) filter (where c.relkind = 'm')::int8 as materialized_views,
    count(*) filter (where c.relkind = 'S')::int8 as sequences,
    count(*) filter (
      where c.relkind = 'f' and not c.relispartition
    )::int8 as foreign_tables,
    count(*) filter (where c.relkind = 'c')::int8 as composite_types
  from pg_catalog.pg_class c
  join user_namespaces n on n.oid = c.relnamespace
),
routine_counts as (
  select
    count(*) filter (where p.prokind = 'f')::int8 as functions,
    count(*) filter (where p.prokind = 'p')::int8 as procedures,
    count(*) filter (where p.prokind = 'a')::int8 as aggregates,
    count(*) filter (where p.prokind = 'w')::int8 as window_functions
  from pg_catalog.pg_proc p
  join user_namespaces n on n.oid = p.pronamespace
),
type_counts as (
  select
    count(*) filter (where t.typtype = 'e')::int8 as enum_types,
    count(*) filter (where t.typtype in ('r', 'm'))::int8 as range_types,
    count(*) filter (where t.typtype = 'd')::int8 as domains
  from pg_catalog.pg_type t
  join user_namespaces n on n.oid = t.typnamespace
),
trigger_counts as (
  select count(*)::int8 as triggers
  from pg_catalog.pg_trigger t
  join pg_catalog.pg_class c on c.oid = t.tgrelid
  join user_namespaces n on n.oid = c.relnamespace
  where not t.tgisinternal
    and not c.relispartition
),
constraint_counts as (
  select count(*)::int8 as constraints
  from pg_catalog.pg_constraint c
  join user_namespaces n on n.oid = c.connamespace
  left join pg_catalog.pg_class r on r.oid = c.conrelid
  where c.conparentid = 0
    and (c.conrelid = 0 or not r.relispartition)
),
policy_counts as (
  select count(*)::int8 as row_security_policies
  from pg_catalog.pg_policy p
  join pg_catalog.pg_class c on c.oid = p.polrelid
  join user_namespaces n on n.oid = c.relnamespace
  where not c.relispartition
),
rule_counts as (
  select count(*)::int8 as rules
  from pg_catalog.pg_rewrite r
  join pg_catalog.pg_class c on c.oid = r.ev_class
  join user_namespaces n on n.oid = c.relnamespace
  where r.rulename <> '_RETURN'
    and not c.relispartition
)
select
  (select count(*)::int8 from user_namespaces) as schemas,
  rc.tables,
  rc.partitioned_tables,
  rc.partitions,
  rc.indexes,
  rc.partitioned_indexes,
  rc.index_partitions,
  rc.views,
  rc.materialized_views,
  rc.sequences,
  rc.foreign_tables,
  rc.composite_types,
  routines.functions,
  routines.procedures,
  routines.aggregates,
  routines.window_functions,
  triggers.triggers,
  constraints.constraints,
  types.enum_types,
  types.range_types,
  types.domains,
  policies.row_security_policies,
  rules.rules,
  (select count(*)::int8 from pg_catalog.pg_extension) as extensions,
  (select count(*)::int8 from pg_catalog.pg_event_trigger) as event_triggers,
  (select count(*)::int8 from pg_catalog.pg_publication) as publications,
  (select count(*)::int8 from pg_catalog.pg_subscription) as subscriptions,
  (select count(*)::int8 from pg_catalog.pg_foreign_data_wrapper) as foreign_data_wrappers,
  (select count(*)::int8 from pg_catalog.pg_foreign_server) as foreign_servers,
  (select count(*)::int8
   from pg_catalog.pg_collation c
   join user_namespaces n on n.oid = c.collnamespace) as collations,
  (select count(*)::int8
   from pg_catalog.pg_conversion c
   join user_namespaces n on n.oid = c.connamespace) as conversions,
  (select count(*)::int8
   from pg_catalog.pg_statistic_ext s
   join user_namespaces n on n.oid = s.stxnamespace) as extended_statistics,
  (select count(*)::int8 from pg_catalog.pg_largeobject_metadata) as large_objects
from relation_counts rc
cross join routine_counts routines
cross join type_counts types
cross join trigger_counts triggers
cross join constraint_counts constraints
cross join policy_counts policies
cross join rule_counts rules
"""

COUNT_COLUMNS = (
    "schemas",
    "tables",
    "partitioned_tables",
    "partitions",
    "indexes",
    "partitioned_indexes",
    "index_partitions",
    "views",
    "materialized_views",
    "sequences",
    "foreign_tables",
    "composite_types",
    "functions",
    "procedures",
    "aggregates",
    "window_functions",
    "triggers",
    "constraints",
    "enum_types",
    "range_types",
    "domains",
    "row_security_policies",
    "rules",
    "extensions",
    "event_triggers",
    "publications",
    "subscriptions",
    "foreign_data_wrappers",
    "foreign_servers",
    "collations",
    "conversions",
    "extended_statistics",
    "large_objects",
)


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    async with ctx.conn.transaction(readonly=True):
        databases = await ctx.conn.fetch(DATABASES_SQL)

    rows = []
    diagnostics = []
    for database in databases:
        source = dict(database)
        database_name = str(source["database_name"])
        row = _empty_row(database_name)
        if not source.get("allows_connections"):
            await _collect_size_from_main_connection(ctx, source, row)
            row["collection_status"] = "connections disabled"
        elif not source.get("can_connect"):
            await _collect_size_from_main_connection(ctx, source, row)
            row["collection_status"] = "CONNECT privilege is unavailable"
        else:
            try:
                async with ctx.connect_database(
                    database_name,
                    timeout_seconds=DATABASE_SIZE_TIMEOUT_SECONDS,
                ) as database_conn:
                    await _collect_connected_database(database_conn, row)
            except Exception as exc:
                await _collect_size_from_main_connection(ctx, source, row)
                row["collection_status"] = f"connection failed: {_error_text(exc)}"

        if row["collection_status"] != "ok":
            diagnostics.append(
                {
                    "level": "warning",
                    "code": "database_volume_partial_row",
                    "message": f"{database_name}: {row['collection_status']}",
                }
            )
        rows.append(row)

    rows.sort(key=_size_sort_key, reverse=True)
    cell_statuses = []
    for row_index, row in enumerate(rows):
        status = row.pop("_database_size_status", None)
        if status:
            cell_statuses.append(
                {
                    "row_index": row_index,
                    "column": "database_size_bytes",
                    **status,
                }
            )
    result = table_result(rows)
    if cell_statuses:
        result["cell_statuses"] = cell_statuses
    return PythonSourceResult(
        collection_status="ok" if rows else "empty",
        result=result,
        severity_level="unknown",
        diagnostics=diagnostics,
    )


async def _collect_connected_database(conn: Any, row: dict[str, Any]) -> None:
    try:
        row["database_size_bytes"] = await _database_size(conn)
    except TimeoutError:
        row["database_size_bytes"] = None
        row["_database_size_status"] = {
            "status": "timeout",
            "reason": DATABASE_SIZE_TIMEOUT_REASON,
        }
        row["collection_status"] = "database size timed out"
    except Exception as exc:
        row["database_size_bytes"] = None
        row["_database_size_status"] = {
            "status": "error",
            "reason": f"Database size calculation failed: {_error_text(exc)}",
        }
        row["collection_status"] = "database size failed"

    try:
        async with conn.transaction(readonly=True):
            counts = await conn.fetchrow(ENTITY_COUNTS_SQL)
        row.update(dict(counts))
    except Exception as exc:
        status = f"entity count failed: {_error_text(exc)}"
        row["collection_status"] = _merge_status(row["collection_status"], status)


async def _collect_size_from_main_connection(
    ctx: PythonSourceContext,
    database: dict[str, Any],
    row: dict[str, Any],
) -> None:
    try:
        row["database_size_bytes"] = await _database_size(
            ctx.conn,
            int(database["database_oid"]),
        )
    except TimeoutError:
        row["database_size_bytes"] = None
        row["_database_size_status"] = {
            "status": "timeout",
            "reason": DATABASE_SIZE_TIMEOUT_REASON,
        }
    except Exception as exc:
        row["database_size_bytes"] = None
        row["_database_size_status"] = {
            "status": "error",
            "reason": f"Database size calculation failed: {_error_text(exc)}",
        }


async def _database_size(conn: Any, database_oid: int | None = None) -> int:
    if database_oid is None:
        sql = "select pg_catalog.pg_database_size(pg_catalog.current_database())::int8"
        args: tuple[Any, ...] = ()
    else:
        sql = "select pg_catalog.pg_database_size($1::oid)::int8"
        args = (database_oid,)
    async with conn.transaction(readonly=True):
        value = await asyncio.wait_for(
            conn.fetchval(sql, *args),
            timeout=DATABASE_SIZE_TIMEOUT_SECONDS,
        )
    return int(value)


def _empty_row(database_name: str) -> dict[str, Any]:
    return {
        "database_name": database_name,
        "database_size_bytes": None,
        **dict.fromkeys(COUNT_COLUMNS),
        "collection_status": "ok",
    }


def _size_sort_key(row: dict[str, Any]) -> tuple[bool, int]:
    value = row.get("database_size_bytes")
    is_integer = isinstance(value, int) and not isinstance(value, bool)
    return is_integer, value if is_integer else -1


def _merge_status(current: str, additional: str) -> str:
    return additional if current == "ok" else f"{current}; {additional}"


def _error_text(exc: Exception) -> str:
    message = " ".join(str(exc).split())
    return (message or type(exc).__name__)[:300]
