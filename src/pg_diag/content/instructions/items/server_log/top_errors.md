# Top Errors By Frequency

This instruction belongs to report item `server_log.top_errors`. The item is backed by `server_log.top_errors` (trusted Python source) and consumes the csvlog window collected with `--log-depth-time-min`.

## What this item shows
- The 100 most frequent error fingerprints (normalized messages: literals and numbers replaced by placeholders) with total occurrences, worst severity, SQLSTATE, first and last time seen, and arrays of distinct user and database names affected by each error.
- `distinct_users` and `distinct_databases` are sorted, deduplicated arrays, each limited to 30 names by `python.yaml` → `python_sources.server_log.top_errors.settings.distinct_names_limit` (a positive integer).
- Missing names produce empty arrays. When names are omitted, the summary reports truncation; `omitted_user_name_count` and `omitted_database_name_count` count omitted names across displayed groups in the result metadata.
- Count completeness is result metadata, not a table column. `count_complete = false` means counts are lower bounds because collection was incomplete.

- `Query id` links open the retained SQL from the report-wide catalog. A fingerprint may list multiple queries; unavailable/zero PostgreSQL IDs use the first 20 hex characters of SHA256, displayed without a prefix. Each ID occurs once per group and opens the first saved SQL sample. Text is capped at 2000 characters, with a truncation note.

## What to watch
- A fingerprint with high `occurrences` and a wide `first_seen .. last_seen` span: a chronic error nobody fixes.
- A new fingerprint with `first_seen` close to the window end: a fresh regression.
- Many names in `distinct_users` or `distinct_databases`: inspect whether the error affects several applications.

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
