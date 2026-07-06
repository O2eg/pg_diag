# pg_diag Content Pack

This directory contains the bundled declarative content pack for `pg_diag`.

The content pack defines the report structure, PostgreSQL SQL sources, local
host script sources, snapshot metrics, and display hints. The Python runtime
loads these files, validates references, chooses version-specific SQL variants,
executes the selected sources, and renders a JSON/HTML report.

## Files And Directories

- `report.yaml` - report metadata, runtime policy, sections, item ordering, and
  lightweight item references (`query`, `script`, or `metric`).
- `queries.yaml` - query catalog index, query defaults, SQL root, and the exact
  list of query catalog files to load.
- `catalog/` - grouped query manifest files referenced by `queries.yaml`.
- `metrics.yaml` - snapshot chart metrics, top-N metrics, table metrics, and
  metrics sourced from local samplers.
- `scripts.yaml` - local script declarations, script defaults, output types, and
  remote DB-only behavior.
- `instructions/` - Markdown instructions embedded into report items and shown
  through the `Show Instruction` button.
- `queries/` - SQL files referenced by query variants.
- `scripts/` - local shell scripts referenced by `scripts.yaml`.
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
```

The layout must not define SQL output columns. Table headers and PostgreSQL data
types are derived from actual cursor metadata of the selected SQL variant.

Useful item-level keys include:

- `state: expanded|collapsed|hidden`
- `empty_message`
- `instruction` or `instructions` to override the default Markdown instruction
  path for the item
- source reference: `query`, `script`, or `metric`

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

## Metrics

`metrics.yaml` is used only in `snapshots` mode.

Metrics can produce:

- charts from repeated SQL samples;
- charts from local OS samplers;
- top-N charts;
- delta/rate tables from start/end or adjacent snapshots;
- per-backend local process tables.

Important keys:

- `source_query` - use repeated SQL samples from a dedicated metric query.
- `source_sampler` - use local threaded sampler data.
- `requires_collection: every_snapshot`
- `partition_by`
- `series`
- `top_n`
- `result: table`
- `table`
- `chart`

For SQL-backed metrics, the referenced query must support `every_snapshot` when
the metric requires repeated collection. Keep metric source queries item-specific
under the `metrics.*` namespace; this keeps SQL editing isolated and avoids
showing unrelated source columns in `Show SQL` or `Show meta`.

For sampler-backed metrics, `source_sampler` identifies local sampler data such
as CPU, memory, disk, network, or backend process metrics.

## Collection Modes

`snapshot` mode collects one point-in-time report. Metric items are skipped
because they require repeated samples.

`snapshots` mode collects repeated samples and builds rates, deltas, top-N
series, and chart/table metrics.

`remote-db-only` collection mode executes PostgreSQL SQL sources but skips local
host scripts and local samplers.

`local` collection mode executes PostgreSQL SQL sources and local host sources on
the collector machine.

## Validation

Run content validation after changing declarations or SQL files:

```bash
pg-diag validate --content content
```

The validator checks schema versions, duplicate YAML keys, report references,
SQL/script file existence, version ranges, collection support, display sort
hints, semantic metric references, shell fallback behavior, and read-only SQL
shape.

For extension examples, see `EXTENDING.md`.
