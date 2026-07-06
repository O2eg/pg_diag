# CPU Load Average

This instruction belongs to report item `snapshot_charts_os.os_cpu_load`. The item is backed by `os.cpu_load` (snapshot metric).

## What this item shows
- System load average over the snapshot window.
- Runnable or waiting task pressure relative to CPU capacity.

## What to watch
- Load far above CPU count.
- Load spike without matching CPU utilization.
- Sustained load during database latency.

## Common fault causes
- CPU saturation.
- Tasks waiting on I/O.
- Host contention from non-PostgreSQL processes.

## Checklist
- Compare load with CPU utilization and disk latency.
- Check host process list outside pg_diag when load is unexplained.
- Use CPU count from CPU Information for context.
