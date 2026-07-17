# Processor Hardware

This instruction belongs to report item `os.lshw_processor`. The item is backed by `os.lshw_processor` (local host script).

## What this item shows
- Processor hardware inventory from lshw.
- CPU model and hardware capability context.

## What to watch
- Unexpected CPU model or count.
- Different CPU generation across nodes.
- Missing hardware data.

## Common fault causes
- VM resized incorrectly.
- Host migration to different CPU class.
- lshw permission limits.

## Automatic evaluation
- No severity is assigned without an approved CPU baseline.
- Empty or partial lshw output should be cross-checked with `CPU Information` from `lscpu`.

## Related report items
- [os.cpu_info](#item-os.cpu_info) — Cross-check processor inventory with lscpu topology.
- [snapshot_charts_os.os_cpu_utilization](#item-snapshot_charts_os.os_cpu_utilization) — Inspect utilization of the reported CPUs.

## Checklist
- Compare with `CPU Information`
- Check extension or JIT assumptions that depend on CPU features.
- Confirm primary and standby CPU class consistency.
