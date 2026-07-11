# pg_diag

`pg_diag` is a PostgreSQL diagnostic report utility for PostgreSQL 14-18.

Based on [pg_perfbench](https://github.com/TantorLabs/pg_perfbench).

It collects PostgreSQL catalog/statistics data, optional local host data, repeated
snapshots for rate/delta charts, and writes two outputs:

- `report.json` - machine-readable diagnostic artifact for other systems or renderers.
- `report.html` - browser report rendered from the JSON artifact.

The report layout, SQL queries, local scripts, trusted Python sources, and
metrics are declarative files under `content/`. The Python runtime loads this
content pack, validates it, selects SQL variants by PostgreSQL version, executes
sources, and renders the result.

## Documentation

- [Content pack overview](content/README.md) - bundled report structure, SQL
  catalogs, local scripts, trusted Python sources, metrics, collection modes,
  and validation.
- [Extending the report](content/EXTENDING.md) - examples for adding SQL table
  items, snapshot charts, top-N charts, delta tables, local Bash items, trusted
  Python items, and OS sampler charts.
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

## Runtime Requirements

Python runtime:

- Python 3.11 or newer.
- Python packages from `pyproject.toml`: `asyncpg` and `PyYAML`.

PostgreSQL target:

- PostgreSQL 14-18.
- A login role that can connect to the diagnosed database and read PostgreSQL
  catalog/statistics views. Granting `pg_monitor` or `pg_read_all_stats` is
  recommended for complete activity/statistics visibility.
- No extension is required for the core catalog, activity, locks, WAL,
  replication, storage, vacuum, index, and OS parts of the report.

Recommended users:

- For `remote-db-only` collection, run the CLI as any OS user that can start
  `pg-diag`. Only PostgreSQL connection privileges matter in this mode.
- For full `local` collection, run the CLI on the PostgreSQL host as an OS user
  that can read local PostgreSQL configuration files and `/proc` process data.
  In packaged Linux installs this is usually the `postgres` OS user, or a
  dedicated diagnostics service user granted read access to files such as
  `pg_hba.conf`.
- Avoid running as `root` by default. Use a least-privilege diagnostics user and
  grant narrow read access where possible. `pg_diag` only tries passwordless
  `sudo -n` for `lshw` hardware inventory if it is already available.
- If the OS user cannot read `pg_hba.conf`, the local security item
  `cluster_inventory.remote_superuser_access` will report an execution error,
  while the rest of the report continues.

Optional PostgreSQL extensions:

- `pg_stat_statements` enables SQL workload sections and SQL delta charts.
  It must be present in `shared_preload_libraries`, PostgreSQL must be
  restarted after that change, and `CREATE EXTENSION pg_stat_statements` must
  be run in the diagnosed database.
- `pg_wait_sampling` enables the optional historical wait sampling profile.
  Install the extension package and run `CREATE EXTENSION pg_wait_sampling` in
  the diagnosed database. Without it, `pg_diag` still reports wait data sampled
  from `pg_stat_activity` in snapshots mode.

Local collection mode OS requirements:

- Linux collector host with `/proc` mounted.
- POSIX shell plus common base tools: `cat`, `grep`, `awk`, `df`, `mount`,
  `uname`.
- `procps` tools: `ps` and `/sbin/sysctl`.
- `util-linux`: `lscpu` and `lsblk`.
- `iproute2`: `ip`.
- `lshw` for hardware inventory sections. Some `lshw` data requires root; if
  passwordless `sudo -n` is available, `pg_diag` uses it automatically.
- `sysstat` / `iostat` for local disk throughput, IOPS, utilization, and
  latency charts in snapshots mode.

Missing local tools do not stop the report. Affected OS items become empty,
skipped, unavailable, or add a diagnostic warning; PostgreSQL SQL collection
continues. In `remote-db-only` mode, local host scripts, local-only Python
sources, and local OS samplers are intentionally skipped.

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

The JSON plan separates user-visible `items` from internal `source_jobs` used
to collect snapshot metric inputs. Every source job executes exactly one query;
sources are not combined across report items.

Inspect a selected SQL query variant:

```bash
pg-diag run-query cluster.settings \
  --content content \
  --pg-version 180000
```

`run-query` is an inspection command: it selects the version-specific variant
and prints its metadata and SQL without connecting to PostgreSQL.

## Run A Single Snapshot

Remote DB-only mode collects PostgreSQL data and skips local host scripts and
local-only Python checks:

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

The collection window is bounded to keep `report.json`, self-contained HTML, and
browser memory usage predictable:

- `--duration-seconds`: 30 seconds to 86400 seconds (24 hours), default 30.
- `--interval-seconds`: 5 seconds to 600 seconds, default 15, and not greater
  than the duration.
- Scheduled snapshots: at most 300. Collection starts at offset zero, continues
  at each interval, and includes the exact window end when it is not already an
  interval boundary.

The scheduled count is `floor(duration / interval) + 1` for an exact boundary,
or `floor(duration / interval) + 2` when the final boundary must be added. For
example, a 24 hour report needs an interval of at least 289 seconds.

Point-in-time SQL, script, and Python items, including `PostgreSQL Settings`,
are collected exactly once before the repeated window starts. Each scheduled
point then executes only SQL sources for chart metrics. Start/end delta tables
use a separate `window_endpoints` source scope and execute exactly twice: once
before and once after the chart window. Endpoint source rows are used in memory
and are not added to the public snapshot array. In local mode, per-backend
`/proc` tables follow the same endpoint model: process counters are read at the
two window boundaries and converted to window-average rates.

Slow chart queries do not create a backlog: stale scheduled points are skipped
and recorded in report diagnostics. One-time collection and the final endpoint
queries can make total command runtime longer than `--duration-seconds`.

High-cardinality statement, table, index, and function metric sources keep an
SQL `ORDER BY ... LIMIT` on every endpoint/sample so a catalog with millions of
objects cannot fill collector memory. Adjacent bounded samples may legitimately
contain different keys. Deltas are calculated only for their intersection;
unmatched keys are counted in compact `interval_coverage` metadata and are not
treated as zero. Counter decreases or invalid values create a gap and warning.

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
- Cluster inventory, security, and configuration checks.
- Per-backend local process statistics calculated from two window endpoints in
  local snapshots mode.

Availability depends on PostgreSQL version, installed extensions, database
permissions, collection mode, and local host permissions.

Repeated table samples store their column schema once in `snapshot_schemas` and
keep only status, rows, and an optional failure reason in each snapshot point.
Raw snapshot points are not duplicated into the self-contained HTML after
derived metric items have been built. Reports use artifact schema version 3.
The renderer accepts that version only and requires the complete unified
content document and source provenance stored by the collector.

## Content Layout

```text
content/
  report.yaml          # report structure and item ordering
  queries.yaml         # query catalog index
  scripts.yaml         # local script catalog
  python.yaml          # trusted Python source catalog
  metrics.yaml         # chart/table metric definitions
  field_reference.yaml # inline help for declarative configuration fields
  catalog/             # query manifests and version ranges
  queries/             # SQL source files
  scripts/             # local shell source files
  python/              # trusted Python source files
```

`report.yaml` references items by `query`, `script`, `metric`, or `python`. SQL
result columns are read from actual cursor metadata; the report layout does not
hardcode table columns.

The loader assembles these YAML files into one effective content document with
canonical roots such as `sections/<section>/items/<item>`, `queries/<id>`,
`scripts/<id>`, `metrics/<id>`, and `python_sources/<id>`. The artifact stores
that document once together with source-file provenance. `Show meta` uses it for
the annotated `Raw` YAML view; `Total` remains the default resolved-metadata view.
All catalog paths and section/item defaults are explicit in `report.yaml`.
Missing configuration is a validation error; the loader and renderer do not
infer paths or adapt older content and artifact schemas.

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
- Every PostgreSQL connection requests `default_transaction_read_only=on` in
  the startup settings and verifies both the session default and current
  transaction before collection starts. SQL source transactions additionally
  use an explicit read-only transaction.
- pg_diag never resets PostgreSQL statistics counters. Counter discontinuities
  are only detected and reported; reset functions are never invoked.
- Unsupported PostgreSQL versions fail at runtime planning.
- JSON and HTML are written atomically per file with mode `0600`; their output
  paths must be different.
- Report JSON uses strict JSON values. Non-finite runtime/source numbers are
  normalized to `null`, and invalid external artifacts are rejected.
- `snapshot` and `snapshots` return a non-zero CLI status when the written
  report contains an item collection error. `runtime_policy.fail_fast: true`
  stops collection at the first item error and does not write a partial report.
- Local host data and local-only Python sources are skipped in
  `remote-db-only` mode.
- Blocking work requested by trusted Python sources runs in a killable child
  process, so a source timeout does not leave its filesystem or command probe
  running in the collector background.
- Generated reports are ignored by Git by default.
