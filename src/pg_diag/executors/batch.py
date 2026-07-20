"""Per-query-batch shared execution context."""

from __future__ import annotations

from typing import Any, Iterable

from pg_diag.executors.buffer_cache import (
    BufferCacheBatchProvider,
    FAST_SUMMARY_SQL_FILES,
)
from pg_diag.planner import PlannedEntry


class QueryBatchContext:
    """Share provider payloads only within one snapshot transaction."""

    def __init__(self, planned_entries: Iterable[PlannedEntry]) -> None:
        entries = tuple(planned_entries)
        source_ids = {entry.source_id for entry in entries if isinstance(entry.source_id, str)}
        prefer_fast_summary = any(entry.sql_file in FAST_SUMMARY_SQL_FILES for entry in entries)
        self.buffer_cache = BufferCacheBatchProvider(
            source_ids,
            prefer_fast_summary=prefer_fast_summary,
        )

    def handles(self, planned: PlannedEntry) -> bool:
        return self.buffer_cache.handles(planned.source_id)

    async def execute(
        self,
        conn: Any,
        planned: PlannedEntry,
    ) -> tuple[list[dict[str, Any]], list[list[Any]]]:
        source_id = planned.source_id
        if not isinstance(source_id, str) or not self.buffer_cache.handles(source_id):
            raise KeyError(f"No batch provider for source: {source_id}")
        return await self.buffer_cache.result_for(conn, source_id)
