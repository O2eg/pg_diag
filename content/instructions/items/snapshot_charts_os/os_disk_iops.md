# Disk IOPS

This instruction belongs to report item `snapshot_charts_os.os_disk_iops`. The item is backed by `os.disk_iops` (snapshot metric).

## What this item shows
- Read and write operations per second by device.
- Small-random-I/O pressure during snapshots mode.

## What to watch
- High write IOPS with high latency.
- High read IOPS on data device.
- IOPS near storage tier limit.

## Common fault causes
- Index-heavy workload.
- Random reads from cache misses.
- WAL fsyncs.
- Checkpoint bursts.

## Automatic evaluation
- Read and write IOPS share a denominator and are stacked per device.
- No universal severity is assigned because acceptable IOPS depends on request size, latency, queueing, and storage tier.

## Checklist
- Compare IOPS with throughput and latency.
- Check storage tier limits.
- Map device to PostgreSQL paths.
