# Query Termination Events By Minute

This instruction belongs to report item `server_log.query_termination_events`. The item consumes the csvlog window collected with `--log-depth-time-min`.

## What this item shows
- A minute-aligned stacked-column chart for statement/lock timeouts, user cancellation, recovery conflicts, administrative shutdown, client disconnections, and NOWAIT/lock-not-available failures.
- Identical events are aggregated within each minute by classification, SQLSTATE, database/user/application, query identity, message, and SQL sample before ranking. Each point retains the full occurrence count for its group, including bursts of more than ten repetitions.
- Up to ten ranked groups per minute and 2,000 points overall. Repeated message and SQL samples are stored once in `references` and points contain only `message_ref`/`query_ref`.
- Hover shows the first event time, classification, group occurrence count, SQLSTATE, database/user/application, query, and message when available. The artifact also retains `last_log_time`. The legend is hidden because ranks change each minute.


- SQLSTATE `55P03` with `lock timeout` is classified as `lock_timeout`; other lock-not-available cases retain their own classification.
- Generic send/receive failures and `connection to client lost` are `client_disconnect` only for `client backend`. Missing backend type is reported as `connection_disconnect`; walsender/walreceiver failures stay with replication. These messages describe connection events, not necessarily an executing query.
- `unexpected EOF on client connection with an open transaction` is retained as `client_disconnect_open_transaction`, including LOG/08006 records. It indicates an interrupted transaction/session, not necessarily an executing query.

## What to watch
- Bursts after a deploy, failover, lock pile-up, or timeout change.
- Recovery conflicts concentrated on a replica and administrative shutdown events around lifecycle transitions.
- `event_count` counts all matched events; `displayed_event_count` and `omitted_event_count` separate shown and discarded occurrences. `omitted_point_count` counts groups discarded by either the per-minute or global limit. Any such omission makes the chart partial and sets severity to `unknown`.
- `reference_omitted_count` reports evidence omitted by the reference payload budgets.

## Common fault causes
- `statement_timeout`/`lock_timeout`, explicit client cancellation, NOWAIT locking, hot-standby recovery conflict, or shutdown/failover.

## Automatic evaluation
- SQLSTATE-driven categories work across locales; English text only refines the generic cancellation subtype.
- Any event requires review. Incomplete collection or payload omission sets severity to `unknown`; counts become lower bounds when collection is incomplete.

## Related report items
- [server_log.lock_waits](#item-server_log.lock_waits) — Blocking evidence.
- [server_log.server_lifecycle](#item-server_log.server_lifecycle) — Shutdown/failover context.

## Checklist
- Correlate minute peaks with lock waits, application logs, deployments, replay delay, and timeout configuration.
- Fix the cause before broadly raising timeouts; a cancellation often protects system capacity.
