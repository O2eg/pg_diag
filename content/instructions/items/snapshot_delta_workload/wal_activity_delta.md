# WAL Activity Delta

This instruction belongs to report item `snapshot_delta_workload.wal_activity_delta`.

## What this item shows
- WAL records, full-page images, bytes, buffer-full events, and WAL byte rate generated during the window.

## What to watch
- High full-page-image volume after checkpoints and any increase in `wal_buffers_full_delta` under sustained write load.

## Automatic evaluation
- No severity is assigned because WAL volume must be evaluated against workload and recovery requirements.

## Interval coverage
- Values require unchanged `pg_stat_wal.stats_reset`; a reset invalidates the interval.

## Common fault causes
- Bulk DML, index maintenance, full-page writes after checkpoints, logical decoding, and undersized WAL buffers.

## Checklist
- Compare WAL bytes with SQL WAL Delta and checkpoint activity.
- Confirm whether the observed volume matches expected transaction throughput.
