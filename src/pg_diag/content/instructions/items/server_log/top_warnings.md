# Top Warnings By Frequency

This instruction belongs to report item `server_log.top_warnings`. The item is backed by `server_log.top_warnings` (trusted Python source) and consumes the csvlog window collected with `--log-depth-time-min`.

## What this item shows
- The 100 most frequent `WARNING` fingerprints with total occurrences, first and last time seen, and how many distinct users and databases produced each warning.
- The first and last time seen answer "did this just start" without reading the raw log.

## What to watch
- Warnings that started recently: often the early signal of a coming failure (wraparound, connection saturation, checkpoint pressure).
- Persistent high-volume warnings: they hide new problems and inflate log volume.

## Common fault causes
- Applications ignoring deprecation or misuse warnings for years.
- Autovacuum and checkpoint tuning warnings left unaddressed.

## Automatic evaluation
- `ok`: warnings are informational here; frequency ranking is the value, severity comes from dedicated items.
- When coverage is partial, occurrences are lower bounds and the summary says so.

## Related report items
- [server_log.top_errors](#item-server_log.top_errors) — The same ranking for errors.

## Checklist
- Silence or fix chronic warnings so new ones become visible.
- Treat a warning fingerprint that appeared today as a change signal: find what changed.
