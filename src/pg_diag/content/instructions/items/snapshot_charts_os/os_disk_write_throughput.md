# Disk Write Throughput

This instruction belongs to report item `snapshot_charts_os.os_disk_write_throughput`. The item is backed by `os.disk_write_throughput` (snapshot metric).

## What this item shows
- Write throughput by block device over time.
- Which device receives writes during the capture window.

## Units
- `B/s` means bytes written per wall-clock second. The chart scales the axis and tooltips together to adaptive IEC units such as `KiB/s`, `MiB/s`, or `GiB/s`.

## What to watch
- Sustained high writes on WAL or data device.
- Write spike during checkpoint or bulk load.
- Writes aligned with WAL growth.

## Common fault causes
- WAL generation.
- Checkpoint writes.
- Bulk DML.
- Vacuum or index build.

## Automatic evaluation
- Values come from interval iostat reports and are informational; throughput alone does not indicate saturation.
- The first since-boot iostat report is discarded.

## Related report items
- [snapshot_charts_os.os_disk_latency](#item-snapshot_charts_os.os_disk_latency) — Determine whether write throughput is accompanied by latency.
- [snapshot_charts_db.wal_growth_rate](#item-snapshot_charts_db.wal_growth_rate) — Compare writes with WAL generation.
- [snapshot_delta_workload.checkpointer_delta](#item-snapshot_delta_workload.checkpointer_delta) — Check checkpoint write activity.

## Checklist
- Map device to WAL/data/archive path.
- Compare with WAL growth and checkpointer items.
- Check latency when throughput is high.
