# Physical Replication Senders

This instruction belongs to report item `replication.physical_replication`. The item is backed by `replication.physical_replication` (SQL query).

## What this item shows
- A point-in-time row for every directly connected WAL sender in `pg_stat_replication` on a primary or cascading standby.
- Text LSN positions plus byte gaps for current-to-sent, sent-to-write, write-to-flush, flush-to-replay, and current-to-replay stages.
- PostgreSQL write/flush/replay lag intervals, reply age, sender state, synchronous state, and client identity where visible.

## What to watch
- A sender that remains outside `streaming`, growing byte gaps across captures, or unexpectedly stale replies.
- Which stage grows: sender backlog, network/write, remote flush, or replay.
- An unexpected `sync_state`; this must be compared with `synchronous_standby_names` and the intended topology.

## Automatic evaluation
- `medium`: a returned WAL sender row is not in `streaming` state.
- Byte or time lag has no universal threshold and does not assign severity.
- A missing expected standby cannot be classified automatically because pg_diag has no topology inventory.

## Common fault causes
- Initial catch-up, base backup, network loss, slow standby storage/replay, or a stopped receiver.
- Intentional asynchronous replication or a topology change.
- Restricted statistics visibility can hide user or client details without hiding the row.

## Checklist
- Compare at least two captures; PostgreSQL lag intervals describe recent commit delay and are not a catch-up-time prediction.
- Preserve LSN text when comparing timelines; byte gaps alone do not identify timeline history.
- Check the matching receiver, replication slot, PostgreSQL logs, and synchronous replication configuration.
- Empty is normal when this server has no directly connected WAL senders.
