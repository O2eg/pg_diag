# Disk Utilization

This instruction belongs to report item `snapshot_charts_os.os_disk_utilization`. The item is backed by `os.disk_utilization` (snapshot metric).

## What this item shows
- Device busy percentage over time.
- Whether a block device is saturated during the capture.

## What to watch
- Sustained utilization near 100 percent.
- Utilization high while latency rises.
- One device saturated while others are idle.

## Common fault causes
- Storage bottleneck.
- Checkpoint burst.
- Autovacuum or bulk load.
- Noisy neighbor on shared storage.

## Automatic evaluation
- This chart is informational; `%util` saturation semantics differ for rotating, SSD, virtual, and parallel devices.
- Always interpret utilization with latency and queue depth.

## Checklist
- Correlate with disk latency and PostgreSQL I/O.
- Identify which PostgreSQL path is on the saturated device.
- Avoid tuning SQL until storage saturation is understood.
