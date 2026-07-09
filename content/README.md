# pg_diag Content Pack

This directory contains the bundled declarative content pack for `pg_diag`.

The content pack defines the report structure, PostgreSQL SQL sources, local
host script sources, trusted Python sources, snapshot metrics, and display
hints. The Python runtime loads these files, validates references, chooses
version-specific SQL variants, executes the selected sources, and renders a
JSON/HTML report.

## Files And Directories

- `report.yaml` - report metadata, runtime policy, sections, item ordering, and
  lightweight item references (`query`, `script`, `metric`, or `python`).
- `queries.yaml` - query catalog index, query defaults, SQL root, and the exact
  list of query catalog files to load.
- `catalog/` - grouped query manifest files referenced by `queries.yaml`.
- `metrics.yaml` - snapshot chart metrics, top-N metrics, table metrics, and
  metrics sourced from local samplers.
- `scripts.yaml` - local script declarations, script defaults, output types, and
  remote DB-only behavior.
- `python.yaml` - trusted Python source declarations, defaults, function names,
  timeouts, and local-only behavior.
- `instructions/` - Markdown instructions embedded into report items and shown
  through the `Show Instruction` button.
- `queries/` - SQL files referenced by query variants.
- `scripts/` - local shell scripts referenced by `scripts.yaml`.
- `python/` - trusted Python source files referenced by `python.yaml`.
- `EXTENDING.md` - examples for adding new report items.

`catalog/*.yaml` is not loaded by glob. A new catalog file must be listed in
`queries.yaml` under `query_catalog.files`; otherwise it is ignored.

## Report Layout

`report.yaml` is intentionally lightweight. A report item must reference exactly
one source:

```yaml
items:
  pg_settings:
    query: cluster.settings
  kernel_version:
    script: os.kernel_version
  database_transaction_rate:
    metric: database.transaction_rate
  remote_superuser_access:
    python: security.remote_superuser_access
```

The layout must not define SQL output columns. Table headers and PostgreSQL data
types are derived from actual cursor metadata of the selected SQL variant.

Useful item-level keys include:

- `state: expanded|collapsed|hidden`
- `tags`, validated against the built-in tag vocabulary and exposed to report
  filters
- `render.empty_message`, used by the HTML renderer for empty table, chart, or
  no-payload states
- `instruction` or `instructions` to override the default Markdown instruction
  path for the item
- source reference: `query`, `script`, `metric`, or `python`

## Item Instructions

Every visible report item has a Markdown instruction file. By default the
runtime maps item id `section.item` to:

```text
instructions/items/<section>/<item>.md
```

For example:

```text
sql_workload.top_sql_by_total_time
=> instructions/items/sql_workload/top_sql_by_total_time.md
```

The Markdown text is embedded in `source_metadata.instructions` in the JSON
artifact and rendered in the HTML report through `Show Instruction`. Keep these
files focused on DBA interpretation: what the item can reveal, what to watch,
common fault causes, and a short checklist.

If an item needs a non-standard path, set it in `report.yaml`:

```yaml
items:
  top_sql_by_total_time:
    query: statements.top_by_total_time
    instruction: items/sql_workload/top_sql_by_total_time.md
```

Instruction files are part of the content checksum. Validation fails when a
report item has no Markdown instruction file.

## Query Manifests

Query manifests live in files listed by `queries.yaml`.

Important keys:

- `title`
- `group`
- `main_view`
- `description`
- `cost`
- `optional`, when a query depends on an optional extension or relation and a
  missing relation should not make the whole item a collection error
- `display.default_sort.column`
- `display.default_sort.direction`
- `collection.default`
- `collection.supports`
- `requirements.unsupported_versions_reason`
- `variants`

Each variant must define:

- `id`
- `min_pg_version`
- optional `max_pg_version`
- `sql_file`
- optional `semantic_columns`

Example:

```yaml
queries:
  cluster.settings:
    title: PostgreSQL Settings
    main_view: pg_settings
    display:
      default_sort:
        column: setting_name
        direction: asc
    collection:
      default: once
      supports: [once, every_snapshot]
    variants:
      - id: cluster_settings_pg14_plus
        min_pg_version: 140000
        sql_file: cluster/settings.sql
        semantic_columns:
          dimensions:
            database: datname
          gauges:
            setting_value: setting_value
```

`semantic_columns` maps stable metric references to physical SQL result columns.
Metrics use these semantic references instead of hardcoding column names.

Collection scopes have distinct runtime meanings:

- `once` - ordinary report table/text item, executed once before the timed window;
- `every_snapshot` - chart source, executed at every scheduled point;
- `window_endpoints` - table delta/rate source, executed only at window start and end.

Only hidden metric sources may be promoted to the latter two scopes. A visible
query item is always planned as `once` in `snapshots` mode.

## Script Manifests

Local scripts are declared in `scripts.yaml`.

Important keys:

- `title`
- `description`
- `script_file`
- `output`
- `local_only`
- `timeout_ms`
- `remote_db_only_behavior`

Supported output modes are plain text and JSON-table output used by hardware or
host inventory scripts.

Local-only scripts are skipped in `remote-db-only` collection mode. The skip
reason comes from `remote_db_only_behavior` or the runtime policy in
`report.yaml`.

## Python Source Manifests

Trusted Python sources are declared in `python.yaml` and loaded from `python/`.
They are intended for checks that need runtime logic beyond a single SQL query
or shell script.

Important keys:

- `title`
- `description`
- `python_file`
- `function`
- `local_only`
- `timeout_ms`

The configured function receives a `PythonSourceContext` and must return a
`PythonSourceResult` or a compatible mapping. Python sources can return table,
plain text, or empty result payloads and can attach diagnostics and structured
issues.

SQL sources can likewise drive a structured summary above a table. Public
finding columns use `risk_level`/`risk_reason`; reserved
`pg_diag_internal_severity`/`pg_diag_internal_reason` columns evaluate an
ordinary table without exposing helper columns. Automatic severity is intended
only for obvious, explicitly documented conditions.

Local-only Python sources are skipped in `remote-db-only` collection mode. The
skip reason comes from the runtime policy in `report.yaml`.

`timeout_ms` bounds how long the collector waits for module loading and source
execution. Synchronous sources run in a daemon thread so they cannot block the
async collector; timed-out work is reported as an item error. CPython cannot
forcibly terminate a running thread, so trusted synchronous sources must avoid
unbounded work and external side effects. Async sources must remain cooperative
and yield to the event loop for cancellation.

## Metrics

`metrics.yaml` is used only in `snapshots` mode.

Metrics can produce:

- charts from repeated SQL samples;
- charts from local OS samplers;
- top-N charts;
- delta/rate tables from two in-memory window endpoints;
- per-backend local process tables from two window endpoints.

Important keys:

- `source_query` - use a dedicated SQL source for a chart or endpoint metric.
- `source_sampler` - use local sampler data.
- `requires_collection: every_snapshot`
- `requires_collection: window_endpoints`
- `partition_by`
- `series`
- `top_n`
- `result: table`
- `table`
- `chart`

For a SQL-backed chart, the referenced query must support `every_snapshot`. For
a start/end table metric, it must support `window_endpoints`. Ordinary report
queries always execute once at the beginning of `snapshots` mode, regardless of
whether their catalog also advertises support for repeated collection. Keep
metric source queries item-specific under the `metrics.*` namespace; this keeps
SQL editing isolated and avoids showing unrelated source columns in `Show SQL`
or `Show meta`.

For sampler-backed metrics, `source_sampler` identifies local sampler data such
as CPU, memory, disk, network, or backend process metrics. CPU, memory, disk,
and network samplers run through the chart window. `os.backend_proc` reads
process counters only at the two window endpoints and feeds table metrics with
window-average rates.

High-cardinality SQL metric sources must remain sorted and limited in SQL before
rows enter collector memory. Consequently, adjacent samples can contain
different table/index/statement/function keys. Only keys present in both
bounded samples produce a delta. `interval_coverage` records comparable,
unmatched, and invalid key intervals without duplicating unmatched rows in the
derived metric result.
Unmatched keys are normal for stacked-column Top-N charts; counter decreases,
invalid values, and invalid timestamps are omitted and reported as warnings.

## Collection Modes

`snapshot` mode collects one point-in-time report. Metric items are skipped
because they require repeated samples.

`snapshots` mode first collects ordinary report items once. During the timed
window it repeats only chart sources. Delta/rate tables use two endpoint samples
outside the public snapshot array. Local backend-process tables likewise use
two `/proc` endpoint reads and are not sampled at every chart point.

`remote-db-only` collection mode executes PostgreSQL SQL sources and non-local
Python sources, but skips local host scripts, local-only Python sources, and
local samplers.

`local` collection mode executes PostgreSQL SQL sources, local host scripts, and
Python sources on the collector machine.

## Validation

Run content validation after changing declarations or SQL files:

```bash
pg-diag validate --content content
```

The validator checks schema versions, duplicate YAML keys, report references,
SQL/script/Python source file existence, Python function declarations, version
ranges, collection support, display sort hint shape, semantic metric references,
shell fallback behavior, executable script files, positive timeouts, report
states/defaults, metric source exclusivity, and read-only SQL shape. Catalog and
source paths must be relative and remain inside their declared content
directories, including after symlink resolution.

Structural YAML mappings are checked during loading, before planning. The
runtime does not require a schema framework: contracts are enforced by the
loader, validator, execution-plan dataclasses, and strict artifact validator.

`runtime_policy.fail_fast` controls orchestration. When it is `false`, item
errors are preserved in the report and the CLI exits non-zero after writing the
artifact. When it is `true`, collection stops at the first item error and no
partial report is written.

For extension examples, see `EXTENDING.md`.
