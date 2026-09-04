# Replication And WAL Transport Events

This instruction belongs to report item `server_log.replication_events`. The item consumes the csvlog window collected with `--log-depth-time-min`.

## What this item shows
- Archive/restore command failures, WAL sender/receiver disconnects, missing WAL, timeline mismatch, replication-slot problems, logical-replication failures, and recovery conflicts.
- Up to 100 highest-frequency/recent series. The existing focused `archiver_failures` item remains available and unchanged.
- These classifications use localized message text and therefore require C/POSIX/English `lc_messages`.

## What to watch
- Missing/removed WAL or timeline mismatch: a replica may require a new base backup or corrected recovery target.
- Repeating archive/restore failures and slot invalidation: retention and recovery-point objectives are at risk.
- Logical worker/subscription failures that repeat after automatic restart.

## Common fault causes
- Broken archive/restore command, credentials, network, full storage, insufficient WAL retention, or stale timeline history.
- Slot retention exceeding `max_slot_wal_keep_size`, changed publication/schema, or apply conflicts.

## Automatic evaluation
- Any matched row requires review and is high priority unless evidence is incomplete, in which case severity is `unknown`.
- `omitted_series_count` reports the fixed 100-row limit; collection truncation makes counts lower bounds.

## Related report items
- [server_log.archiver_failures](#item-server_log.archiver_failures) — Focused archive-command evidence.
- [server_log.server_lifecycle](#item-server_log.server_lifecycle) — Promotion and recovery chronology.

## Checklist
- Validate sender/receiver state, slots, retained WAL, timelines, archive destination, restore source, and replica replay progress.
- Correlate repeated disconnects with network and server lifecycle events before changing timeouts.
