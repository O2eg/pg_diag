# Tables Without PK Or Unique Index From relpages

This instruction belongs to report item `fallback.indexes.tables_without_pk_or_unique_relpages`. The item is backed by `indexes.tables_without_pk_or_unique_relpages` (SQL query).

## What this item shows
- Top-level user tables without a valid, ready, live, non-partial primary or unique index.
- Approximate physical table pages and bytes calculated from `pg_class.relpages`.
- Aggregated page and row estimates for physical descendants of partitioned tables.
- Coverage fields showing how many keyless roots were found in the bounded candidate pools, how many were evaluated, and whether selection inside those pools was truncated.

## What to watch
- Large estimated durable tables without stable row identity.
- Keyless tables used by logical replication or application update/delete paths.
- Partitioned roots whose aggregate leaf size makes the missing key operationally significant.
- `root_selection_truncated = true`, which means the fallback did not evaluate every keyless root found inside the bounded candidate pools.
- `result_truncated = true`, which means more than 200 evaluated roots qualified and only the highest-ranked 200 are displayed.
- `tree_truncated = true`, which means the shared descendant traversal exceeded 3,000 rows and page/tuple estimates are partial.

## Common fault causes
- The primary item waited while `pg_total_relation_size` conflicted with concurrent DDL.
- Exact total-size calculations for candidate tables exceeded the primary statement timeout.
- Staging or transient tables were intentionally created without keys.
- `relpages` or tuple estimates are stale after rapid loading or deletion.

## Automatic evaluation
- `medium` is raised when the aggregated physical-table row estimate is at least 100,000 and the partition traversal was not truncated.
- `estimated_table_size_bytes` covers main table relations only; it excludes indexes, TOAST, and auxiliary forks.
- The result preserves the key-eligibility checks of the primary item but uses approximate catalog data for prioritization.
- To keep the emergency query bounded, it first considers at most 10,000 largest non-empty ordinary roots and 10,000 alphabetically selected partitioned roots. It then evaluates at most 200 keyless roots of each kind before ranking the final 200 results.
- `sampled_eligible_root_count` is a count inside those bounded pools, not a total database-wide count.
- `ranked_candidate_count` is the number of evaluated roots available before the final 200-row presentation limit.

## Related report items
- [indexes.tables_without_pk_or_unique](#item-indexes.tables_without_pk_or_unique) — Retry the primary item when exact total relation sizes are required.
- [object_workload.table_workload](#item-object_workload.table_workload) — Check whether affected tables carry meaningful application workload.

## Checklist
- Confirm whether each table is durable, transient, or staging.
- Check logical-replication identity requirements.
- Resolve duplicates before adding a primary key or unique constraint.
- Refresh statistics before treating relpages and tuple estimates as reliable ranking data.
- If root selection was truncated, rerun a narrowly scoped catalog query for schemas or tables not represented in this result.
- If result selection was truncated, use the displayed ordering for initial prioritization and narrow a follow-up query by schema.
- Even when `root_selection_truncated = false`, objects outside the initial 10,000-row pools were not evaluated.
- If tree traversal was truncated, do not use partial row or size estimates for severity or final prioritization.
