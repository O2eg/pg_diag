# SQL I/O Attribution Delta

This instruction belongs to report item `snapshot_delta_workload.sql_io_attribution_delta`. The item is backed by `statements.io_attribution_delta` (snapshot metric).

## What this item shows
- Side-by-side interval bytes from `pg_stat_kcache` filesystem counters and PostgreSQL shared/local/temp block counters multiplied by `block_size`.
- Filesystem and PostgreSQL-block bytes per second plus filesystem-to-block percentages for reads, writes, and their total.
- Up to 50 rows from this item's independent 250-entry endpoint candidate set; `query_id` opens captured SQL text.

## What to watch
- A low filesystem-to-PostgreSQL-read percentage can indicate that many PostgreSQL buffer misses were served from OS cache.
- A high or divergent percentage can indicate filesystem work not represented by ordinary relation block counters, differing counter semantics, or endpoint candidate bias.
- `B` is bytes accumulated over the window and `B/s` is bytes per wall-clock second; percentages compare deltas and are not cache-hit ratios.

## Automatic evaluation
- No threshold is assigned because `getrusage` I/O and PostgreSQL block counters describe different layers and are not expected to reconcile exactly.
- A percentage is omitted when its PostgreSQL-block denominator has no activity or any required counter is unavailable/reset.

## Interval coverage
- Filesystem and PostgreSQL block counters must belong to the same query identity at both endpoints with unchanged `pg_stat_kcache.stats_since`.
- Unmatched candidates, resets, and decreases invalidate the full row so cross-layer ratios never combine different intervals.

## Common fault causes
- OS page-cache hits, reads/writes outside ordinary relation counters, temporary I/O, extensions, or background writeback.
- Different buffering, accounting granularity, and kernel/platform semantics.
- Query entry churn or a source Top-N candidate absent from one endpoint.

## Related report items
- [snapshot_delta_workload.sql_filesystem_io_delta](#item-snapshot_delta_workload.sql_filesystem_io_delta) — Inspect the kernel filesystem rates and bytes/call alone.
- [snapshot_delta_workload.sql_io_delta](#item-snapshot_delta_workload.sql_io_delta) — Inspect shared-block counts and timing for the same SQL identity.
- [snapshot_delta_workload.sql_temp_io_delta](#item-snapshot_delta_workload.sql_temp_io_delta) — Separate temporary block I/O.
- [snapshot_charts_os.os_disk_utilization](#item-snapshot_charts_os.os_disk_utilization) — Check whether attributed bytes coincide with device saturation.

## Checklist
- Treat the percentages as attribution clues, not equality checks.
- Compare read and write sides separately and account for local/temp blocks included in the PostgreSQL total.
- Correlate with OS throughput, utilization, and latency in the same time window.
- Empty means no comparable non-zero I/O; `unsupported` normally means pg_stat_kcache 2.3+ is unavailable.
