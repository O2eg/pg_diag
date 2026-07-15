# Extending The Report

All new items and charts must comply with
[`ITEM_DEVELOPMENT_SPEC.md`](ITEM_DEVELOPMENT_SPEC.md). In particular, sources
return canonical raw values, every displayed numeric or temporal field declares
an explicit unit, and sorting uses raw typed data rather than formatted text.

This guide describes how to add new report items to the bundled `pg_diag`
content pack.

The content pack is declarative: `report.yaml` defines where an item appears,
catalog files define SQL sources, `scripts.yaml` defines local Bash sources,
`python.yaml` defines trusted Python sources, and `metrics.yaml` defines charts
and derived snapshot tables.

## Before You Start

- PostgreSQL versions 14 through 18 are supported. New SQL variants should use
  `min_pg_version: 140000` unless the source view exists only in a newer major
  version.
- `report.yaml` must stay lightweight. Do not describe table columns in report
  layout; table headers come from the actual SQL result.
- Every visible report item needs a Markdown instruction file under
  `instructions/items/<section>/<item>.md`.
- Every report item needs at least one tag from
  `report.allowed_item_tags`. Keep three to five items in each section
  `state: expanded`; use `collapsed` for the rest unless an item is hidden.
- `catalog/*.yaml` is not loaded by glob. A new catalog file must be registered
  in `queries.yaml` under `query_catalog.files`.
- SQL used by metrics should expose stable `semantic_columns` so metrics do not
  depend on physical column names.
- Every metric table column declares `pg_type`, including keys and text fields,
  so an empty result has the same schema as a populated result.
- Reuse `presentation.yaml` only for unambiguous global rules. Ambiguous fields
  require a source override or an explicit descriptor in their source manifest.
- SQL used by charts must return `statement_timestamp() as snapshot_time`.
- Every database connection is opened with
  `default_transaction_read_only=on` and fails closed if PostgreSQL does not
  confirm read-only mode. SQL should also be read-only by construction and
  should not create temporary objects. Snapshot
  joins, deltas, rates, and top-N calculations are done in the Python runtime.

The executable-content integrity baseline covers `*.py`, `*.sh`, `*.sql`,
`*.yaml`, and `*.yml`, but not Markdown. In the vendor source tree, refresh that
baseline only through the release maintenance workflow after the content change
has been reviewed. The public validation command intentionally neither repairs
nor accepts an unknown protected-content set.

After any required vendor baseline update, run validation for every content
change:

```bash
pg-diag validate
```

Preview the selected execution plan:

```bash
pg-diag explain-plan \
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
       database_scope: current_database
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
        tags: [Locks]
        state: collapsed
        render:
          empty_message: No locks found.
   ```

The item title, description, SQL metadata, sort hint, and table shape are
inherited from the query catalog unless explicitly overridden by supported
report item keys. Every report item must define at least one validated `tags`
entry. Use `render.empty_message` when an empty table, empty chart, or no-result
payload needs item-specific wording in the HTML report.

Every non-OS item inherits `database_scope: all_databases` from
`defaults.item`. Override it with `database_scope: current_database` when the
source can only inspect the connection database. The report appends
`(All databases)` or `(Only DB_NAME)` to every such item title. Pure OS
sections declare `show_database_scope: false`.

For `current_database`, top-level `datname` and `database_name` table columns
are omitted from the final presentation because the title already identifies
the database; source snapshots and metric identity still retain them.
Query-backed metrics must repeat the same explicit scope as their source query.

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
   High-cardinality sources must use deterministic `ORDER BY ... LIMIT` before
   rows enter collector memory; do not remove this bound to obtain a global
   Top-N.

   Example:

   ```sql
   select
     statement_timestamp() as snapshot_time,
     datname,
     xact_commit::int8 as xact_commit,
     xact_rollback::int8 as xact_rollback
   from pg_stat_database
   where datname is not null
   ```

   Different keys in adjacent bounded samples are expected. The metric engine
   computes deltas only for the intersection and records
   `missing_start`/`missing_end` as informational unmatched coverage. It never
   substitutes zero for an unmatched key. Counter decreases and malformed
   values are invalid intervals and produce gaps plus diagnostics.

2. Add the query manifest. The query must support `every_snapshot`.

   Example:

   ```yaml
   queries:
     metrics.transaction_counters:
       title: Transaction Counter Chart Source
       database_scope: all_databases
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
     database_scope: all_databases
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
        tags: [Databases, Transactions]
        state: collapsed
   ```

The planner promotes the metric source query to repeated collection in
`snapshots` mode. Prefer one dedicated `metrics.*` query per report item so
`Show SQL` and `Show meta` stay item-specific and isolated.

When a change introduces a new configuration field, add its canonical path or
wildcard path to `field_reference.yaml`. This keeps every node in the `Show
meta` Raw YAML view documented. Dynamic ids use `*`, for example
`metrics/*/chart/kind`; list entries use `[]`, for example
`metrics/*/series[]/value_ref`.
Do not add a catch-all `*` entry. Validation requires a specific exact or
wildcard-aware description for every effective path.

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

Its source query manifest must declare:

```yaml
collection:
  default: window_endpoints
  supports: [once, window_endpoints]
```

Example:

```yaml
database.workload_delta:
  title: Database Workload Delta
  database_scope: all_databases
  source_query: metrics.database_workload_delta
  requires_collection: window_endpoints
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
        pg_type: text
      - name: commit_delta
        value_ref: counters.xact_commit
        transform: delta
        pg_type: int8
      - name: commits_per_sec
        value_ref: counters.xact_commit
        transform: rate
        pg_type: float8
      - name: rollback_delta
        value_ref: counters.xact_rollback
        transform: delta
        pg_type: int8
```

Supported endpoint-table transforms include key columns, `delta`, `rate`, and
`last`. A window endpoint source executes only at the start and end of the timed
chart window; its raw rows are not persisted in the artifact snapshot array.

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
   ```

   JSON table example:

   ```yaml
   scripts:
     os.device_inventory:
       title: Device Inventory
       description: Local device inventory rendered as a table.
       script_file: os/device_inventory.sh
       output: table_json
   ```

3. Add the script item to `report.yaml`.

   Example:

   ```yaml
   os:
     items:
      kernel_cmdline:
        script: os.kernel_cmdline
        tags: [Kernel]
        state: collapsed
   ```

Scripts are local-only by default. In `remote-db-only` collection mode the
planner does not execute them and omits their items from JSON/HTML. The item id
and skip reason are written to stdout and `report.log`.

Host shell scripts inherit `runtime_policy.default_shell_timeout_ms`; an optional
per-source `timeout_ms` can only reduce that bound. Local-only Python sources
inherit their catalog timeout. Neither host source type may exceed `1000 ms`.
A timeout is attached to that item as its collection error and rendered in place
of the expected result; it does not abort unrelated items when `fail_fast` is
disabled.

4. Add `instructions/items/<section>/<item>.md` so the collected script has DBA
   guidance in reports produced by applicable collection modes.

## Add A Trusted Python Item

Use Python sources for trusted content-pack checks that need procedural logic,
multiple SQL calls, local file parsing, or structured issue output.

1. Add a Python file under `python/<group>/<name>.py`.

   The function receives a `PythonSourceContext` and returns a
   `PythonSourceResult` or compatible mapping:

   ```python
   from pg_diag.executors.python import PythonSourceResult, table_result


   async def collect(ctx):
       rows = await ctx.conn.fetch("select current_database() as datname")
       return PythonSourceResult(
           collection_status="ok",
           result=table_result([dict(row) for row in rows]),
           severity_level="ok",
       )
   ```

2. Add a source declaration to `python.yaml`.

   ```yaml
   python_sources:
     security.database_identity:
       title: Database Identity
       description: Example trusted Python source.
       python_file: security/database_identity.py
       function: collect
       local_only: false
       timeout_ms: 5000
   ```

3. Add the Python item to `report.yaml`.

   ```yaml
   cluster_inventory:
     items:
       database_identity:
         python: security.database_identity
         tags: [Security]
         state: collapsed
   ```

Local-only Python sources are not executed and are omitted from JSON/HTML in
`remote-db-only` collection mode; their item ids and skip reasons remain in
stdout and `report.log`. Use `local_only: true` when the function reads host
files such as PostgreSQL configuration files. Read host state only through async
`ctx.host` operations (`stat`, `read_text`, `read_bytes`, `list_dir`, `glob`,
`run`, or `run_script`). This keeps one evaluator valid in both `local` and
full SSH `remote` modes; direct `Path.read_*`, `Path.stat`, `subprocess`, and
collector-local environment access are incorrect for a local-only source.

For a cluster-wide database inventory, list databases through `ctx.conn` and
open each target sequentially with
`async with ctx.connect_database(database_name, timeout_seconds=...) as conn`.
The additional connection reuses the configured database endpoint or SSH
tunnel, enforces read-only startup settings, verifies read-only state, and is
closed when its context exits.

4. Add `instructions/items/<section>/<item>.md` for the item.

## Add SQL Result Evaluation

Use automatic severity only for direct, low-ambiguity findings. A SQL finding
table can expose `risk_level`/`risk_reason`. A normal diagnostic table can keep
evaluation fields out of the displayed result by returning reserved columns:

```sql
case when obvious_problem then 'medium' else 'ok' end
  as pg_diag_internal_severity,
case when obvious_problem then 'why this row requires review' end
  as pg_diag_internal_reason
```

The SQL executor removes `pg_diag_internal_*` columns from the public table,
sets item severity from the highest row, and creates `issues.summary` above the
table. Optional manifest text customizes that summary:

```yaml
evaluation:
  summary_title: Configuration requires review
  recommendation: Validate workload evidence before changing production settings.
```

Do not assign severity to contextual ratios or cumulative counters without a
defensible threshold, reset scope, and applicability contract. The instruction
must explain the trigger, false positives, evidence boundary, and safe next
step.

## Add A Sampler-Backed Chart

Sampler implementations are registered in the top-level `sampler_providers`
mapping in `metrics.yaml`; core never maps a provider or output id to
implementation code. A provider manifest declares its module, async function,
post-window grace timeout, opaque configuration, and output contracts. Put any
host command in an implementation-owned file under `scripts/` and reference it
from the output so the collected source remains visible in the report.

Provider example:

```yaml
sampler_providers:
  host_example:
    module: my_product.providers.host_example
    function: collect
    grace_timeout_ms: 1000
    config:
      source_script: samplers/host_example.sh
      output: host.example
    outputs:
      host.example:
        collection_scope: every_snapshot
        source_file: samplers/host_example.sh
        source_language: bash
```

The async function receives `SamplerProviderContext` and returns
`SamplerCollection` or an equivalent mapping. It may emit only declared output
ids. Each sample has `timestamp` and `rows`; each error names the affected output
in `sampler`. Use `ctx.required_outputs` to avoid unrequested work and
`ctx.host` for the same bounded local/SSH command contract.

Metric example:

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
        tags: [Disk, "I/O"]
        state: collapsed
```

Sampler-backed tables must reference an output declared with
`collection_scope: window_endpoints`; they must not add table collection work to
each chart iteration.

## Validation Checklist

Before committing a content change, check the following:

- New catalog files are listed in `queries.yaml`.
- Query IDs, script IDs, Python source IDs, metric IDs, and report item IDs are
  unique.
- PostgreSQL variants use correct `min_pg_version` and optional
  `max_pg_version` boundaries.
- Every referenced SQL, Bash, or Python source file exists.
- Every visible report item has a non-empty Markdown instruction file.
- Every report item has at least one allowed tag, and each section has three to
  five items expanded by default.
- Every SQL-backed chart query returns `snapshot_time`.
- Every metric `value_ref`, `key_ref`, `label_ref`, and `partition_by` entry has
  a matching semantic column or sampler field.
- Large cumulative views are pre-filtered in SQL before snapshot collection.
- `display.default_sort` uses the public result column name expected by the
  renderer.
- Every metric table column defines `pg_type`; integer counter Delta columns use
  an integral type such as `int8`, while rates use a decimal type such as
  `float8`.
- Local-only scripts and Python sources have reasonable timeouts and safe remote
  behavior.
- Reviewed changes to Python, shell, SQL, or YAML content are reflected in the
  vendor integrity baseline before running validation; Markdown changes do not
  require a baseline update.

Run:

```bash
pg-diag validate
pg-diag explain-plan --pg-version 180000 --run-mode snapshots --collection-mode local
```
