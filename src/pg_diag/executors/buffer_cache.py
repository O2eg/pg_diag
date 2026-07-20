"""Version-aware batch collector for pg_buffercache snapshot sources."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

SUMMARY_SOURCE_IDS = frozenset(
    {
        "buffer_cache.utilization",
        "buffer_cache.usage_count_distribution",
        "buffer_cache.dirty_and_pinned",
    }
)
DETAIL_SOURCE_IDS = frozenset(
    {
        "buffer_cache.by_database",
        "buffer_cache.top_relations",
        "buffer_cache.top_dirty_relations",
    }
)
BUFFER_CACHE_SOURCE_IDS = SUMMARY_SOURCE_IDS | DETAIL_SOURCE_IDS
RELATION_SOURCE_IDS = frozenset(
    {
        "buffer_cache.top_relations",
        "buffer_cache.top_dirty_relations",
    }
)
DATABASE_SOURCE_IDS = frozenset({"buffer_cache.by_database"})
FAST_SUMMARY_SQL_FILES = frozenset(
    {
        "buffer_cache/utilization_pg16_plus.sql",
        "buffer_cache/usage_count_distribution_pg16_plus.sql",
        "buffer_cache/dirty_and_pinned_pg16_plus.sql",
    }
)

CAPABILITY_SQL = """
/* pg_diag:buffer_cache:capabilities */
select
  coalesce(
    bool_or(
      procedure_record.proname = 'pg_buffercache_summary'
      and pg_catalog.has_function_privilege(
        current_user,
        procedure_record.oid,
        'EXECUTE'
      )
    ),
    false
  ) as has_summary,
  coalesce(
    bool_or(
      procedure_record.proname = 'pg_buffercache_usage_counts'
      and pg_catalog.has_function_privilege(
        current_user,
        procedure_record.oid,
        'EXECUTE'
      )
    ),
    false
  ) as has_usage_counts
from pg_catalog.pg_proc procedure_record
join pg_catalog.pg_namespace namespace_record
  on namespace_record.oid = procedure_record.pronamespace
where namespace_record.nspname = 'public'
  and procedure_record.proname in (
    'pg_buffercache_summary',
    'pg_buffercache_usage_counts'
  )
  and procedure_record.pronargs = 0
"""

FAST_SUMMARY_SQL = """
/* pg_diag:buffer_cache:fast_summary */
select
  statement_timestamp() as snapshot_time,
  buffers_used::int8 as buffers_used,
  buffers_unused::int8 as buffers_unused,
  buffers_dirty::int8 as buffers_dirty,
  buffers_pinned::int8 as buffers_pinned
from public.pg_buffercache_summary()
"""

FAST_USAGE_COUNTS_SQL = """
/* pg_diag:buffer_cache:fast_usage_counts */
select
  statement_timestamp() as snapshot_time,
  usage_count::int4 as usage_count,
  buffers::int8 as buffers,
  dirty::int8 as dirty,
  pinned::int8 as pinned
from public.pg_buffercache_usage_counts()
order by usage_count
"""

METADATA_SQL = """
/* pg_diag:buffer_cache:metadata */
select
  statement_timestamp() as snapshot_time,
  current_database_record.oid::int8 as current_database_oid,
  database_record.oid::int8 as database_oid,
  database_record.datname as database_name
from pg_catalog.pg_database database_record
cross join lateral (
  select oid
  from pg_catalog.pg_database
  where datname = pg_catalog.current_database()
) current_database_record
order by database_record.oid
"""

RESOLVE_SQL = """
/* pg_diag:buffer_cache:resolve */
with physical_keys as (
  select *
  from unnest($1::oid[], $2::oid[]) as keys(reltablespace, relfilenode)
), resolved as (
  select
    reltablespace,
    relfilenode,
    pg_catalog.pg_filenode_relation(reltablespace, relfilenode) as relation_oid
  from physical_keys
)
select
  resolved.reltablespace::int8 as reltablespace,
  resolved.relfilenode::int8 as relfilenode,
  resolved.relation_oid::text as relation_name
from resolved
"""


@dataclass(frozen=True)
class AggregateRow:
    reltablespace: int | None
    reldatabase: int | None
    relfilenode: int | None
    relforknumber: int | None
    isdirty: bool
    usagecount: int | None
    is_pinned: bool
    buffers: int


@dataclass(frozen=True)
class FastSummary:
    snapshot_time: Any
    buffers_used: int
    buffers_unused: int
    buffers_dirty: int
    buffers_pinned: int


@dataclass(frozen=True)
class UsageCountRow:
    snapshot_time: Any
    usage_count: int
    buffers: int
    dirty: int
    pinned: int


@dataclass(frozen=True)
class FastCapabilities:
    has_summary: bool = False
    has_usage_counts: bool = False


@dataclass(frozen=True)
class ResolvedRelation:
    relation_name: str | None


@dataclass
class BufferCachePayload:
    snapshot_time: Any
    current_database_oid: int | None
    database_names: dict[int, str]
    aggregates: list[AggregateRow]
    resolved: dict[tuple[int, int], ResolvedRelation]
    relation_candidate_keys: dict[str, frozenset[tuple[int, int]]] = field(
        default_factory=dict
    )


class BufferCacheBatchProvider:
    """Share pg_buffercache work within one snapshot query batch."""

    def __init__(
        self,
        source_ids: Iterable[str],
        *,
        prefer_fast_summary: bool = False,
    ) -> None:
        self.source_ids = frozenset(source_ids) & BUFFER_CACHE_SOURCE_IDS
        self.prefer_fast_summary = prefer_fast_summary
        self._fast_capability_checked = False
        self._fast_capabilities = FastCapabilities()
        self._summary: FastSummary | None = None
        self._summary_error: BaseException | None = None
        self._usage_counts: list[UsageCountRow] | None = None
        self._usage_counts_error: BaseException | None = None
        self._detail_payload: BufferCachePayload | None = None
        self._detail_error: BaseException | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.source_ids)

    def handles(self, source_id: str | None) -> bool:
        return bool(source_id and source_id in self.source_ids)

    async def result_for(
        self,
        conn: Any,
        source_id: str,
    ) -> tuple[list[dict[str, Any]], list[list[Any]]]:
        if source_id not in self.source_ids:
            raise KeyError(f"Buffer-cache source is not part of this batch: {source_id}")

        capabilities = await self._get_fast_capabilities(conn)
        if source_id == "buffer_cache.utilization" and capabilities.has_summary:
            return _build_fast_utilization(await self._get_fast_summary(conn))
        if source_id == "buffer_cache.usage_count_distribution" and (
            capabilities.has_summary and capabilities.has_usage_counts
        ):
            summary = await self._get_fast_summary(conn)
            usage_counts = await self._get_fast_usage_counts(conn)
            return _build_fast_usage_count_distribution(summary, usage_counts)
        if source_id == "buffer_cache.dirty_and_pinned":
            if capabilities.has_summary:
                return _build_fast_dirty_and_pinned(await self._get_fast_summary(conn))
            if capabilities.has_usage_counts:
                return _build_fast_dirty_and_pinned_from_usage_counts(
                    await self._get_fast_usage_counts(conn)
                )

        payload = await self._get_detail_payload(conn)
        return build_result(source_id, payload)

    async def _get_fast_capabilities(self, conn: Any) -> FastCapabilities:
        if not self.prefer_fast_summary:
            return FastCapabilities()
        if self._fast_capability_checked:
            return self._fast_capabilities
        self._fast_capability_checked = True
        try:
            # A failed SQL statement aborts the current PostgreSQL transaction.
            # Probe in its own savepoint so a legacy fallback can still execute.
            async with conn.transaction(readonly=True):
                records = await conn.fetch(CAPABILITY_SQL)
            first = records[0] if records else None
            self._fast_capabilities = FastCapabilities(
                has_summary=bool(
                    first is not None and _record_value(first, "has_summary")
                ),
                has_usage_counts=bool(
                    first is not None and _record_value(first, "has_usage_counts")
                ),
            )
        except Exception:
            self._fast_capabilities = FastCapabilities()
        return self._fast_capabilities

    async def _get_fast_summary(self, conn: Any) -> FastSummary:
        if self._summary is not None:
            return self._summary
        if self._summary_error is not None:
            raise self._summary_error
        try:
            records = await conn.fetch(FAST_SUMMARY_SQL)
            if not records:
                raise RuntimeError("pg_buffercache_summary() returned no row")
            first = records[0]
            summary = FastSummary(
                snapshot_time=_record_value(first, "snapshot_time"),
                buffers_used=int(_record_value(first, "buffers_used")),
                buffers_unused=int(_record_value(first, "buffers_unused")),
                buffers_dirty=int(_record_value(first, "buffers_dirty")),
                buffers_pinned=int(_record_value(first, "buffers_pinned")),
            )
        except BaseException as exc:
            self._summary_error = exc
            raise
        self._summary = summary
        return summary

    async def _get_fast_usage_counts(self, conn: Any) -> list[UsageCountRow]:
        if self._usage_counts is not None:
            return self._usage_counts
        if self._usage_counts_error is not None:
            raise self._usage_counts_error
        try:
            records = await conn.fetch(FAST_USAGE_COUNTS_SQL)
            usage_counts = [
                UsageCountRow(
                    snapshot_time=_record_value(record, "snapshot_time"),
                    usage_count=int(_record_value(record, "usage_count")),
                    buffers=int(_record_value(record, "buffers")),
                    dirty=int(_record_value(record, "dirty")),
                    pinned=int(_record_value(record, "pinned")),
                )
                for record in records
            ]
        except BaseException as exc:
            self._usage_counts_error = exc
            raise
        self._usage_counts = usage_counts
        return usage_counts

    async def _get_detail_payload(self, conn: Any) -> BufferCachePayload:
        if self._detail_payload is not None:
            return self._detail_payload
        if self._detail_error is not None:
            raise self._detail_error
        try:
            capabilities = await self._get_fast_capabilities(conn)
            payload_source_ids = frozenset(
                source_id
                for source_id in self.source_ids
                if not _uses_fast_source(source_id, capabilities)
            )
            aggregate_sql = _aggregate_sql(payload_source_ids)
            payload = await _collect_detail_payload(
                conn,
                payload_source_ids,
                aggregate_sql,
            )
        except BaseException as exc:
            self._detail_error = exc
            raise
        self._detail_payload = payload
        return payload


def _uses_fast_source(source_id: str, capabilities: FastCapabilities) -> bool:
    if source_id == "buffer_cache.utilization":
        return capabilities.has_summary
    if source_id == "buffer_cache.usage_count_distribution":
        return capabilities.has_summary and capabilities.has_usage_counts
    if source_id == "buffer_cache.dirty_and_pinned":
        return capabilities.has_summary or capabilities.has_usage_counts
    return False


def _aggregate_sql(source_ids: frozenset[str]) -> str:
    """Build the narrowest shared pg_buffercache aggregate for selected sources."""
    if not source_ids:
        raise ValueError("No buffer-cache sources require a detailed aggregate")

    needs_physical_identity = bool(source_ids & RELATION_SOURCE_IDS)
    needs_database = bool(source_ids & (DATABASE_SOURCE_IDS | RELATION_SOURCE_IDS))
    needs_utilization = "buffer_cache.utilization" in source_ids
    needs_usage = "buffer_cache.usage_count_distribution" in source_ids
    needs_dirty_summary = "buffer_cache.dirty_and_pinned" in source_ids
    needs_top_dirty = "buffer_cache.top_dirty_relations" in source_ids
    needs_dirty_dimension = needs_dirty_summary or (needs_top_dirty and len(source_ids) > 1)

    select_expressions = ["statement_timestamp() as snapshot_time"]
    group_expressions: list[str] = []

    if needs_physical_identity:
        select_expressions.append("reltablespace")
        group_expressions.append("reltablespace")
    else:
        select_expressions.append("null::oid as reltablespace")

    if needs_database:
        select_expressions.append("reldatabase")
        group_expressions.append("reldatabase")
    else:
        select_expressions.append("null::oid as reldatabase")

    if needs_physical_identity:
        select_expressions.append("relfilenode")
        group_expressions.append("relfilenode")
    elif needs_utilization:
        used_marker = "case when relfilenode is null then null::oid else 1::oid end"
        select_expressions.append(f"{used_marker} as relfilenode")
        group_expressions.append(used_marker)
    elif source_ids & DATABASE_SOURCE_IDS:
        select_expressions.append("1::oid as relfilenode")
    else:
        select_expressions.append("null::oid as relfilenode")

    # No remaining chart distinguishes relation forks.
    select_expressions.append("null::int2 as relforknumber")

    if needs_dirty_dimension:
        select_expressions.append("isdirty")
        group_expressions.append("isdirty")
    elif needs_top_dirty:
        select_expressions.append("true as isdirty")
    else:
        select_expressions.append("false as isdirty")

    if needs_usage:
        select_expressions.append("usagecount")
        group_expressions.append("usagecount")
    else:
        select_expressions.append("null::int2 as usagecount")

    if needs_dirty_summary:
        pinned_expression = "(pinning_backends > 0)"
        select_expressions.append(f"{pinned_expression} as is_pinned")
        group_expressions.append(pinned_expression)
    else:
        select_expressions.append("false as is_pinned")

    select_expressions.append("count(*)::int8 as buffers")

    where_conditions: list[str] = []
    if not needs_utilization:
        where_conditions.append("relfilenode is not null")
    if source_ids <= RELATION_SOURCE_IDS:
        where_conditions.append(
            "reldatabase = (select oid from pg_catalog.pg_database "
            "where datname = pg_catalog.current_database())"
        )
    if source_ids == {"buffer_cache.top_dirty_relations"}:
        where_conditions.append("isdirty")

    marker = "aggregate_legacy" if source_ids & SUMMARY_SOURCE_IDS else "aggregate_detail"
    lines = [
        f"/* pg_diag:buffer_cache:{marker} */",
        "select",
        "  " + ",\n  ".join(select_expressions),
        "from public.pg_buffercache",
    ]
    if where_conditions:
        lines.append("where " + "\n  and ".join(where_conditions))
    if group_expressions:
        lines.append("group by " + ", ".join(group_expressions))
    return "\n".join(lines)


async def _collect_detail_payload(
    conn: Any,
    source_ids: frozenset[str],
    aggregate_sql: str,
) -> BufferCachePayload:
    aggregate_records = await conn.fetch(aggregate_sql)
    needs_metadata = bool(source_ids & (DATABASE_SOURCE_IDS | RELATION_SOURCE_IDS))
    metadata_records = await conn.fetch(METADATA_SQL) if needs_metadata else []
    if needs_metadata and not metadata_records:
        raise RuntimeError("Cannot resolve current database metadata for pg_buffercache")
    if not aggregate_records and not metadata_records:
        raise RuntimeError("pg_buffercache aggregate returned no rows")

    metadata_first = metadata_records[0] if metadata_records else None
    snapshot_time = _record_value(aggregate_records[0], "snapshot_time") if aggregate_records else (
        _record_value(metadata_first, "snapshot_time")
    )
    aggregates = [_aggregate_row(record) for record in aggregate_records]
    database_names = {
        int(_record_value(record, "database_oid")): str(_record_value(record, "database_name"))
        for record in metadata_records
    }
    payload = BufferCachePayload(
        snapshot_time=snapshot_time,
        current_database_oid=(
            int(_record_value(metadata_first, "current_database_oid"))
            if metadata_first is not None
            else None
        ),
        database_names=database_names,
        aggregates=aggregates,
        resolved={},
    )

    if source_ids & RELATION_SOURCE_IDS:
        payload.relation_candidate_keys = _relation_candidate_keys(payload, source_ids)
        physical_keys = sorted(
            set().union(*payload.relation_candidate_keys.values())
            if payload.relation_candidate_keys
            else set()
        )
        if physical_keys:
            resolve_records = await conn.fetch(
                RESOLVE_SQL,
                [key[0] for key in physical_keys],
                [key[1] for key in physical_keys],
            )
            payload.resolved = {
                (
                    int(_record_value(record, "reltablespace")),
                    int(_record_value(record, "relfilenode")),
                ): ResolvedRelation(
                    relation_name=_optional_text(_record_value(record, "relation_name")),
                )
                for record in resolve_records
            }
    return payload


def _relation_candidate_keys(
    payload: BufferCachePayload,
    source_ids: frozenset[str],
) -> dict[str, frozenset[tuple[int, int]]]:
    if payload.current_database_oid is None:
        raise RuntimeError("Current database OID is required for relation cache charts")
    result: dict[str, frozenset[tuple[int, int]]] = {}
    if "buffer_cache.top_relations" in source_ids:
        result["buffer_cache.top_relations"] = _top_physical_keys(payload, dirty_only=False)
    if "buffer_cache.top_dirty_relations" in source_ids:
        result["buffer_cache.top_dirty_relations"] = _top_physical_keys(
            payload,
            dirty_only=True,
        )
    return result


def _top_physical_keys(
    payload: BufferCachePayload,
    *,
    dirty_only: bool,
    limit: int = 30,
) -> frozenset[tuple[int, int]]:
    counts: defaultdict[tuple[int, int], int] = defaultdict(int)
    for row in _current_database_rows(payload):
        if dirty_only and not row.isdirty:
            continue
        counts[_physical_key(row)] += row.buffers
    if len(counts) <= limit:
        return frozenset(counts)

    cutoff = sorted(counts.values(), reverse=True)[limit - 1]
    # Resolve all ties at the cutoff so the existing name-based tie order is preserved.
    return frozenset(key for key, buffers in counts.items() if buffers >= cutoff)


def build_result(
    source_id: str,
    payload: BufferCachePayload,
) -> tuple[list[dict[str, Any]], list[list[Any]]]:
    builders = {
        "buffer_cache.utilization": _build_utilization,
        "buffer_cache.usage_count_distribution": _build_usage_count_distribution,
        "buffer_cache.dirty_and_pinned": _build_dirty_and_pinned,
        "buffer_cache.by_database": _build_by_database,
        "buffer_cache.top_relations": _build_top_relations,
        "buffer_cache.top_dirty_relations": _build_top_dirty_relations,
    }
    builder = builders.get(source_id)
    if builder is None:
        raise KeyError(f"Unsupported buffer-cache source: {source_id}")
    return builder(payload)


def _build_fast_utilization(
    summary: FastSummary,
) -> tuple[list[dict[str, Any]], list[list[Any]]]:
    return (
        _columns(
            ("snapshot_time", "timestamptz"),
            ("scope", "text"),
            ("used_blocks", "int8"),
            ("unused_blocks", "int8"),
        ),
        [
            [
                summary.snapshot_time,
                "shared buffers",
                summary.buffers_used,
                summary.buffers_unused,
            ]
        ],
    )


def _build_fast_dirty_and_pinned(
    summary: FastSummary,
) -> tuple[list[dict[str, Any]], list[list[Any]]]:
    return (
        _columns(
            ("snapshot_time", "timestamptz"),
            ("scope", "text"),
            ("dirty_blocks", "int8"),
            ("pinned_blocks", "int8"),
        ),
        [
            [
                summary.snapshot_time,
                "shared buffers",
                summary.buffers_dirty,
                summary.buffers_pinned,
            ]
        ],
    )


def _build_fast_dirty_and_pinned_from_usage_counts(
    usage_counts: list[UsageCountRow],
) -> tuple[list[dict[str, Any]], list[list[Any]]]:
    if not usage_counts:
        raise RuntimeError("pg_buffercache_usage_counts() returned no rows")
    return (
        _columns(
            ("snapshot_time", "timestamptz"),
            ("scope", "text"),
            ("dirty_blocks", "int8"),
            ("pinned_blocks", "int8"),
        ),
        [
            [
                usage_counts[0].snapshot_time,
                "shared buffers",
                sum(row.dirty for row in usage_counts),
                sum(row.pinned for row in usage_counts),
            ]
        ],
    )


def _build_fast_usage_count_distribution(
    summary: FastSummary,
    usage_counts: list[UsageCountRow],
) -> tuple[list[dict[str, Any]], list[list[Any]]]:
    counts = {row.usage_count: row.buffers for row in usage_counts}
    counts[0] = max(0, counts.get(0, 0) - summary.buffers_unused)
    return (
        _columns(
            ("snapshot_time", "timestamptz"),
            ("usage_count_label", "text"),
            ("buffers", "int8"),
        ),
        [
            [summary.snapshot_time, f"usage count {usage_count}", counts.get(usage_count, 0)]
            for usage_count in range(6)
        ],
    )


def _build_utilization(
    payload: BufferCachePayload,
) -> tuple[list[dict[str, Any]], list[list[Any]]]:
    used = sum(row.buffers for row in payload.aggregates if row.relfilenode is not None)
    unused = sum(row.buffers for row in payload.aggregates if row.relfilenode is None)
    return (
        _columns(
            ("snapshot_time", "timestamptz"),
            ("scope", "text"),
            ("used_blocks", "int8"),
            ("unused_blocks", "int8"),
        ),
        [[payload.snapshot_time, "shared buffers", used, unused]],
    )


def _build_usage_count_distribution(
    payload: BufferCachePayload,
) -> tuple[list[dict[str, Any]], list[list[Any]]]:
    counts: defaultdict[int, int] = defaultdict(int)
    for row in payload.aggregates:
        if row.usagecount is not None:
            counts[row.usagecount] += row.buffers
    return (
        _columns(
            ("snapshot_time", "timestamptz"),
            ("usage_count_label", "text"),
            ("buffers", "int8"),
        ),
        [
            [payload.snapshot_time, f"usage count {usage_count}", counts[usage_count]]
            for usage_count in range(6)
        ],
    )


def _build_dirty_and_pinned(
    payload: BufferCachePayload,
) -> tuple[list[dict[str, Any]], list[list[Any]]]:
    dirty = sum(row.buffers for row in payload.aggregates if row.isdirty)
    pinned = sum(row.buffers for row in payload.aggregates if row.is_pinned)
    return (
        _columns(
            ("snapshot_time", "timestamptz"),
            ("scope", "text"),
            ("dirty_blocks", "int8"),
            ("pinned_blocks", "int8"),
        ),
        [[payload.snapshot_time, "shared buffers", dirty, pinned]],
    )


def _build_by_database(
    payload: BufferCachePayload,
) -> tuple[list[dict[str, Any]], list[list[Any]]]:
    counts: defaultdict[int, int] = defaultdict(int)
    for row in payload.aggregates:
        if row.relfilenode is not None and row.reldatabase is not None:
            counts[row.reldatabase] += row.buffers
    named = [
        (
            "shared catalogs"
            if database_oid == 0
            else payload.database_names.get(database_oid, f"unknown database {database_oid}"),
            buffers,
        )
        for database_oid, buffers in counts.items()
    ]
    named.sort(key=lambda item: (-item[1], item[0]))
    return (
        _columns(
            ("snapshot_time", "timestamptz"),
            ("database_name", "text"),
            ("cached_blocks", "int8"),
        ),
        [[payload.snapshot_time, database_name, buffers] for database_name, buffers in named[:100]],
    )


def _build_top_relations(
    payload: BufferCachePayload,
) -> tuple[list[dict[str, Any]], list[list[Any]]]:
    return _build_bounded_relations(payload, dirty_only=False, value_name="cached_blocks")


def _build_top_dirty_relations(
    payload: BufferCachePayload,
) -> tuple[list[dict[str, Any]], list[list[Any]]]:
    return _build_bounded_relations(payload, dirty_only=True, value_name="dirty_blocks")


def _build_bounded_relations(
    payload: BufferCachePayload,
    *,
    dirty_only: bool,
    value_name: str,
) -> tuple[list[dict[str, Any]], list[list[Any]]]:
    counts: defaultdict[str, int] = defaultdict(int)
    source_id = (
        "buffer_cache.top_dirty_relations"
        if dirty_only
        else "buffer_cache.top_relations"
    )
    candidate_keys = payload.relation_candidate_keys.get(source_id)
    other = 0
    for row in _current_database_rows(payload):
        if dirty_only and not row.isdirty:
            continue
        key = _physical_key(row)
        if candidate_keys is not None and key not in candidate_keys:
            other += row.buffers
            continue
        resolved = payload.resolved.get(key)
        relation_name = (
            resolved.relation_name
            if resolved is not None and resolved.relation_name
            else f"unresolved:{key[0]}/{key[1]}"
        )
        counts[relation_name] += row.buffers
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    bounded = ranked[:30]
    other += sum(value for _, value in ranked[30:])
    if other:
        bounded.append(("Other", other))
    bounded.sort(key=lambda item: (-item[1], item[0]))
    return (
        _columns(
            ("snapshot_time", "timestamptz"),
            ("relation_name", "text"),
            (value_name, "int8"),
        ),
        [
            [payload.snapshot_time, relation_name, buffers]
            for relation_name, buffers in bounded[:31]
        ],
    )


def _current_database_rows(payload: BufferCachePayload) -> Iterable[AggregateRow]:
    return (
        row
        for row in payload.aggregates
        if row.reldatabase == payload.current_database_oid and row.relfilenode is not None
    )


def _physical_key(row: AggregateRow) -> tuple[int, int]:
    if row.reltablespace is None or row.relfilenode is None:
        raise ValueError("Physical pg_buffercache row has no relation file identity")
    return row.reltablespace, row.relfilenode


def _aggregate_row(record: Any) -> AggregateRow:
    return AggregateRow(
        reltablespace=_optional_int(_record_value(record, "reltablespace")),
        reldatabase=_optional_int(_record_value(record, "reldatabase")),
        relfilenode=_optional_int(_record_value(record, "relfilenode")),
        relforknumber=_optional_int(_record_value(record, "relforknumber")),
        isdirty=bool(_record_value(record, "isdirty")),
        usagecount=_optional_int(_record_value(record, "usagecount")),
        is_pinned=bool(_record_value(record, "is_pinned")),
        buffers=int(_record_value(record, "buffers")),
    )


def _record_value(record: Any, name: str) -> Any:
    try:
        return record[name]
    except (KeyError, TypeError):
        return getattr(record, name)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _optional_text(value: Any) -> str | None:
    return None if value is None else str(value)


def _columns(*definitions: tuple[str, str]) -> list[dict[str, Any]]:
    type_oids = {"timestamptz": 1184, "text": 25, "int8": 20}
    return [
        {"name": name, "pg_type": pg_type, "pg_type_oid": type_oids[pg_type]}
        for name, pg_type in definitions
    ]
