# Kernel VM Parameters

This instruction belongs to report item `os.sysctl_vm`. The item is backed by `os.sysctl_vm` (local host script).

## What this item shows
- Kernel virtual-memory settings relevant to writeback, overcommit, dirty pages, and swappiness.
- Runtime kernel values, not just configured files.

## What to watch
- Swappiness too high for database latency goals.
- Dirty page limits that can create writeback stalls.
- Overcommit settings inconsistent with memory planning.

## Common fault causes
- Default OS tuning left in place.
- Sysctl change not persisted.
- Configuration management drift.

## Automatic evaluation
- No severity is assigned: safe VM values depend on RAM, storage latency, kernel release, and workload.
- Only readable runtime `vm.*` keys are shown; this does not verify persistence in sysctl configuration files.

## Related report items
- [snapshot_charts_os.os_memory_pressure](#item-snapshot_charts_os.os_memory_pressure) — Compare VM settings with RAM and swap pressure.
- [snapshot_charts_os.os_memory_usage](#item-snapshot_charts_os.os_memory_usage) — Inspect memory composition under the configured policy.

## Checklist
- Compare VM sysctl values with platform baseline.
- Relate dirty/writeback settings to checkpoint and disk latency evidence.
- Persist approved changes through system configuration management.
