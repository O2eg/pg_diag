# Tables Without PK Or Unique Index From relpages

This instruction belongs to report item `fallback.indexes.tables_without_pk_or_unique_relpages`. The item is backed by `indexes.tables_without_pk_or_unique_relpages` (SQL query).

## What this item shows
- Top-level user tables without a valid, ready, live, non-partial primary or unique index.
- Approximate physical table pages and bytes calculated from `pg_class.relpages`.
- Aggregated page and row estimates for physical descendants of partitioned tables.
- Coverage fields showing how many eligible roots existed, how many were evaluated, and whether root selection was truncated.

## What to watch
- Large estimated durable tables without stable row identity.
- Keyless tables used by logical replication or application update/delete paths.
- Partitioned roots whose aggregate leaf size makes the missing key operationally significant.
- `root_selection_truncated = true`, which means the lightweight fallback intentionally bounded catalog recursion and did not evaluate every eligible root.

## Common fault causes
- The primary item waited while `pg_total_relation_size` conflicted with concurrent DDL.
- Exact total-size calculations for candidate tables exceeded the primary statement timeout.
- Staging or transient tables were intentionally created without keys.
- `relpages` or tuple estimates are stale after rapid loading or deletion.

## Automatic evaluation
- `medium` is raised when the aggregated physical-table row estimate is at least 100,000.
- `estimated_table_size_bytes` covers main table relations only; it excludes indexes, TOAST, and auxiliary forks.
- The result preserves the key-eligibility checks of the primary item but uses approximate catalog data for prioritization.
- To keep the emergency query bounded, it evaluates at most 200 ordinary roots and 200 partitioned roots before ranking the final 200 results.

## Related report items
- [indexes.tables_without_pk_or_unique](#item-indexes.tables_without_pk_or_unique) — Retry the primary item when exact total relation sizes are required.
- [object_workload.table_workload](#item-object_workload.table_workload) — Check whether affected tables carry meaningful application workload.

## Checklist
- Confirm whether each table is durable, transient, or staging.
- Check logical-replication identity requirements.
- Resolve duplicates before adding a primary key or unique constraint.
- Refresh statistics before treating relpages and tuple estimates as reliable ranking data.
- If root selection was truncated, rerun a narrowly scoped catalog query for schemas or tables not represented in this result.
