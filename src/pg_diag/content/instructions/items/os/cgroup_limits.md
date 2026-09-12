# Container And cgroup Limits

This instruction belongs to report item `os.cgroup_limits`. The item is backed by `os.cgroup_limits` (local host script).

## What this item shows
- The CPU quota (`cpu_quota_us` / `cpu_period_us`, summarized as `cpu_limit_cores`), the effective cpuset, the memory limit, high watermark, current usage, swap limit and pid limit of the cgroup that contains the PostgreSQL postmaster, read from the cgroup filesystem (cgroup v2 or v1).
- The script finds postmasters as `postgres` processes whose parent is not one, resolves each one's cgroup through `/proc/<pid>/cgroup` and the cgroup mount, and walks every ancestor group, so a limit set on a systemd slice, a Kubernetes pod or a Docker scope is found wherever it sits. `cpu_limit_source` and `memory_limit_source` name the directory that imposes each limit; `cgroup_path` is the postmaster's own group.
- `scope` says whose cgroup was measured: `postmaster` (one row per distinct postmaster cgroup, `postmaster_count` processes in it, `cgroup_count` distinct groups on the host) or `collector` when no postmaster is visible to the collector, for example a remote database with local host scripts. Collector limits are not database limits.
- `host_online_cpus` and `host_memory_total_bytes` for comparison: `/proc/stat`, `/proc/meminfo`, `lscpu` and the OS charts describe the whole host even when PostgreSQL runs inside a container.
- `container_hint` (`docker`, the `container` environment variable, or a container-like cgroup path) as evidence that a limit is expected; `path_resolved = false` means the postmaster's cgroup path is not visible from the collector's cgroup namespace and the visible root was read instead.
- Absent limits are `null`; the script never converts "no limit" into zero.

## What to watch
- `cpu_limit_cores` far below `host_online_cpus`: CPU percentages in the OS charts are host-wide and understate saturation inside the container (100% of two cores reads as 12.5% of sixteen).
- `memory_limit_bytes` far below `host_memory_total_bytes`: `shared_buffers`, `work_mem` and `effective_cache_size` must be sized against the limit, and the kernel OOM killer acts at the cgroup boundary while the host still shows free memory.
- `memory_current_bytes` close to `memory_limit_bytes` during the capture window (`memory.current` includes reclaimable page cache, so headroom is understated rather than overstated).
- A `pids_max` that a connection storm plus parallel workers could reach.
- `cgroup_count` above 1: several PostgreSQL instances run in different cgroups on this host and the report cannot tell which row is this database. Host capacity is not used as a substitute: the embedded configurator asks for the container allocation explicitly, the `configuration-facts` contract reports `effective_cpu_cores` / `effective_ram_bytes` as null, and pg_play refuses to size a configuration until `db_cpu` / `db_ram` are given.

## Common fault causes
- Container orchestration limits set for a smaller workload than the one deployed.
- Configuration copied from the host or from a bigger container.
- A cpuset shared with noisy neighbours, which the quota alone does not reveal.
- A limit inherited from a parent slice or pod that nobody set on the service itself.

## Automatic evaluation
- No severity is assigned: the limits are capacity facts.
- Consumers apply the limits only when the row is unambiguous (`scope = postmaster`, one postmaster cgroup); a `collector` row is shown for reference only and, with several postmaster cgroups, capacity is treated as unknown rather than taken from the host: the embedded configurator and the `configuration-facts` CLI contract (`host.effective_cpu_cores`, `host.effective_ram_bytes`) use the smaller of host capacity and the limit; the diagnostic graph sizes `shared_buffers` and the `work_mem` budget against the limit and judges memory headroom inside the cgroup from `memory_current_bytes` against `memory_limit_bytes`, while host `MemAvailable` stays a host-level ratio.
- In remote DB-only mode the item is skipped like every other host script.

## Related report items
- [os.total_ram](#item-os.total_ram) — Host RAM that the limit may cap.
- [os.cpu_info](#item-os.cpu_info) — Host CPU topology that the quota may cap.
- [snapshot_charts_os.os_cpu_utilization](#item-snapshot_charts_os.os_cpu_utilization) — Host-wide CPU percentages to renormalize against `cpu_limit_cores`.
- [snapshot_charts_os.os_memory_usage](#item-snapshot_charts_os.os_memory_usage) — Host-wide memory stack to compare with `memory_limit_bytes`.

## Checklist
- Size PostgreSQL memory settings against `memory_limit_bytes`, not against host RAM, when a limit exists.
- Renormalize CPU charts against `cpu_limit_cores` before concluding that CPU headroom exists.
- Check the orchestrator (docker, Kubernetes requests/limits, systemd `CPUQuota`/`MemoryMax`) when the cgroup shows a limit the team did not expect, and `cpu_limit_source` / `memory_limit_source` to see where it is set.
- With `cgroup_count` above 1, identify this database's postmaster (`postmaster.pid` in the data directory) before applying any row.
