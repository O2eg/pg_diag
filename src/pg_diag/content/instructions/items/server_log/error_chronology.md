# Error Chronology From Server Log

This instruction belongs to report item `server_log.error_chronology`. The item is backed by `server_log.error_chronology` (trusted Python source) and consumes the csvlog window collected with `--log-depth-time-min`.

## What this item shows
- The newest 100 series of `ERROR`, `FATAL`, and `PANIC` records from csvlog, newest first.
- Adjacent identical errors (same severity, SQLSTATE, and normalized message, gap under one minute) collapse into one series with `repeat_count`, `first_time`, and `last_time`, so a flood of one repeated error occupies one row instead of pushing unique errors out of the list.
- The sanitized first line of each message: quoted literals become placeholders and secrets are redacted before the text reaches the report.
- `count_complete = false` marks a series whose count is a lower bound because the window was truncated by a budget.

## What to watch
- `FATAL` and `PANIC` rows: backend or postmaster failures, not application errors.
- Series with very large `repeat_count`: one client retrying a broken statement can dominate the log and hide real incidents.
- `partial = true` rows: the record was multiline or oversized and only its first line was parsed.

## Common fault causes
- Application retry loops repeating one failing statement.
- Schema drift: queries referencing dropped columns or tables.
- Resource exhaustion surfacing as repeated identical errors.

## Automatic evaluation
- `high`: at least one `FATAL` or `PANIC` series is present.
- `medium`: only `ERROR` series are present.
- `ok`: the collected window contains no error records.

## Related report items
- [server_log.top_errors](#item-server_log.top_errors) — The same window ranked by frequency instead of chronology.
- [server_log.crash_recovery_events](#item-server_log.crash_recovery_events) — Crash and corruption markers extracted from the same window.

## Checklist
- Investigate `FATAL`/`PANIC` series first, then the newest `ERROR` series.
- For flood series, fix the retrying client before reading further: the log is cheaper without it.
- Correlate timestamps with deploys, failovers, and maintenance windows.
