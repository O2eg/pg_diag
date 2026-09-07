# pg_play integration contract

This document is for orchestrator authors. Normal users retain the report,
render, inspect, and collection CLI documented in the README.

`pg_diag` supports the hidden `pg_play/component/v1` machine transport:

```bash
pg-diag --machine --request-id diag-001 --component-capabilities
pg-diag --machine --request-id diag-002 explain-plan \
  --pg-version 180000 --run-mode snapshots --collection-mode remote-db-only
pg-diag --machine --request-id diag-003 validate-artifact report.json
pg-diag --machine --request-id diag-004 summarize report.json
pg-diag --machine --request-id diag-005 configuration-facts report.json \
  --out configuration-facts.json
```

The capability document uses `pg_play/capabilities/v1`. Every command declares
the common boolean fields `mutates_target`, `machine_output`, and
`accepts_plan_hash`.
Its `machine_interface` object records the canonical machine, request-id, and
capability option names.

One-shot and snapshots collection commands also return the common machine
envelope. Report files are described by paths and SHA-256 hashes. Partial
collection remains `partial`; it is not promoted to success merely because a
JSON artifact exists.

Orchestrators may pass `--log-depth-time-min N` (0-1440) to the collection
commands to enable the `server_log` section for the last `N` minutes of the
server csvlog; pg_play forwards `spec.diagnostics.log_depth_time_min` this
way. The log phase never fails the report: its outcome is recorded in
`runtime.log_collection` (`{status, reason, coverage, source}`), and the
section is collected only in `local` and `remote` collection modes (see
`access-best-practices.md`, "Server log access"). `source.kind` is `database`
for these commands.

The `logs` command is the third machine collection command: it takes
`--log-dir` (and optionally `--log-timezone`, `--log-depth-time-min`,
`--item-id`/`--tags`/`--item-type`), never connects to PostgreSQL, returns the
same envelope and artifact descriptors as `one-shot`, and writes an artifact
with `runtime.mode: "logs"` whose `runtime.log_collection.source.kind` is
`directory` (with the detected `csv_format` and discovery counters). All three
collection commands accept `--item-type table,text,chart,delta`, and every
artifact item now carries `item_type`.

`summarize` validates the artifact schema before returning deterministic
counts, completeness, severities, collection statuses, snapshot count, and
fallback degradation. A successful replacement may keep completeness at 100%
and `has_errors` false while setting `degraded: true`; `fallback_items` lists
the affected parent IDs, triggers, and final statuses. It does not interpret
findings or apply remediation.

`configuration-facts` validates the source report and extracts the stable
`pg_diag/configuration-facts-v1` subset used by configuration tools. The facts
artifact preserves its source hash and item completeness. Missing CPU, RAM,
server-version, or `pg_settings` items make `collection.usable` false instead
of silently substituting host-local defaults.
