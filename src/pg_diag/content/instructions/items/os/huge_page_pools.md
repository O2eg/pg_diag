# OS Huge Page Pools

This instruction belongs to report item `os.huge_page_pools`. The item has its own local host script and does not reuse the query, host probe, or result table of any other report item.

## What this item shows
- One point-in-time row for every HugeTLB page-size pool exposed under `/sys/kernel/mm/hugepages`; the item is collected once per report run.
- Page size and pool-capacity columns are exact bytes displayed with adaptive IEC units; `*_pages` columns and `numa_nodes_with_pages` are counts.
- `used_pages` is `total_pages - free_pages`; `free_unreserved_pages` is `free_pages - reserved_pages`, with negative transient results clamped to zero.
- `is_default_size` identifies the page size reported as `Hugepagesize` by `/proc/meminfo`.
- `numa_distribution` shows the configured page count per visible NUMA node, for example `node0=4096,node1=4096`.

## What to watch
- The PostgreSQL page size having no pool row or a total capacity smaller than PostgreSQL's required page count.
- Few or no free unreserved pages before a PostgreSQL restart, shared-memory increase, or another HugeTLB allocation.
- Nonzero surplus pages, which can indicate dynamic overcommit use and a pool state different from the persistent target.
- Strong NUMA imbalance when PostgreSQL is expected to allocate memory across sockets.
- A populated pool at a page size PostgreSQL does not use, while the required pool is empty.

## Common fault causes
- `vm.nr_hugepages` or per-size sysfs reservations were not persisted across reboot.
- Contiguous pages could not be reserved after memory became fragmented.
- Another service consumed or reserved pages from the same pool.
- Kernel command-line, sysctl, systemd, or configuration-management values disagree.
- NUMA-specific allocation was configured on only one node or the collector cannot see all host nodes.

## Automatic evaluation
- This detailed pool inventory is informational and does not assign severity because its source intentionally has no PostgreSQL query or dependency on another item.
- Compare the correct page-size row with `os.postgresql_huge_pages` for requested state and required page count. A free page can already be reserved, so use `free_unreserved_pages` when assessing immediately allocatable capacity.
- `unsupported` means the kernel does not expose `/sys/kernel/mm/hugepages` or no page-size directories were found.

## Related report items
- [os.postgresql_huge_pages](#item-os.postgresql_huge_pages) — Compare each independent OS pool with PostgreSQL's requested state, effective page size, and required capacity.
- [os.memory_info](#item-os.memory_info) — Cross-check the default pool with the aggregate `/proc/meminfo` counters.
- [os.total_ram](#item-os.total_ram) — Put reserved HugeTLB capacity in the context of total host RAM.
- [os.lshw_memory](#item-os.lshw_memory) — Review physical memory and NUMA-related hardware inventory when pool placement is uneven.

## Checklist
- Match the pool row to PostgreSQL's effective huge-page size; do not add counts from different page sizes.
- Compare total, free, reserved, and free-unreserved pages before changing the reservation.
- Validate NUMA distribution against PostgreSQL CPU and memory placement.
- Reserve pages early in boot when runtime allocation fails because of fragmentation.
- Recollect both huge-page items after a kernel setting change and after the PostgreSQL restart.
