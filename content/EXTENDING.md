# Extending The Report

This guide describes how to add new report items to the bundled `pg_diag`
content pack.

The content pack is declarative: `report.yaml` defines where an item appears,
catalog files define SQL sources, `scripts.yaml` defines local Bash sources, and
`metrics.yaml` defines charts and derived snapshot tables.

## Before You Start

- PostgreSQL versions 14 through 18 are supported. New SQL variants should use
  `min_pg_version: 140000` unless the source view exists only in a newer major
  version.
- `report.yaml` must stay lightweight. Do not describe table columns in report
  layout; table headers come from the actual SQL result.
- Every visible report item needs a Markdown instruction file under
  `instructions/items/<section>/<item>.md`.
- `catalog/*.yaml` is not loaded by glob. A new catalog file must be registered
  in `queries.yaml` under `query_catalog.files`.
- SQL used by metrics should expose stable `semantic_columns` so metrics do not
  depend on physical column names.
- SQL used by charts must return `statement_timestamp() as snapshot_time`.
- SQL should be read-only and should not create temporary objects. Snapshot
  joins, deltas, rates, and top-N calculations are done in the Python runtime.

Run validation after every content change:

```bash
pg-diag validate --content content
```

Preview the selected execution plan:

```bash
pg-diag explain-plan \
  --content content \
  --pg-version 180000 \
  --run-mode snapshots \
  --collection-mode local
```

## Add A SQL Table Item

Use this when the report needs another PostgreSQL result table.

1. Add a SQL file under `queries/<group>/<name>.sql`.

   Example:

   ```sql
   select
     current_database() as datname,
     locktype,
     mode,
     count(*)::int8 as locks
   from pg_locks
   group by locktype, mode
   order by locks desc, locktype, mode
   ```

2. Add a query manifest to an existing `catalog/<group>.yaml`, or create a new
   catalog file and register it in `queries.yaml`.

   Example:

   ```yaml
   queries:
     locks.mode_summary:
       title: Lock Mode Summary
       group: Activity & Locks
       main_view: pg_locks
       description: Current lock count by lock type and mode.
       display:
         default_sort:
           column: locks
           direction: desc
       collection:
         default: once
         supports: [once, every_snapshot]
       variants:
         - id: locks_mode_summary_pg14_plus
           min_pg_version: 140000
           sql_file: locks/mode_summary.sql
           semantic_columns:
             dimensions:
               database: datname
               locktype: locktype
               mode: mode
             gauges:
               locks: locks
   ```

3. Add a report item to an existing section in `report.yaml`.

   Example:

   ```yaml
   activity_locks:
     items:
       lock_mode_summary:
         query: locks.mode_summary
         state: collapsed
         render:
           empty_message: No locks visible to the current user.
   ```

The item title, description, SQL metadata, sort hint, and table shape are
inherited from the query catalog unless explicitly overridden by supported
report item keys.

4. Add the item instruction Markdown file.

   The default path is derived from the report item id:

   ```text
   instructions/items/activity_locks/lock_mode_summary.md
   ```

   Use this structure:

   ```markdown
   # Lock Mode Summary

   ## What this item shows
   - Current lock volume by lock type and mode.

   ## What to watch
   - Granted and waiting locks growing during the same incident window.

   ## Common fault causes
   - Long transactions, DDL, hot rows, or unindexed foreign key checks.

   ## Checklist
   - Find the root blocker before terminating sessions.
   - Compare with Activity & Locks and SQL Workload sections.
   ```

   The HTML report embeds this file and shows it with the item-level
   `Show Instruction` button.

## Add A Repeated-Snapshot Chart

Use this when the report needs a time-series chart from SQL samples.

1. Add a minimal source query. Keep it narrow and specific to the chart.

   Example:

   ```sql
   select
     statement_timestamp() as snapshot_time,
     current_database() as datname,
     xact_commit::int8 as xact_commit,
     xact_rollback::int8 as xact_rollback
   from pg_stat_database
   where datname = current_database()
   ```

2. Add the query manifest. The query must support `every_snapshot`.

   Example:

   ```yaml
   queries:
     metrics.transaction_counters:
       title: Transaction Counter Chart Source
       group: Metric Sources
       main_view: pg_stat_database
       description: Minimal transaction counters for chart metrics.
       display:
         default_sort:
           column: datname
           direction: asc
       collection:
         default: every_snapshot
         supports: [once, every_snapshot]
       variants:
         - id: metrics_transaction_counters_pg14_plus
           min_pg_version: 140000
           sql_file: metrics/transaction_counters.sql
           semantic_columns:
             dimensions:
               database: datname
             counters:
               commits: xact_commit
               rollbacks: xact_rollback
   ```

3. Add a metric to `metrics.yaml`.

   Example:

   ```yaml
   metrics.transaction_rate:
     title: Database Transaction Rate
     source_query: metrics.transaction_counters
     requires_collection: every_snapshot
     partition_by:
       - dimensions.database
     series:
       - name: commits
         value_ref: counters.commits
         transform: rate
         unit: tx/s
       - name: rollbacks
         value_ref: counters.rollbacks
         transform: rate
         unit: tx/s
     chart:
       kind: stacked_area
       unit: tx/s
   ```

4. Add the chart item to the DB snapshot chart section.

   Example:

   ```yaml
   snapshot_charts_db:
     items:
       database_transaction_rate:
         metric: metrics.transaction_rate
         state: collapsed
   ```

The planner promotes the metric source query to repeated collection in
`snapshots` mode. Prefer one dedicated `metrics.*` query per report item so
`Show SQL` and `Show meta` stay item-specific and isolated.

5. Add `instructions/items/snapshot_charts_db/<item>.md` for the chart item.

## Add A Top-N Chart

Top-N charts are computed from adjacent snapshots in memory. They are useful for
tables, indexes, functions, and statements where the most active objects can
change over time.

Example:

```yaml
objects.indexes_top_scan_rate:
  title: Top Indexes By Scan Rate
  source_query: metrics.objects_indexes_top_scan_rate
  requires_collection: every_snapshot
  top_n:
    mode: interval
    limit: 10
    key_refs: [dimensions.database, dimensions.schema, dimensions.table, dimensions.index]
    label_refs: [dimensions.schema, dimensions.table, dimensions.index]
    value_ref: counters.idx_scan
    transform: rate
    unit: scans/s
  chart:
    kind: stacked_column
    unit: scans/s
```

For large source views, limit candidates in SQL before collecting samples. For
example, an index workload query can keep only indexes with activity and sort by
relation size before applying `limit 100`.

## Add A Delta Or Rate Table Metric

Use a table metric when a report section should show start/end deltas or rates
instead of raw cumulative counters.

Example:

```yaml
database.workload_delta:
  title: Database Workload Delta
  source_query: metrics.database_workload_delta
  requires_collection: every_snapshot
  result: table
  display:
    default_sort:
      column: commits_per_sec
      direction: desc
  table:
    key_refs: [dimensions.database]
    limit: 50
    sort:
      column: commits_per_sec
      direction: desc
    columns:
      - name: datname
        role: key
        key_index: 0
      - name: commit_delta
        value_ref: counters.xact_commit
        transform: delta
        pg_type: float8
      - name: commits_per_sec
        value_ref: counters.xact_commit
        transform: rate
        pg_type: float8
      - name: rollback_delta
        value_ref: counters.xact_rollback
        transform: delta
        pg_type: float8
```

Supported table transforms include key columns, `delta`, `rate`, `last`, sample
counts, and aggregate transforms such as `sum`, `avg`, and `max` for sampled
data.

## Add A Local Bash Item

Use scripts for collector-host information that cannot be collected through
PostgreSQL SQL.

1. Add a script under `scripts/<group>/<name>.sh`.

2. Add a script declaration to `scripts.yaml`.

   Plain text example:

   ```yaml
   scripts:
     os.kernel_cmdline:
       title: Kernel Command Line
       description: Local kernel boot command line.
       script_file: os/kernel_cmdline.sh
       output: plain_text
       timeout_ms: 5000
   ```

   JSON table example:

   ```yaml
   scripts:
     os.device_inventory:
       title: Device Inventory
       description: Local device inventory rendered as a table.
       script_file: os/device_inventory.sh
       output: table_json
       timeout_ms: 15000
   ```

3. Add the script item to `report.yaml`.

   Example:

   ```yaml
   os:
     items:
       kernel_cmdline:
         script: os.kernel_cmdline
         state: collapsed
   ```

Scripts are local-only by default. In `remote-db-only` collection mode they are
kept in the report with skipped status and a skip message.

4. Add `instructions/items/<section>/<item>.md` so the skipped or collected
   script still has DBA guidance in the HTML report.

## Add An OS Sampler Chart

OS sampler metrics use threaded local samplers. They are available only in local
collection modes and only in `snapshots` mode.

Example:

```yaml
os.disk_read_throughput:
  title: Disk Read Throughput
  source_sampler: os.disk
  partition_by:
    - device
  series:
    - name: read
      value_ref: read_bytes_per_sec
      transform: gauge
      unit: bytes/s
  chart:
    kind: area
    unit: bytes/s
```

Then add the metric to `snapshot_charts_os`:

```yaml
snapshot_charts_os:
  items:
    os_disk_read_throughput:
      metric: os.disk_read_throughput
      state: collapsed
```

## Validation Checklist

Before committing a content change, check the following:

- New catalog files are listed in `queries.yaml`.
- Query IDs, script IDs, metric IDs, and report item IDs are unique.
- PostgreSQL variants use correct `min_pg_version` and optional
  `max_pg_version` boundaries.
- Every referenced SQL or Bash file exists.
- Every report item has a non-empty Markdown instruction file.
- Every SQL-backed chart query returns `snapshot_time`.
- Every metric `value_ref`, `key_ref`, `label_ref`, and `partition_by` entry has
  a matching semantic column or sampler field.
- Large cumulative views are pre-filtered in SQL before snapshot collection.
- `display.default_sort` points to an actual result column.
- Local-only scripts have reasonable timeouts and safe remote behavior.

Run:

```bash
pg-diag validate --content content
pg-diag explain-plan --content content --pg-version 180000 --run-mode snapshots --collection-mode local
```
