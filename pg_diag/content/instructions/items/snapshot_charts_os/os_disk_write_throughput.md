# Disk Write Throughput

This instruction belongs to report item `snapshot_charts_os.os_disk_write_throughput`. The item is backed by `os.disk_write_throughput` (snapshot metric).

## What this item shows
- Write throughput by block device over time.
- Which device receives writes during the capture window.

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

## Checklist
- Map device to WAL/data/archive path.
- Compare with WAL growth and checkpointer items.
- Check latency when throughput is high.
