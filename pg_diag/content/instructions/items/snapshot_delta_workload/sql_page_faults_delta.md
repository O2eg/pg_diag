# SQL Page Faults Delta

This instruction belongs to report item `snapshot_delta_workload.sql_page_faults_delta`. The item is backed by `statements.page_faults_delta` (snapshot metric).

## What this item shows
- Minor/major execution page-fault deltas, faults per second, and faults per call for each SQL identity.
- `/s` means faults per wall-clock second; per-call fields divide interval fault deltas by the interval call delta.
- Rows sort by major faults first; up to 50 are retained from an independent 250-entry candidate set and `query_id` is clickable.

## What to watch
- Any sustained major-fault rate because it can require storage access and cause sharp latency.
- High minor faults per call, especially with memory pressure, large mappings, many processes, or allocation churn.
- Missing native counters, which mean unavailable evidence rather than zero faults.

## Automatic evaluation
- No universal threshold is assigned; a single major fault may matter to low-latency workloads while batch systems tolerate more.
- Only comparable 2.3+ entry epochs are used and counter decreases invalidate the interval.

## Interval coverage
- The same query identity and unchanged `pg_stat_kcache.stats_since` are required at both endpoints.
- Candidate churn, reset/decrease, and native-null counters are omitted and reflected in coverage rather than converted to zero.

## Common fault causes
- Memory pressure, swap-backed pages, cold executable/library mappings, or working-set churn.
- Many backend processes and page-table pressure.
- Large temporary or memory-mapped workloads and cold cache after restart.

## Related report items
- [snapshot_charts_db.database_page_fault_rate](#item-snapshot_charts_db.database_page_fault_rate) — Place per-query faults in the database timeline.
- [snapshot_charts_os.os_memory_pressure](#item-snapshot_charts_os.os_memory_pressure) — Check RAM and swap pressure.
- [snapshot_delta_workload.sql_context_switches_delta](#item-snapshot_delta_workload.sql_context_switches_delta) — Check scheduler effects accompanying faults.
- [os.postgresql_huge_pages](#item-os.postgresql_huge_pages) — Review page-table pressure and Huge Pages suitability.

## Checklist
- Investigate major faults before minor faults.
- Correlate fault timestamps with swap, memory pressure, and storage latency.
- Compare faults per call to distinguish execution frequency from individual footprint.
- Empty means no non-zero comparable native counters; `unsupported` normally means the extension/API is unavailable.
