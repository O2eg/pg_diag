# WAL Receiver

This instruction belongs to report item `replication.wal_receiver`. The item is backed by `replication.wal_receiver` (SQL query).

## What this item shows
- The current `pg_stat_wal_receiver` row on a streaming standby, including textual receive/write/flush/end LSNs and timelines.
- Direct upstream `sender_host`/port, slot, receiver status, message timestamps, and latest-end-to-flushed byte gap.
- Only the directly connected upstream; it does not reconstruct the full replication topology.

## What to watch
- A row outside `streaming`, stale message receipt, a growing receive gap, or an unexpected upstream/slot.
- A timeline change between receive start and the latest received timeline.
- Receiver absence on a standby that is expected to use streaming replication.

## Automatic evaluation
- `medium`: a returned receiver row is not in `streaming` state.
- Empty is not automatically severe because it is normal on a primary and possible on archive-only recovery.
- Lag size and message age remain contextual.

## Common fault causes
- Primary/network/authentication/TLS failure, wrong `primary_conninfo`, missing sender capacity, or a disabled receiver.
- Archive-only recovery, promotion, or a standby that has not started streaming yet.

## Checklist
- Confirm `pg_is_in_recovery()`, intended upstream, receiver logs, and the sender row on the upstream.
- Treat `receive_lag_bytes` as the gap between the last upstream end reported and locally flushed WAL, not SQL apply latency.
- Compare repeated captures before diagnosing a stalled receiver.
- Empty means no receiver row was visible at capture time.
