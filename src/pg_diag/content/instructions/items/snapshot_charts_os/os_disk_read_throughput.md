# Disk Read Throughput

This instruction belongs to report item `snapshot_charts_os.os_disk_read_throughput`. The item is backed by `os.disk_read_throughput` (snapshot metric).

## What this item shows
- Read throughput by block device over time.
- Which device reads data during the capture window.

## Units
- `B/s` means bytes read per wall-clock second. The chart scales the axis and tooltips together to adaptive IEC units such as `KiB/s`, `MiB/s`, or `GiB/s`.

## What to watch
- Sustained high reads on database device.
- Read spike during report or batch workload.
- Reads aligned with PostgreSQL shared block reads.

## Common fault causes
- Large scans.
- Cold cache.
- Backup or maintenance reads.
- Index/table reads beyond memory.

## Automatic evaluation
- Values come from interval `iostat -dxk` reports and are informational; storage limits and topology are external context.
- The first since-boot iostat report is discarded.

## Related report items
- [snapshot_charts_os.os_disk_latency](#item-snapshot_charts_os.os_disk_latency) — Determine whether read throughput is accompanied by latency.
- [snapshot_delta_workload.sql_io_delta](#item-snapshot_delta_workload.sql_io_delta) — Find SQL shared-block reads in the same window.
- [snapshot_delta_workload.table_io_delta](#item-snapshot_delta_workload.table_io_delta) — Attribute reads to relations.

## Checklist
- Map device to PostgreSQL mount.
- Compare with SQL shared I/O and table I/O.
- Check disk latency before assuming throughput is healthy.
