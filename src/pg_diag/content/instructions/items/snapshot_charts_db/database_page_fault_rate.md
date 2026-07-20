# Database Page Fault Rate

This instruction belongs to report item `snapshot_charts_db.database_page_fault_rate`. The item is backed by `database.page_fault_rate` (snapshot metric).

## What this item shows
- A stacked database timeline of minor and major execution page faults from top-level `pg_stat_kcache` entries.
- The chart unit `/s` is faults per wall-clock second; major faults use a contrasting series because they may require storage access.
- The first sample has no preceding interval, so its rate is unavailable.

## What to watch
- Any sustained major-fault series, especially with latency, swap, or disk-read spikes.
- Rising minor faults during high backend counts, allocation churn, or page-table pressure.
- Gaps caused by counter decreases or changing aggregate membership.

## Automatic evaluation
- No universal severity threshold is assigned because latency objectives and platform behavior differ.
- Native counter absence is rendered as unavailable/empty rather than false zero activity.

## Common fault causes
- RAM pressure, swap-backed pages, cold mappings, or working-set churn.
- Many PostgreSQL processes, large mappings, and page-table overhead.
- Cold start after server or application restart.

## Related report items
- [snapshot_delta_workload.sql_page_faults_delta](#item-snapshot_delta_workload.sql_page_faults_delta) — Attribute database faults to SQL identities.
- [snapshot_charts_os.os_memory_pressure](#item-snapshot_charts_os.os_memory_pressure) — Compare faults with RAM and swap pressure.
- [snapshot_charts_os.os_disk_read_throughput](#item-snapshot_charts_os.os_disk_read_throughput) — Check storage reads during major faults.
- [os.postgresql_huge_pages](#item-os.postgresql_huge_pages) — Review PageTables and Huge Pages diagnostics.

## Checklist
- Prioritize major faults and correlate them with swap and device latency.
- Compare per-database and per-query evidence in the same window.
- Check page-table pressure and backend count before proposing Huge Pages or connection changes.
- Empty means fewer than two comparable samples or no non-zero native faults; `unsupported` normally means pg_stat_kcache 2.3+ is unavailable.
