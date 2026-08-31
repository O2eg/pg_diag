# Top Errors By Frequency

This instruction belongs to report item `server_log.top_errors`. The item is backed by `server_log.top_errors` (trusted Python source) and consumes the csvlog window collected with `--log-depth-time-min`.

## What this item shows
- The 100 most frequent error fingerprints (normalized messages: literals and numbers replaced by placeholders) with total occurrences, worst severity, SQLSTATE, first and last time seen, and how many distinct users and databases hit each error.
- `count_complete = false` marks counts that are lower bounds because a collection budget truncated the window.

## What to watch
- A fingerprint with high `occurrences` and a wide `first_seen .. last_seen` span: a chronic error nobody fixes.
- A new fingerprint with `first_seen` close to the window end: a fresh regression.
- High `distinct_users` or `distinct_databases`: the error is systemic, not one application's bug.

## Common fault causes
- Constraint violations and serialization failures under load.
- Statements broken by a recent schema change.
- Clients with wrong parameters retrying in a loop.

## Automatic evaluation
- `medium`: any error fingerprints exist in the window.
- `ok`: the collected window contains no error records.
- When coverage is partial, the summary says the ranking covers only the collected part of the window; already listed findings keep their severity.

## Related report items
- [server_log.error_chronology](#item-server_log.error_chronology) — The same window in time order with flood collapsing.
- [server_log.top_warnings](#item-server_log.top_warnings) — The same ranking for warnings.

## Checklist
- Fix the top fingerprint first: it usually removes most of the log volume.
- Check whether top errors correlate with specific users or databases before blaming the server.
