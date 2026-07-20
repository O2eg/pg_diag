# Logical Decoding Slot Delta

This instruction belongs to report item `snapshot_delta_workload.logical_decoding_slot_delta`.

## What this item shows
- Transactions and bytes spilled, streamed, and emitted by each logical decoding slot during the window.

## What to watch
- Repeated spill activity and high spill bytes, which indicate logical decoding exceeded its memory budget.

## Automatic evaluation
- No severity is assigned because spilling can be acceptable for large transactions and bounded workloads.

## Interval coverage
- Slot name is the stable key and `stats_reset` is the reset epoch.
- New, dropped, or reset slots are omitted rather than represented as zero deltas.

## Common fault causes
- Large transactions, insufficient `logical_decoding_work_mem`, slow consumers, and output-plugin behavior.

## Related report items
- [replication.replication_slots](#item-replication.replication_slots) — Inspect current logical-slot state and retained WAL.
- [snapshot_charts_db.wal_growth_rate](#item-snapshot_charts_db.wal_growth_rate) — Compare slot retention with WAL growth.
- [snapshot_delta_workload.subscription_errors_conflicts_delta](#item-snapshot_delta_workload.subscription_errors_conflicts_delta) — Check downstream subscription failures.

## Checklist
- Compare spill and stream bytes with transaction size and consumer throughput.
- Review retained WAL and slot activity before tuning or dropping a slot.
