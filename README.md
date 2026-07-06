# pg_diag

`pg_diag` is a PostgreSQL diagnostic report utility for PostgreSQL 14-18.

Based on [pg_perfbench](https://github.com/TantorLabs/pg_perfbench).

It collects PostgreSQL catalog/statistics data, optional local host data, repeated
snapshots for rate/delta charts, and writes two outputs:

- `report.json` - machine-readable diagnostic artifact for other systems or renderers.
- `report.html` - browser report rendered from the JSON artifact.

The report layout, SQL queries, local scripts, and metrics are declarative files
under `content/`. The Python runtime loads this content pack, validates it,
selects SQL variants by PostgreSQL version, executes sources, and renders the
result.

## Documentation

- [Content pack overview](content/README.md) - bundled report structure, SQL
  catalogs, local scripts, metrics, collection modes, and validation.
- [Extending the report](content/EXTENDING.md) - examples for adding SQL table
  items, snapshot charts, top-N charts, delta tables, local Bash items, and OS
  sampler charts.
- [Tests](tests/README.md) - test layout, unit and integration test commands,
  and guidance for adding or correcting tests.

## Features

- PostgreSQL version-aware SQL variants for PostgreSQL 14-18.
- Single snapshot and repeated snapshots modes.
- Local and remote DB-only collection modes.
- Read-only SQL execution.
- Local OS sections and OS charts in local mode.
- Table, plain text, and chart report items.
- Table filtering, sorting, pagination, and compact value formatting.
- Chart zoom, pan, reset, export menu, and fixed color palettes.
- Source and metadata dialogs for report items.
- Error diagnostics embedded directly into failed report items.
- JSON artifact separated from HTML rendering.

## Installation

Install from the project directory:

```bash
cd pg_diag

python3 -m venv .venv
. .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -e .
```

For development and tests:

```bash
cd pg_diag
. .venv/bin/activate

python -m pip install -e ".[dev]"
```

Optional test extras are split out:

```bash
python -m pip install -e ".[docker]"
python -m pip install -e ".[browser]"
```

Check the installed command:

```bash
pg-diag --version
pg-diag --help
```

You can also run the CLI without installing the console script:

```bash
python -m pg_diag.cli --help
```

## Validate Content

Validate the bundled content pack:

```bash
pg-diag validate --content content
```

List available report items:

```bash
pg-diag list-items --content content
```

List query catalog entries and selected SQL files:

```bash
pg-diag list-queries --content content
```

Preview the execution plan for PostgreSQL 18 in local snapshots mode:

```bash
pg-diag explain-plan \
  --content content \
  --pg-version 180000 \
  --run-mode snapshots \
  --collection-mode local
```

Print the same plan as JSON:

```bash
pg-diag explain-plan \
  --content content \
  --pg-version 180000 \
  --run-mode snapshots \
  --collection-mode local \
  --json
```

Inspect a selected SQL query variant:

```bash
pg-diag run-query cluster.settings \
  --content content \
  --pg-version 180000 \
  --dry-run
```

## Run A Single Snapshot

Remote DB-only mode collects PostgreSQL data and skips local host scripts:

```bash
export PGDIAG_PASSWORD='change-me'

pg-diag snapshot \
  --content content \
  --host 127.0.0.1 \
  --port 5432 \
  --database appdb \
  --user app \
  --password "$PGDIAG_PASSWORD" \
  --collection-mode remote-db-only \
  --out reports/appdb_snapshot
```

The output directory will contain:

```text
reports/appdb_snapshot/report.json
reports/appdb_snapshot/report.html
```

To write outputs to fixed file names instead of the default files inside
`--out`, pass exact output paths:

```bash
pg-diag snapshot \
  --content content \
  --dsn "postgresql://app:${PGDIAG_PASSWORD}@127.0.0.1:5432/appdb" \
  --collection-mode remote-db-only \
  --json-out reports/appdb_snapshot_20260706.json \
  --html-out reports/appdb_snapshot_20260706.html
```

If only one fixed output path is supplied, the other file still uses the
default path under `--out`.

The same command can use a DSN:

```bash
pg-diag snapshot \
  --content content \
  --dsn "postgresql://app:${PGDIAG_PASSWORD}@127.0.0.1:5432/appdb" \
  --collection-mode remote-db-only \
  --out reports/appdb_snapshot
```

## Run Local Collection

Local mode collects PostgreSQL data and local host data from the machine where
`pg_diag` is running:

```bash
pg-diag snapshot \
  --content content \
  --host 127.0.0.1 \
  --port 5432 \
  --database appdb \
  --user app \
  --password "$PGDIAG_PASSWORD" \
  --collection-mode local \
  --out reports/appdb_local_snapshot
```

Use local mode only when the collector runs on the PostgreSQL host or when local
OS data from the collector host is intentionally required.

## Run Repeated Snapshots

Repeated snapshots mode collects samples over time and computes rates, deltas,
top-N charts, and workload summaries from adjacent snapshots.

Example: collect for 60 seconds with a 5 second interval:

```bash
pg-diag snapshots \
  --content content \
  --host 127.0.0.1 \
  --port 5432 \
  --database appdb \
  --user app \
  --password "$PGDIAG_PASSWORD" \
  --collection-mode local \
  --duration-seconds 60 \
  --interval-seconds 5 \
  --out reports/appdb_60s
```

For a remote DB-only repeated report:

```bash
pg-diag snapshots \
  --content content \
  --dsn "postgresql://app:${PGDIAG_PASSWORD}@127.0.0.1:5432/appdb" \
  --collection-mode remote-db-only \
  --duration-seconds 60 \
  --interval-seconds 5 \
  --out reports/appdb_60s_remote
```

Repeated snapshot reports also support fixed output file names:

```bash
pg-diag snapshots \
  --content content \
  --dsn "postgresql://app:${PGDIAG_PASSWORD}@127.0.0.1:5432/appdb" \
  --collection-mode remote-db-only \
  --duration-seconds 60 \
  --interval-seconds 5 \
  --json-out reports/appdb_60s.json \
  --html-out reports/appdb_60s.html
```

## Render Existing JSON

`report.json` is the durable artifact. HTML can be rebuilt later without
reconnecting to PostgreSQL:

```bash
pg-diag render \
  --from-json reports/appdb_60s/report.json \
  --out reports/appdb_60s/report.html
```

## Report Contents

The bundled content pack includes sections for:

- PostgreSQL version and settings.
- Local operating system inventory and charts.
- Session activity, connection pressure, locks, and waits.
- Statement workload capability checks and top SQL reports.
- Snapshot delta/rate workload summaries.
- Table, index, and function workload counters.
- Optional wait sampling data when available.
- Replication, WAL, checkpoints, and I/O views.
- Storage, vacuum, wraparound, sequence, and XID horizon diagnostics.
- Index health checks.
- Cluster inventory and configuration checks.
- Per-backend local process statistics in local snapshots mode.

Availability depends on PostgreSQL version, installed extensions, database
permissions, collection mode, and local host permissions.

## Content Layout

```text
content/
  report.yaml          # report structure and item ordering
  queries.yaml         # query catalog index
  scripts.yaml         # local script catalog
  metrics.yaml         # chart/table metric definitions
  catalog/             # query manifests and version ranges
  queries/             # SQL source files
  scripts/             # local shell source files
```

`report.yaml` references items by `query`, `script`, or `metric`. SQL result
columns are read from actual cursor metadata; the report layout does not hardcode
table columns.

## Development

Run unit tests:

```bash
cd pg_diag
. .venv/bin/activate

PYTHONDONTWRITEBYTECODE=1 python -m pytest -q
```

Validate content before committing content changes:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pg_diag.cli validate --content content
```

Compile Python files:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m py_compile \
  pg_diag/*.py \
  pg_diag/executors/*.py \
  pg_diag/render/*.py
```

## Notes

- Runtime dependencies are intentionally small: YAML parsing and PostgreSQL
  access.
- SQL sources are executed in read-only transactions.
- Unsupported PostgreSQL versions fail at runtime planning.
- Local host data is skipped in `remote-db-only` mode.
- Generated reports are ignored by Git by default.
