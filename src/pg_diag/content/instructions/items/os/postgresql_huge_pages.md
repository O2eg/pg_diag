# PostgreSQL Huge Pages

This instruction belongs to report item `os.postgresql_huge_pages`. The item has an independent trusted Python source that correlates PostgreSQL settings with a host probe for the connected instance.

## What this item shows
- A one-shot diagnostic row combining the requested and actual PostgreSQL huge-page state, the PostgreSQL and OS default page sizes, shared-memory sizing, the matching default HugeTLB pool, and a conservative recommendation.
- All memory and page-size columns are exact bytes displayed with adaptive IEC units; page columns are counts; `*_pct_*` columns are percentages.
- `required_huge_pages` and `shared_memory_size_bytes` come from PostgreSQL when the server version exposes those settings. They are empty on older versions rather than estimates.
- `host_page_tables_bytes` is the host-wide Linux `PageTables` counter. `postgres_vmpte_bytes` is a point-in-time sum for the connected postmaster and its visible direct PostgreSQL children, so it is attribution evidence rather than an accounting identity.
- Transparent Huge Pages are reported separately because THP policy and PostgreSQL explicit HugeTLB pages are different mechanisms.

## What to watch
- `huge_pages_requested=try` together with `huge_pages_actual=off`, which means PostgreSQL continued on regular pages.
- A nonzero `default_pool_shortfall_pages` when the default OS page size matches the PostgreSQL page size.
- `default_pool_free_unreserved_pages` near zero before a restart or shared-memory increase.
- Host page-table memory above both 512 MiB and 1% of host RAM, especially when the connected PostgreSQL instance contributes at least 50% of `PageTables` through visible `VmPTE` values.
- `transparent_huge_pages_mode=always` on a latency-sensitive database host.

## Common fault causes
- The matching HugeTLB pool was not reserved persistently, was sized for an older `shared_buffers` value, or is already consumed by another process.
- PostgreSQL settings changed without the restart required to rebuild the main shared-memory area.
- A different huge-page size was configured than the OS default pool represented by `/proc/meminfo`.
- Many backends, large mappings, colocated services, KVM guests, or an unusual kernel workload increased host page-table memory.
- The collector and PostgreSQL are in different PID namespaces, preventing process-level attribution even though host memory counters remain available.

## Automatic evaluation
- `medium` is assigned when `huge_pages=try` fell back to regular pages, the matching default pool is smaller than PostgreSQL's reported requirement, host `PageTables` is at least 512 MiB and at least 1% of RAM, or THP mode is `always`.
- A high PostgreSQL share of host `PageTables` changes the recommendation toward considering explicit PostgreSQL huge pages; it does not by itself prove that huge pages are required.
- `ok` means none of those conservative checks fired. No `high` severity is assigned because pool changes require maintenance planning, restart context, and confirmation of other HugeTLB consumers.
- `unsupported` means the database backend PID or required host `/proc/meminfo` evidence could not be collected. Missing process visibility alone leaves the item available with a warning and empty instance-attribution fields.

## Related report items
- [os.huge_page_pools](#item-os.huge_page_pools) — Inspect every OS HugeTLB page-size pool and its NUMA distribution instead of only the default pool.
- [os.memory_info](#item-os.memory_info) — Review the surrounding host memory, commit, swap, and huge-page counters.
- [os.total_ram](#item-os.total_ram) — Confirm the physical RAM denominator used by the page-table percentage.
- [snapshot_charts_os.os_memory_usage](#item-snapshot_charts_os.os_memory_usage) — Check whether page-table growth and other memory components persist over the capture interval.
- [snapshot_charts_db.database_backends](#item-snapshot_charts_db.database_backends) — Correlate process and page-table pressure with backend concurrency.

## Checklist
- Verify that PostgreSQL's page size matches the intended OS pool before comparing page counts.
- Compare the reported required page count with total capacity and with free pages not already reserved.
- Persist the kernel HugeTLB reservation, account for other consumers and NUMA placement, then restart PostgreSQL in a maintenance window.
- Confirm actual use after restart; do not treat THP as a substitute for PostgreSQL explicit huge pages.
- In containers, validate PID namespace visibility, cgroup limits, and whether `/proc/meminfo` represents the host or the container boundary.
