# Disk Read Throughput

This instruction belongs to report item `snapshot_charts_os.os_disk_read_throughput`. The item is backed by `os.disk_read_throughput` (snapshot metric).

## What this item shows
- Read throughput by block device over time.
- Which device reads data during the capture window.

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

## Checklist
- Map device to PostgreSQL mount.
- Compare with SQL shared I/O and table I/O.
- Check disk latency before assuming throughput is healthy.
