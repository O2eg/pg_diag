from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from pg_diag.executors.batch import QueryBatchContext
from pg_diag.executors.buffer_cache import (
    AggregateRow,
    BufferCacheBatchProvider,
    BufferCachePayload,
    ResolvedRelation,
    _aggregate_sql,
    _top_physical_keys,
    build_result,
)
from pg_diag.planner import SourceJob


SNAPSHOT_TIME = datetime(2026, 7, 20, tzinfo=timezone.utc)


def _payload() -> BufferCachePayload:
    return BufferCachePayload(
        snapshot_time=SNAPSHOT_TIME,
        current_database_oid=42,
        database_names={7: "other_db", 42: "app_db"},
        aggregates=[
            AggregateRow(None, None, None, None, False, None, False, 5),
            AggregateRow(0, 42, 100, 0, False, 5, False, 10),
            AggregateRow(0, 42, 100, 0, True, 3, True, 2),
            AggregateRow(0, 42, 100, 1, False, 2, False, 3),
            AggregateRow(0, 42, 200, 0, True, 1, False, 7),
            AggregateRow(0, 42, 300, 0, False, 0, False, 4),
            AggregateRow(0, 7, 400, 0, False, 2, False, 6),
            AggregateRow(0, 0, 500, 0, False, 1, False, 2),
        ],
        resolved={
            (0, 100): ResolvedRelation("public.accounts"),
            (0, 200): ResolvedRelation("public.accounts_pkey"),
            (0, 300): ResolvedRelation(None),
        },
    )


def _column_names(columns: list[dict]) -> list[str]:
    return [column["name"] for column in columns]


def test_builds_summary_results_from_one_aggregate_payload() -> None:
    payload = _payload()

    columns, rows = build_result("buffer_cache.utilization", payload)
    assert _column_names(columns) == [
        "snapshot_time",
        "scope",
        "used_blocks",
        "unused_blocks",
    ]
    assert rows == [[SNAPSHOT_TIME, "shared buffers", 34, 5]]

    _columns, rows = build_result("buffer_cache.usage_count_distribution", payload)
    assert rows == [
        [SNAPSHOT_TIME, "usage count 0", 4],
        [SNAPSHOT_TIME, "usage count 1", 9],
        [SNAPSHOT_TIME, "usage count 2", 9],
        [SNAPSHOT_TIME, "usage count 3", 2],
        [SNAPSHOT_TIME, "usage count 4", 0],
        [SNAPSHOT_TIME, "usage count 5", 10],
    ]

    _columns, rows = build_result("buffer_cache.dirty_and_pinned", payload)
    assert rows == [[SNAPSHOT_TIME, "shared buffers", 9, 2]]


def test_builds_database_and_relation_results_with_existing_semantics() -> None:
    payload = _payload()

    _columns, rows = build_result("buffer_cache.by_database", payload)
    assert rows == [
        [SNAPSHOT_TIME, "app_db", 26],
        [SNAPSHOT_TIME, "other_db", 6],
        [SNAPSHOT_TIME, "shared catalogs", 2],
    ]

    _columns, rows = build_result("buffer_cache.top_relations", payload)
    assert rows == [
        [SNAPSHOT_TIME, "public.accounts", 15],
        [SNAPSHOT_TIME, "public.accounts_pkey", 7],
        [SNAPSHOT_TIME, "unresolved:0/300", 4],
    ]

    _columns, rows = build_result("buffer_cache.top_dirty_relations", payload)
    assert rows == [
        [SNAPSHOT_TIME, "public.accounts_pkey", 7],
        [SNAPSHOT_TIME, "public.accounts", 2],
    ]


def test_top_relations_bounds_cardinality_with_other_bucket() -> None:
    payload = _payload()
    payload.aggregates = [
        AggregateRow(0, 42, filenode, 0, False, 1, False, 100 - filenode)
        for filenode in range(1, 34)
    ]
    payload.resolved = {
        (0, filenode): ResolvedRelation(f"public.r{filenode:02d}") for filenode in range(1, 34)
    }

    _columns, rows = build_result("buffer_cache.top_relations", payload)

    assert len(rows) == 31
    assert [row for row in rows if row[1] == "Other"] == [[SNAPSHOT_TIME, "Other", 67 + 68 + 69]]


class FakeConnection:
    def __init__(
        self,
        *,
        fast_supported: bool = False,
        has_summary: bool | None = None,
        has_usage_counts: bool | None = None,
        capability_error: BaseException | None = None,
        aggregate_error: BaseException | None = None,
        summary_error: BaseException | None = None,
        usage_counts_error: BaseException | None = None,
    ) -> None:
        self.has_summary = fast_supported if has_summary is None else has_summary
        self.has_usage_counts = (
            fast_supported if has_usage_counts is None else has_usage_counts
        )
        self.capability_error = capability_error
        self.aggregate_error = aggregate_error
        self.summary_error = summary_error
        self.usage_counts_error = usage_counts_error
        self.calls: list[str] = []
        self.transaction_failed = False

    def transaction(self, *, readonly: bool):
        assert readonly is True
        return FakeSavepoint(self)

    async def fetch(self, sql: str, *_args):
        if self.transaction_failed:
            raise RuntimeError("current transaction is aborted")
        if "pg_diag:buffer_cache:capabilities" in sql:
            self.calls.append("capabilities")
            if self.capability_error is not None:
                self.transaction_failed = True
                raise self.capability_error
            return [
                {
                    "has_summary": self.has_summary,
                    "has_usage_counts": self.has_usage_counts,
                }
            ]
        if "pg_diag:buffer_cache:fast_summary" in sql:
            self.calls.append("fast_summary")
            if self.summary_error is not None:
                raise self.summary_error
            return [
                {
                    "snapshot_time": SNAPSHOT_TIME,
                    "buffers_used": 34,
                    "buffers_unused": 5,
                    "buffers_dirty": 9,
                    "buffers_pinned": 2,
                }
            ]
        if "pg_diag:buffer_cache:fast_usage_counts" in sql:
            self.calls.append("fast_usage_counts")
            if self.usage_counts_error is not None:
                raise self.usage_counts_error
            return [
                {
                    "snapshot_time": SNAPSHOT_TIME,
                    "usage_count": 0,
                    "buffers": 9,
                    "dirty": 0,
                    "pinned": 0,
                },
                {
                    "snapshot_time": SNAPSHOT_TIME,
                    "usage_count": 1,
                    "buffers": 9,
                    "dirty": 7,
                    "pinned": 0,
                },
                {
                    "snapshot_time": SNAPSHOT_TIME,
                    "usage_count": 2,
                    "buffers": 9,
                    "dirty": 0,
                    "pinned": 0,
                },
                {
                    "snapshot_time": SNAPSHOT_TIME,
                    "usage_count": 3,
                    "buffers": 2,
                    "dirty": 2,
                    "pinned": 2,
                },
                {
                    "snapshot_time": SNAPSHOT_TIME,
                    "usage_count": 4,
                    "buffers": 0,
                    "dirty": 0,
                    "pinned": 0,
                },
                {
                    "snapshot_time": SNAPSHOT_TIME,
                    "usage_count": 5,
                    "buffers": 10,
                    "dirty": 0,
                    "pinned": 0,
                },
            ]
        if "pg_diag:buffer_cache:aggregate_legacy" in sql:
            self.calls.append("aggregate_legacy")
            if self.aggregate_error is not None:
                raise self.aggregate_error
            return [
                {
                    "snapshot_time": SNAPSHOT_TIME,
                    "reltablespace": None,
                    "reldatabase": None,
                    "relfilenode": None,
                    "relforknumber": None,
                    "isdirty": False,
                    "usagecount": 0,
                    "is_pinned": False,
                    "buffers": 5,
                },
                {
                    "snapshot_time": SNAPSHOT_TIME,
                    "reltablespace": 0,
                    "reldatabase": 42,
                    "relfilenode": 100,
                    "relforknumber": 0,
                    "isdirty": True,
                    "usagecount": 3,
                    "is_pinned": False,
                    "buffers": 10,
                },
            ]
        if "pg_diag:buffer_cache:aggregate_detail" in sql:
            self.calls.append("aggregate_detail")
            if self.aggregate_error is not None:
                raise self.aggregate_error
            return [
                {
                    "snapshot_time": SNAPSHOT_TIME,
                    "reltablespace": 0,
                    "reldatabase": 42,
                    "relfilenode": 100,
                    "relforknumber": None,
                    "isdirty": True,
                    "usagecount": None,
                    "is_pinned": False,
                    "buffers": 10,
                }
            ]
        if "pg_diag:buffer_cache:metadata" in sql:
            self.calls.append("metadata")
            return [
                {
                    "snapshot_time": SNAPSHOT_TIME,
                    "current_database_oid": 42,
                    "database_oid": 42,
                    "database_name": "app_db",
                }
            ]
        if "pg_diag:buffer_cache:resolve" in sql:
            self.calls.append("resolve")
            return [
                {
                    "reltablespace": 0,
                    "relfilenode": 100,
                    "relation_name": "public.accounts",
                }
            ]
        raise AssertionError(f"Unexpected SQL: {sql}")


class FakeSavepoint:
    def __init__(self, conn: FakeConnection) -> None:
        self.conn = conn

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        if exc_type is not None:
            self.conn.transaction_failed = False
        return False


def test_legacy_batch_provider_scans_detailed_view_once_for_all_items() -> None:
    source_ids = [
        "buffer_cache.utilization",
        "buffer_cache.usage_count_distribution",
        "buffer_cache.dirty_and_pinned",
        "buffer_cache.by_database",
        "buffer_cache.top_relations",
        "buffer_cache.top_dirty_relations",
    ]
    provider = BufferCacheBatchProvider(source_ids)
    conn = FakeConnection()

    async def collect_all() -> None:
        for source_id in source_ids:
            await provider.result_for(conn, source_id)

    asyncio.run(collect_all())

    assert conn.calls == ["aggregate_legacy", "metadata", "resolve"]


def test_pg16_batch_provider_uses_fast_functions_for_summary_items() -> None:
    source_ids = [
        "buffer_cache.utilization",
        "buffer_cache.usage_count_distribution",
        "buffer_cache.dirty_and_pinned",
        "buffer_cache.by_database",
        "buffer_cache.top_relations",
        "buffer_cache.top_dirty_relations",
    ]
    provider = BufferCacheBatchProvider(source_ids, prefer_fast_summary=True)
    conn = FakeConnection(fast_supported=True)
    collected = {}

    async def collect_all() -> None:
        for source_id in source_ids:
            collected[source_id] = await provider.result_for(conn, source_id)

    asyncio.run(collect_all())

    assert conn.calls == [
        "capabilities",
        "fast_summary",
        "fast_usage_counts",
        "aggregate_detail",
        "metadata",
        "resolve",
    ]
    assert collected["buffer_cache.utilization"][1] == [[SNAPSHOT_TIME, "shared buffers", 34, 5]]
    assert collected["buffer_cache.usage_count_distribution"][1][0] == [
        SNAPSHOT_TIME,
        "usage count 0",
        4,
    ]
    assert collected["buffer_cache.dirty_and_pinned"][1] == [
        [SNAPSHOT_TIME, "shared buffers", 9, 2]
    ]


def test_pg16_detail_timeout_does_not_break_fast_summary_items() -> None:
    error = RuntimeError("detailed pg_buffercache failed")
    provider = BufferCacheBatchProvider(
        {
            "buffer_cache.by_database",
            "buffer_cache.top_relations",
            "buffer_cache.utilization",
        },
        prefer_fast_summary=True,
    )
    conn = FakeConnection(fast_supported=True, aggregate_error=error)

    async def collect() -> None:
        with pytest.raises(RuntimeError, match="detailed pg_buffercache failed"):
            await provider.result_for(conn, "buffer_cache.by_database")
        _columns, rows = await provider.result_for(conn, "buffer_cache.utilization")
        assert rows == [[SNAPSHOT_TIME, "shared buffers", 34, 5]]
        with pytest.raises(RuntimeError, match="detailed pg_buffercache failed"):
            await provider.result_for(conn, "buffer_cache.top_relations")

    asyncio.run(collect())

    assert conn.calls == ["capabilities", "aggregate_detail", "fast_summary"]


def test_pg16_plan_falls_back_when_fast_functions_are_unavailable() -> None:
    provider = BufferCacheBatchProvider(
        {"buffer_cache.utilization", "buffer_cache.dirty_and_pinned"},
        prefer_fast_summary=True,
    )
    conn = FakeConnection(fast_supported=False)

    async def collect() -> None:
        await provider.result_for(conn, "buffer_cache.utilization")
        await provider.result_for(conn, "buffer_cache.dirty_and_pinned")

    asyncio.run(collect())

    assert conn.calls == ["capabilities", "aggregate_legacy"]


def test_capability_error_rolls_back_savepoint_before_legacy_fallback() -> None:
    provider = BufferCacheBatchProvider(
        {"buffer_cache.utilization"},
        prefer_fast_summary=True,
    )
    conn = FakeConnection(capability_error=RuntimeError("capability probe failed"))

    async def collect() -> None:
        _columns, rows = await provider.result_for(conn, "buffer_cache.utilization")
        assert rows == [[SNAPSHOT_TIME, "shared buffers", 10, 5]]

    asyncio.run(collect())

    assert conn.calls == ["capabilities", "aggregate_legacy"]
    assert conn.transaction_failed is False


def test_fast_capabilities_are_applied_per_source() -> None:
    provider = BufferCacheBatchProvider(
        {
            "buffer_cache.utilization",
            "buffer_cache.usage_count_distribution",
            "buffer_cache.dirty_and_pinned",
        },
        prefer_fast_summary=True,
    )
    conn = FakeConnection(has_summary=True, has_usage_counts=False)

    async def collect() -> None:
        await provider.result_for(conn, "buffer_cache.utilization")
        await provider.result_for(conn, "buffer_cache.dirty_and_pinned")
        await provider.result_for(conn, "buffer_cache.usage_count_distribution")

    asyncio.run(collect())

    assert conn.calls == ["capabilities", "fast_summary", "aggregate_legacy"]


def test_dirty_and_pinned_can_use_usage_counts_without_summary_privilege() -> None:
    provider = BufferCacheBatchProvider(
        {"buffer_cache.dirty_and_pinned"},
        prefer_fast_summary=True,
    )
    conn = FakeConnection(has_summary=False, has_usage_counts=True)

    _columns, rows = asyncio.run(
        provider.result_for(conn, "buffer_cache.dirty_and_pinned")
    )

    assert rows == [[SNAPSHOT_TIME, "shared buffers", 9, 2]]
    assert conn.calls == ["capabilities", "fast_usage_counts"]


def test_dynamic_aggregate_uses_only_dimensions_needed_by_selected_sources() -> None:
    utilization_sql = _aggregate_sql(frozenset({"buffer_cache.utilization"}))
    assert "group by case when relfilenode is null" in utilization_sql
    assert "group by reltablespace" not in utilization_sql
    assert "pinning_backends" not in utilization_sql

    by_database_sql = _aggregate_sql(frozenset({"buffer_cache.by_database"}))
    assert "group by reldatabase" in by_database_sql
    assert "group by reltablespace" not in by_database_sql
    assert "relfilenode is not null" in by_database_sql

    top_dirty_sql = _aggregate_sql(frozenset({"buffer_cache.top_dirty_relations"}))
    assert "pg_catalog.current_database()" in top_dirty_sql
    assert "and isdirty" in top_dirty_sql

    full_legacy_sql = _aggregate_sql(
        frozenset(
            {
                "buffer_cache.utilization",
                "buffer_cache.usage_count_distribution",
                "buffer_cache.dirty_and_pinned",
                "buffer_cache.by_database",
                "buffer_cache.top_relations",
                "buffer_cache.top_dirty_relations",
            }
        )
    )
    group_by = full_legacy_sql.partition("group by ")[2]
    assert "relforknumber" not in group_by


def test_relation_resolution_candidates_preserve_other_bucket() -> None:
    payload = _payload()
    payload.aggregates = [
        AggregateRow(0, 42, filenode, None, False, None, False, 100 - filenode)
        for filenode in range(1, 34)
    ]
    candidates = _top_physical_keys(payload, dirty_only=False)
    payload.relation_candidate_keys = {"buffer_cache.top_relations": candidates}
    payload.resolved = {
        key: ResolvedRelation(f"public.r{key[1]:02d}") for key in candidates
    }

    _columns, rows = build_result("buffer_cache.top_relations", payload)

    assert len(candidates) == 30
    assert len(rows) == 31
    assert [row for row in rows if row[1] == "Other"] == [
        [SNAPSHOT_TIME, "Other", 67 + 68 + 69]
    ]


def test_query_batch_context_enables_fast_path_for_pg16_variant() -> None:
    planned = SourceJob(
        job_id="buffer_cache.utilization",
        title="Buffer Cache Utilization",
        source_id="buffer_cache.utilization",
        status="planned",
        variant_id="buffer_cache_utilization_pg16_plus",
        sql_file="buffer_cache/utilization_pg16_plus.sql",
        collection_scope="every_snapshot",
    )

    context = QueryBatchContext([planned])

    assert context.handles(planned)
    assert context.buffer_cache.prefer_fast_summary is True


def test_batch_provider_does_not_repeat_failed_scan() -> None:
    error = RuntimeError("pg_buffercache failed")
    provider = BufferCacheBatchProvider(
        {"buffer_cache.utilization", "buffer_cache.dirty_and_pinned"}
    )
    conn = FakeConnection(aggregate_error=error)

    async def collect_twice() -> None:
        with pytest.raises(RuntimeError, match="pg_buffercache failed"):
            await provider.result_for(conn, "buffer_cache.utilization")
        with pytest.raises(RuntimeError, match="pg_buffercache failed"):
            await provider.result_for(conn, "buffer_cache.dirty_and_pinned")

    asyncio.run(collect_twice())

    assert conn.calls == ["aggregate_legacy"]
