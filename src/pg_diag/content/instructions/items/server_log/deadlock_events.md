# Deadlock Events

This instruction belongs to report item `server_log.deadlock_events`. The item is backed by `server_log.deadlock_events` (trusted Python source) and consumes the csvlog window collected with `--log-depth-time-min`.

## What this item shows
- Records with SQLSTATE `40P01` (`deadlock detected`), newest first, up to 100.
- The sanitized `detail` column (csvlog DETAIL) names the processes and lock waits involved; query text and literals are redacted or replaced with placeholders.
- Detection is based on SQLSTATE and remains available when `lc_messages` is not English; the displayed message stays in the server's language.
- `matched_event_count` counts all SQLSTATE 40P01 events, including RLE repeats. `displayed_event_count` and `omitted_event_count` distinguish the 100-row presentation limit from collection coverage. The summary and diagnostic graph use the full matched count.
- Supplemental `LOG: process ... detected deadlock while waiting for ...` messages appear as `deadlock_detected` in `server_log.lock_waits`. They are context, not additional deadlock incidents.

## What to watch
- Repeated deadlocks between the same relations: a stable application ordering bug, not bad luck.
- Deadlocks clustered in time: batch jobs colliding with online traffic.

## Common fault causes
- Transactions locking the same rows or tables in different orders.
- Foreign-key updates combined with explicit locking.
- Long transactions widening the conflict window.

## Automatic evaluation
- `medium`: any deadlock occurred in the window.
- `ok`: the collected window contains no deadlocks.

## Related report items
- [activity_locks.blocking_lock_tree](#item-activity_locks.blocking_lock_tree) — Live lock waits at collection time.
- [server_log.error_chronology](#item-server_log.error_chronology) — Deadlocks in the context of other errors.

## Checklist
- Make conflicting transactions acquire locks in one global order.
- Shorten transactions that appear in deadlock messages.
- Retry deadlocked transactions in the application, but fix the ordering too.
