# pg_diag

`pg_diag` is a PostgreSQL diagnostic report utility for PostgreSQL 14-18.

Based on [pg_perfbench](https://github.com/TantorLabs/pg_perfbench).

It collects PostgreSQL catalog/statistics data, optional host data locally or over
SSH, repeated snapshots for rate/delta charts, and by default writes three outputs:

- `report.json` - machine-readable diagnostic artifact for other systems or renderers.
- `report.html` - browser report rendered from the JSON artifact.
- `report.log` - timestamped collection progress, item outcomes, and skip reasons.

The report layout, taxonomy, presentation rules, SQL queries, host scripts,
trusted Python sources, metrics, and sampler-provider registrations are
declarative files under `pg_diag/content/`. The installed command uses this bundled
content pack by default. The engine validates and executes only its
generic contracts; bundled item and host-probe implementations are not embedded
in core dispatch, validation, or metric rendering.

## Documentation

- [Content pack overview](https://github.com/O2eg/pg_diag/blob/main/pg_diag/content/README.md) - bundled report structure, SQL
  catalogs, host scripts, trusted Python sources, metrics, collection modes,
  and validation.
- [Extending the report](https://github.com/O2eg/pg_diag/blob/main/pg_diag/content/EXTENDING.md) - examples for adding SQL table
  items, snapshot charts, top-N charts, delta tables, host shell items, trusted
  Python items, and OS sampler charts.
- [Item development specification](https://github.com/O2eg/pg_diag/blob/main/pg_diag/content/ITEM_DEVELOPMENT_SPEC.md) - normative
  contracts for values, units, timestamps, tables, charts, and diagnostics.
- [Tests](https://github.com/O2eg/pg_diag/blob/main/tests/README.md) - test layout, unit and integration test commands,
  and guidance for adding or correcting tests.

## Quick Navigation

- [Quick start](#quick-start)
- [Credentials and security](#credentials-and-security)
- [Inspect and validate content](#inspect-and-validate-content)
- [Report and collection modes](#report-and-collection-modes)
- [Run one-shot reports](#run-one-shot-reports)
- [Run repeated snapshots](#run-repeated-snapshots)
- [Select report items](#select-report-items)
- [Collection timing and metric evaluation](#collection-timing-and-metric-evaluation)
- [Output files and exit status](#output-files-and-exit-status)

## Features

- PostgreSQL version-aware SQL variants for PostgreSQL 14-18.
- One-shot and repeated snapshots report modes.
- Local, SSH remote, and remote DB-only collection modes.
- Read-only SQL execution.
- OS sections and OS charts from the collector host or an SSH target.
- Table, plain text, and chart report items.
- Table filtering, sorting, pagination, and compact value formatting.
- Chart zoom, drag-pan, reset, legends with vertical scrolling after six rows,
  consistent axis/tooltip unit scaling, SVG/PNG/CSV export, and fixed color
  palettes.
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

- Python 3.10 or newer.
- Python packages from `pyproject.toml`: `asyncpg`, `AsyncSSH`, and `PyYAML`.

Compatibility matrix:

| Collector Python | PostgreSQL 14 | PostgreSQL 15 | PostgreSQL 16 | PostgreSQL 17 | PostgreSQL 18 | Status |
|---|---:|---:|---:|---:|---:|---|
| 3.10 | Yes | Yes | Yes | Yes | Yes | Minimum supported Python; full unit and Docker integration matrix |
| 3.11 | Yes | Yes | Yes | Yes | Yes | Supported |
| 3.12 | Yes | Yes | Yes | Yes | Yes | Supported; primary development runtime |

Python 3.9 and older are outside the compatibility contract. The PostgreSQL
version is detected from the server, independently of the collector's Python
minor version.

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
- For full `remote` collection, use a dedicated SSH account with public-key
  authentication and the same narrow host read permissions described for local
  collection. The private key and PostgreSQL credentials remain on the
  collector; they are not copied to the target host. The SSH service must allow
  command execution, the SFTP subsystem, and local TCP forwarding to the
  PostgreSQL endpoint.
- For full `local` collection, run the CLI on the PostgreSQL host as an OS user
  that can read local PostgreSQL configuration files and `/proc` process data.
  In packaged Linux installs this is usually the `postgres` OS user, or a
  dedicated diagnostics service user granted read access to files such as
  `pg_hba.conf`.
- Avoid running as `root` by default. Use a least-privilege diagnostics user and
  grant narrow read access where possible. `pg_diag` only tries passwordless
  `sudo -n` for `lshw` hardware inventory if it is already available.
- If the OS user cannot read `pg_hba.conf`, the local security item
  `cluster_inventory.remote_superuser_access` will report unsupported evidence,
  while the rest of the report continues.

Optional PostgreSQL extensions:

- `pg_stat_statements` enables SQL workload sections and SQL delta charts.
  It must be present in `shared_preload_libraries`, PostgreSQL must be
  restarted after that change, and `CREATE EXTENSION pg_stat_statements` must
  be run in the diagnosed database.
- `pg_wait_sampling` enables the optional historical wait sampling profile.
  Install the extension package, add `pg_wait_sampling` to
  `shared_preload_libraries`, restart PostgreSQL, and run
  `CREATE EXTENSION pg_wait_sampling` in the diagnosed database. When both
  extensions are enabled, place `pg_stat_statements` before `pg_wait_sampling`
  in `shared_preload_libraries`. Without it, `pg_diag` still reports wait data
  sampled from `pg_stat_activity` in snapshots mode.

Full host collection requirements (`local` collector or `remote` SSH target):

- Linux host with `/proc` mounted.
- POSIX shell plus common Linux base tools: `cat`, `grep`, `head` (including
  `-z`), `find`, `getent`, `getconf`, `sed`, `tr`, `awk`, `df`, `mount`, and
  `uname`.
- `procps` tools: `ps` and `sysctl`.
- `util-linux`: `lscpu` and `lsblk`.
- `iproute2`: `ip`.
- `lshw` for hardware inventory sections. Some `lshw` data requires root; if
  passwordless `sudo -n` is available, `pg_diag` uses it automatically.
- `sysstat` / `iostat` for disk throughput, IOPS, utilization, and
  latency charts in snapshots mode.

Missing host tools do not stop the report. Affected OS items become empty,
unsupported, unavailable, or add a diagnostic warning; PostgreSQL SQL
collection continues. In `remote-db-only` mode, host scripts, local-only
Python sources, and host sampler providers are not executed or included in the
final report; their item IDs and skip reasons are recorded in `report.log` and
stdout.

## Credentials and Security

### Content Trust Boundary

A content pack is executable input, not passive configuration. SQL files are
executed in verified read-only PostgreSQL transactions, but declared shell
sources run as operating-system commands and trusted Python sources are loaded
as Python code. In `remote` mode, shell sources are sent to and executed on the
SSH target with the configured SSH account's privileges.

Use `--content` only with a content pack you trust and have reviewed. Content
validation verifies schema and cross-reference contracts; it is not a sandbox
or a malicious-code scanner. Run the collector and its SSH account with the
least privileges needed for diagnostics.

Before any content YAML is parsed, pg_diag verifies the bundled baseline for
all Python, shell, SQL, and YAML files under the selected `--content` directory.
Markdown documentation and item instructions are not part of this executable-content
integrity baseline. A modified, added, or removed protected file stops the command
before report collection starts. The failure does not print expected or
calculated hashes; restore pg_diag and its content directory from a trusted
distribution instead of accepting an unknown check set.

### PostgreSQL Credentials

Avoid putting passwords in `--password` or directly in a DSN because command
arguments can be visible to other processes and command tracing. For short
interactive runs, let asyncpg read the standard environment variable and omit
`--password`:

```bash
export PGPASSWORD='change-me'
```

For automation, prefer a PostgreSQL passfile with mode `0600`:

```text
db.example.com:5432:appdb:app:change-me
```

```bash
chmod 600 ~/.pgpass

pg-diag one-shot \
  --host db.example.com \
  --port 5432 \
  --database appdb \
  --user app \
  --passfile ~/.pgpass \
  --collection-mode remote-db-only \
  --out reports/appdb_one_shot
```

In `remote` mode, passfile entries are matched against the original PostgreSQL
host and port as seen from the SSH target, before asyncpg connects through the
local tunnel. `PGPASSFILE` and the default `~/.pgpass` are also supported.

### Report Handling

Reports can contain query text, object names, configuration, filesystem paths,
host inventory, and diagnostic evidence. Built-in redaction removes recognized
credential fields and obvious secrets, but it cannot guarantee that arbitrary
application data or custom source output is non-sensitive. JSON and HTML files
are created with mode `0600`; preserve restrictive permissions when copying or
publishing them.

## Quick Start

After installation, validate the bundled content and build a database-only
point-in-time report:

```bash
cd pg_diag
. .venv/bin/activate

export PGPASSWORD='change-me'

pg-diag validate

pg-diag one-shot \
  --host 127.0.0.1 \
  --port 5432 \
  --database appdb \
  --user app \
  --collection-mode remote-db-only \
  --out reports/appdb_one_shot
```

Successful collection writes:

```text
reports/appdb_one_shot/report.json
reports/appdb_one_shot/report.html
reports/appdb_one_shot/report.log
```

Open the HTML locally in a browser. Keep the JSON artifact: it can be validated
or rendered again without reconnecting to PostgreSQL.

## Inspect and Validate Content

The bundled content pack is installed inside the `pg_diag` Python package and is
used by default from any working directory. Use `--content /path/to/content`
only to select an explicit alternative pack; pg_diag does not implicitly load a
same-named directory from the current working directory.

Validate the bundled content pack:

```bash
pg-diag validate
```

List available report items:

```bash
pg-diag list-items
```

List query catalog entries and selected SQL files:

```bash
pg-diag list-queries
```

Preview the execution plan for PostgreSQL 18 in local snapshots mode:

```bash
pg-diag explain-plan \
  --pg-version 180000 \
  --run-mode snapshots \
  --collection-mode local
```

Print the same plan as JSON:

```bash
pg-diag explain-plan \
  --pg-version 180000 \
  --run-mode snapshots \
  --collection-mode local \
  --json
```

The JSON plan separates user-visible `items` from internal `source_jobs` used
to collect snapshot metric inputs. Every source job executes exactly one query;
sources are not combined across report items.

`--run-mode` accepts `one-shot` for a point-in-time report and `snapshots` for
an interval report.

Inspect a selected SQL query variant:

```bash
pg-diag run-query cluster.settings \
  --pg-version 180000
```

`run-query` is an inspection command: it selects the version-specific variant
and prints its metadata and SQL without connecting to PostgreSQL.

## Report and Collection Modes

The report command, collection mode, and collection timing are separate
dimensions. After command-line and content validation, a collection run creates
`report.log`; every successfully completed collection also writes the report
representations selected by `--output-format` (both JSON and self-contained HTML
by default).

### Report Commands

| Command | Default collection mode | Purpose | Timing behavior | Artifact result |
| --- | --- | --- | --- | --- |
| `one-shot` | `remote-db-only` | Point-in-time diagnostic report | Executes applicable `query`, `script`, and `python` items with `once`; does not execute or include `metric` items because no interval data exists | `runtime.mode` is `one-shot`; the public `snapshots` array is empty |
| `snapshots` | `local` | Interval diagnostic report | Executes visible once-items, collects required repeated/end-point sources, then evaluates derived metrics | `runtime.mode` is `snapshots`; when the selected plan requires repeated SQL sampling, the artifact contains samples plus derived rates, deltas, tables, and charts |

### Collection Modes

| Collection mode | PostgreSQL access | Host evidence | Availability behavior |
| --- | --- | --- | --- |
| `remote-db-only` | Direct asyncpg connection from the collector | Not collected | Host `script`, host-dependent `python`, and host-backed `metric` items are omitted from the final report without executing their sources; DB-only sources remain available |
| `local` | Direct asyncpg connection from the collector | Read from the collector machine | Use when the collector is the PostgreSQL host or when collector-host evidence is intentionally required |
| `remote` | Asyncpg connection through an AsyncSSH local port forward | Read from the SSH target over the same authenticated connection | `script` sources execute on the SSH target; trusted `python` evaluates locally using SSH-backed file and process evidence |

### Combined Report Matrix

| Report command | Collection mode | Item types and scopes | Result |
| --- | --- | --- | --- |
| `one-shot` | `remote-db-only` | `query` and DB-only `python` run with `once`; `script`, host-dependent `python`, and all `metric` items are omitted without execution | One point-in-time PostgreSQL report without host evidence |
| `one-shot` | `local` | `query`, `script`, and `python` run with `once`; all `metric` items are omitted without execution | Point-in-time PostgreSQL report plus collector-host evidence |
| `one-shot` | `remote` | `query` runs with `once`; `script` runs on the SSH target; `python` evaluates locally with SSH-host evidence; all `metric` items are omitted without execution | Point-in-time PostgreSQL and SSH-target report through one SSH connection |
| `snapshots` | `remote-db-only` | Report `query` and DB-only `python` run with `once`; SQL metric source jobs run with `every_snapshot` or `window_endpoints`; DB-backed `metric` items are calculated; host sources and metrics are omitted without execution | PostgreSQL rates, deltas, tables, and charts without host metrics |
| `snapshots` | `local` | Report `query`, `script`, and `python` run with `once`; SQL and local sampler jobs run with `every_snapshot` or `window_endpoints`; DB- and host-backed `metric` items are calculated | PostgreSQL and collector-host rates, deltas, tables, charts, and backend `/proc` endpoints |
| `snapshots` | `remote` | Report `query` runs with `once`; `script` runs on the SSH target; `python` evaluates locally with SSH-host evidence; SQL and SSH-host sampler jobs run with `every_snapshot` or `window_endpoints`; DB- and host-backed `metric` items are calculated | PostgreSQL and SSH-target rates, deltas, tables, charts, and backend `/proc` endpoints |

`snapshots --duration-seconds 30 --interval-seconds 5` schedules seven sample
points at 0, 5, 10, 15, 20, 25, and 30 seconds. One-time items and final
endpoint processing can make total wall-clock time longer than 30 seconds.

## Run One-Shot Reports

`one-shot` defaults to `remote-db-only`. Specify the collection mode explicitly
in automation so the source of any host evidence is unambiguous.

### Remote DB-Only

Remote DB-only mode collects PostgreSQL data and skips host scripts and
host-dependent Python checks:

```bash
pg-diag one-shot \
  --host 127.0.0.1 \
  --port 5432 \
  --database appdb \
  --user app \
  --collection-mode remote-db-only \
  --out reports/appdb_one_shot
```

The output directory will contain:

```text
reports/appdb_one_shot/report.json
reports/appdb_one_shot/report.html
```

To write outputs to fixed file names instead of the default files inside
`--out`, pass exact output paths:

```bash
pg-diag one-shot \
  --dsn "postgresql://app@127.0.0.1:5432/appdb" \
  --collection-mode remote-db-only \
  --json-out reports/appdb_one_shot_20260706.json \
  --html-out reports/appdb_one_shot_20260706.html
```

With the default `--output-format=[html,json]`, if only one fixed output path is
supplied, the other file still uses the default path under `--out`. To create
only one report representation, select it explicitly:

```bash
# HTML only; report.json is not created
pg-diag one-shot \
  --dsn "postgresql://app@127.0.0.1:5432/appdb" \
  --output-format=html \
  --html-out reports/appdb_one_shot.html

# JSON only; HTML is not rendered
pg-diag one-shot \
  --dsn "postgresql://app@127.0.0.1:5432/appdb" \
  --output-format=json \
  --json-out reports/appdb_one_shot.json
```

The same command can use a DSN:

```bash
pg-diag one-shot \
  --dsn "postgresql://app@127.0.0.1:5432/appdb" \
  --collection-mode remote-db-only \
  --out reports/appdb_one_shot
```

### Local

Local mode collects PostgreSQL data and local host data from the machine where
`pg_diag` is running:

```bash
pg-diag one-shot \
  --host 127.0.0.1 \
  --port 5432 \
  --database appdb \
  --user app \
  --collection-mode local \
  --out reports/appdb_local_one_shot
```

Use local mode only when the collector runs on the PostgreSQL host or when local
OS data from the collector host is intentionally required.

### Remote over SSH

Remote mode opens one authenticated SSH connection, forwards a dynamically
allocated loopback port to PostgreSQL, and collects SQL and host data from the
same target. `--host` and `--port` identify PostgreSQL as seen from the SSH host,
not from the collector:

```bash
pg-diag one-shot \
  --collection-mode remote \
  --ssh-host db.example.com \
  --ssh-port 22 \
  --ssh-user pgdiag \
  --ssh-key ~/.ssh/id_ed25519 \
  --ssh-known-hosts ~/.ssh/pg_diag_known_hosts \
  --host 127.0.0.1 \
  --port 5432 \
  --database appdb \
  --user app \
  --out reports/appdb_remote_one_shot
```

#### Prepare `--ssh-known-hosts`

`--ssh-known-hosts` points to an OpenSSH-format `known_hosts` file on the
collector host. It is used for strict SSH server identity verification. When
the option is omitted, pg_diag uses `~/.ssh/known_hosts`. A separate file is
convenient for service accounts, containers, and automated report jobs.

Create a dedicated file and obtain the target host key:

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
ssh-keyscan -p 22 -t ed25519 db.example.com > ~/.ssh/pg_diag_known_hosts
chmod 600 ~/.ssh/pg_diag_known_hosts
ssh-keygen -lf ~/.ssh/pg_diag_known_hosts
```

`ssh-keyscan` only retrieves a candidate key; it does not prove that the key
belongs to the intended server. Before using the file, compare the displayed
fingerprint with a value obtained through a trusted channel, such as the server
console, configuration management inventory, or the system administrator. For
an Ed25519 host key, the fingerprint can be checked on the server console with:

```bash
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

The entry must match the value passed to `--ssh-host`. For a non-default SSH
port, `known_hosts` uses the bracketed form `[host]:port`; `ssh-keyscan -p`
creates this form automatically:

```bash
ssh-keyscan -p 2222 -t ed25519 db.example.com > ~/.ssh/pg_diag_known_hosts

pg-diag one-shot \
  --collection-mode remote \
  --ssh-host db.example.com \
  --ssh-port 2222 \
  --ssh-user pgdiag \
  --ssh-key ~/.ssh/id_ed25519 \
  --ssh-known-hosts ~/.ssh/pg_diag_known_hosts \
  --host 127.0.0.1 \
  --port 5432 \
  --database appdb \
  --user app \
  --out reports/appdb_remote_one_shot
```

If the file is missing, it has no entry for the requested host and port, or
the server key differs from the trusted key, pg_diag terminates the SSH
connection before collecting data. After a legitimate host-key rotation,
replace the entry only after verifying the new fingerprint through a trusted
channel.

For an encrypted SSH key, put its passphrase in an environment variable and
name that variable with `--ssh-key-passphrase-env`; do not place the passphrase
on the command line:

```bash
export PGDIAG_SSH_KEY_PASSPHRASE='change-me'

pg-diag one-shot \
  --dsn "postgresql://app@127.0.0.1:5432/appdb" \
  --collection-mode remote \
  --ssh-host db.example.com \
  --ssh-user pgdiag \
  --ssh-key ~/.ssh/id_ed25519 \
  --ssh-key-passphrase-env PGDIAG_SSH_KEY_PASSPHRASE \
  --out reports/appdb_remote_one_shot
```

Remote mode requires explicit key authentication and strict `known_hosts`
verification. It does not fall back to password authentication, ssh-agent, or
the user's OpenSSH configuration. It does not upload an agent, create a remote
working directory, or require Python on the SSH target. Shell source text is
sent to `/bin/sh` through SSH stdin, file metadata/content is read over the
same SSH connection, and evaluation stays in the collector process. The
private key and any PostgreSQL passfile used by the collector must not grant
group or other access. Password lookup honors `--passfile`, a URI `passfile`,
`PGPASSFILE`, and the default `~/.pgpass`, and matches entries against the
original remote database host and port before `asyncpg` connects through the
dynamic local tunnel. A URI DSN can provide the remote endpoint; a keyword-style
DSN must be accompanied by `--host` and optionally `--port`.

Remote mode rejects `sslmode=verify-full` and an `SSLContext` with hostname
verification enabled. The dynamic forward changes the endpoint seen by
`asyncpg` to `127.0.0.1`, so preserving the original PostgreSQL TLS hostname is
not possible with this transport. Use direct database connectivity when
hostname verification is required.

## Run Repeated Snapshots

Repeated snapshots mode collects samples over time and computes rates, deltas,
top-N charts, and workload summaries. It defaults to `local`; choose
`remote-db-only` explicitly when the collector does not run on the PostgreSQL
host and no SSH host evidence is required.

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
are collected exactly once before the repeated window starts. At scheduled
points, the collector executes the SQL sources required by chart metrics. In
`local` and `remote` modes, required host sampler providers run concurrently on
the collector or SSH target. Start/end delta tables use a separate
`window_endpoints` source scope and execute exactly twice: once before and once
after the chart window. Endpoint source rows are used in memory and are not
added to the public snapshot array. Per-backend `/proc` tables use the same
endpoint model: process counters are read at the two window boundaries and
converted to window-average rates.

Slow chart queries do not create a backlog: stale scheduled points are skipped
and recorded in report diagnostics. One-time collection and the final endpoint
queries can make total command runtime longer than `--duration-seconds`.

High-cardinality statement, table, index, and function metric sources keep an
SQL `ORDER BY ... LIMIT` on every endpoint/sample so a catalog with millions of
objects cannot fill collector memory. Adjacent bounded samples may legitimately
contain different keys. Deltas are calculated only for their intersection;
unmatched keys are counted in compact `interval_coverage` metadata and are not
treated as zero. Counter decreases or invalid values create a gap and warning.

The examples below collect for 60 seconds with a 5 second interval.

### Local

```bash
pg-diag snapshots \
  --host 127.0.0.1 \
  --port 5432 \
  --database appdb \
  --user app \
  --collection-mode local \
  --duration-seconds 60 \
  --interval-seconds 5 \
  --out reports/appdb_60s
```

### Remote DB-Only

```bash
pg-diag snapshots \
  --dsn "postgresql://app@127.0.0.1:5432/appdb" \
  --collection-mode remote-db-only \
  --duration-seconds 60 \
  --interval-seconds 5 \
  --out reports/appdb_60s_remote
```

### Remote over SSH

Use the same SSH and database arguments as the one-shot remote example:

```bash
pg-diag snapshots \
  --collection-mode remote \
  --ssh-host db.example.com \
  --ssh-user pgdiag \
  --ssh-key ~/.ssh/id_ed25519 \
  --ssh-known-hosts ~/.ssh/known_hosts \
  --host 127.0.0.1 \
  --port 5432 \
  --database appdb \
  --user app \
  --duration-seconds 60 \
  --interval-seconds 5 \
  --out reports/appdb_60s_ssh
```

### Fixed Output Paths

Repeated snapshot reports also support fixed output file names:

```bash
pg-diag snapshots \
  --dsn "postgresql://app@127.0.0.1:5432/appdb" \
  --collection-mode remote-db-only \
  --duration-seconds 60 \
  --interval-seconds 5 \
  --json-out reports/appdb_60s.json \
  --html-out reports/appdb_60s.html
```

## Select Report Items

Both report commands support mutually exclusive exact-ID and tag filters. The
informational list options validate content and exit without requiring database
or SSH arguments.

List item IDs together with their tags and source-metadata descriptions:

```bash
pg-diag one-shot --item-id-list
```

The existing catalog-oriented command remains available:

```bash
pg-diag list-items
```

`--item-id` accepts either one ID or a comma-separated array. Both forms below
are valid:

```bash
pg-diag one-shot \
  --dsn "postgresql://app@127.0.0.1:5432/appdb" \
  --collection-mode remote-db-only \
  --item-id overview.pg_settings \
  --out reports/pg_settings

pg-diag one-shot \
  --dsn "postgresql://app@127.0.0.1:5432/appdb" \
  --collection-mode remote-db-only \
  --item-id=[overview.pg_settings,overview.database_stats] \
  --out reports/settings_and_database_stats
```

Collect multiple interval items and only the hidden sources those selected
metrics require:

```bash
pg-diag snapshots \
  --dsn "postgresql://app@127.0.0.1:5432/appdb" \
  --collection-mode remote-db-only \
  --item-id=[snapshot_delta_workload.database_workload_delta,snapshot_charts_db.database_transaction_rate] \
  --duration-seconds 30 \
  --interval-seconds 5 \
  --out reports/database_workload_selected
```

List the canonical filter tags:

```bash
pg-diag one-shot --tags-list
```

`--tags` accepts a scalar or comma-separated array, matches tags
case-insensitively, and uses OR semantics: an item is selected when it has at
least one requested tag. Brackets are optional for a scalar and supported for
arrays:

```bash
pg-diag one-shot \
  --dsn "postgresql://app@127.0.0.1:5432/appdb" \
  --collection-mode remote-db-only \
  --tags=[security,tables] \
  --out reports/security_or_tables
```

`--item-id` and `--tags` cannot be used together. Unknown tags and every
unknown ID in an item array are reported before SSH or PostgreSQL is opened.

Selection applies to visible report items, not directly to query, script,
Python, metric, or sampler catalog identifiers. In `snapshots` mode:

- Selecting a `query`, `script`, or `python` item executes it once. Since the
  selected plan has no interval dependencies, the timed window is skipped and
  `runtime.snapshot_count` is `0`.
- Selecting a `metric` item automatically plans only its required hidden SQL or
  host sampler dependencies and runs the full required sampling window.

In `one-shot` mode a selected metric is not executed and the final report has
no visible item because interval data is unavailable. The skip reason remains
visible in stdout and `report.log`.

## Collection Timing and Metric Evaluation

### Collection Timing Scopes

| Scope | Execution time | Applicable entries | Typical use |
| --- | --- | --- | --- |
| `once` | Once, before the timed window | Visible `query`, `script`, and `python` report items | Configuration, inventory, current activity, and security evidence |
| `every_snapshot` | At every scheduled point in the timed window | Hidden SQL metric source jobs and sampler-provider outputs | Time-series charts, adjacent-interval rates, and interval Top-N calculations |
| `window_endpoints` | Exactly twice: at the start and end of the timed window | Hidden SQL metric source jobs and sampler-provider outputs | Full-window counter deltas, average rates, and backend `/proc` endpoint tables |
| `post_collection` | Once, after repeated, endpoint, and sampler sources have finished | Visible derived `metric` items assigned this internal scope by the planner | Build final charts/tables, calculate rates and deltas, apply Top-N, and attach coverage diagnostics |

`post_collection` is an internal planned-item scope. Content authors select
`every_snapshot` or `window_endpoints` through a metric's
`requires_collection`; the planner assigns `post_collection` to the visible
metric that consumes those sources.

### `snapshots` Execution Order

| Stage | Work performed | Public artifact behavior |
| ---: | --- | --- |
| 1 | Execute visible `once` items | Results are written to top-level `items` |
| 2 | Collect the start value for `window_endpoints` SQL sources | Kept in memory; not added to the public `snapshots` array |
| 3 | Start required local or SSH-host sampler providers | Providers run concurrently with the database window |
| 4 | At scheduled offsets, execute required `every_snapshot` SQL sources | Compact source samples and their scheduled points are added to the public `snapshots` array |
| 5 | Collect the end value for `window_endpoints` SQL sources | Kept in memory; not added to the public `snapshots` array |
| 6 | Await sampler providers and gather their repeated or endpoint output | Provider data remains metric input rather than a visible report item |
| 7 | Evaluate `post_collection` metrics | Derived items are written to top-level `items` |
| 8 | Validate the artifact and write the selected JSON/HTML representation(s) | `snapshot_count` records the number of retained scheduled sample points |

The timed window starts only when the selected plan needs an interval SQL
source or host sampler. For example, `snapshots --item-id` or `--tags` with
only selected `once` items skips stages 2-6 and does not wait for
`--duration-seconds`.

### Delta and Rate Patterns

`delta` and `rate` are calculation patterns, not collection scopes.

| Pattern | Required source scope | Calculation | Result examples |
| --- | --- | --- | --- |
| Adjacent interval | `every_snapshot` | `delta = value[n] - value[n-1]`; `rate = delta / actual adjacent duration` | Time-series rate charts and interval Top-N |
| Full window | `window_endpoints` | `delta = end_value - start_value`; `rate = delta / actual endpoint duration` | Start/end delta tables and window-average PostgreSQL or `/proc` rates |
| Point-in-time | `once` | No delta; the collected value is presented as current evidence | Settings, catalogs, active sessions, and host inventory |

Counter resets, missing keys, invalid timestamps, and unmatched bounded Top-N
rows do not become artificial zeroes. They produce gaps and coverage metadata
or diagnostics in the derived metric.

## Output Files and Exit Status

By default, both report commands use `--out report` and create
`report/report.log`, `report/report.json`, and `report/report.html`. `--out
PATH` changes that directory.

`--output-format` controls which report representations are written. It accepts
one value (`--output-format=html` or `--output-format=json`) or a comma-separated
list with optional brackets (`--output-format=[html,json]` or
`--output-format=html,json`). The default is both formats. JSON-only collection
does not invoke the HTML renderer; HTML-only collection does not write the JSON
artifact file.

`--json-out FILE` and `--html-out FILE` independently replace the corresponding
enabled report path; passing a path for a format excluded by `--output-format`
is an argument error. `report.log` is always written under `--out`. When both
formats are enabled, the JSON and HTML paths must identify different files.

Each generated file has mode `0600`; JSON and HTML are written atomically.
Progress lines are flushed to `report.log` and identically printed to stdout.
Every line contains `progress=N%`; planner-skipped items are reported as
`SKIP item=SECTION.ITEM reason=...` and their sources are not invoked. Empty
results, unsupported sources, and collection errors remain visible report
items because they describe an actual collection attempt.

Do not infer success only from the presence of files: a report containing an
item-level collection error is deliberately written for diagnosis and the
command then exits with status `1`.

| Exit status | Meaning | Report files |
| ---: | --- | --- |
| `0` | Command completed successfully; for report commands, no item has collection status `error` | Log and the selected report file or files are written |
| `1` | Content/inspection failure, runtime or connection failure, or a written report contains an item collection error | `report.log` may exist even when JSON/HTML could not be written; check stderr and the log |
| `2` | Invalid command-line invocation or rejected argument combination | Not written |
| `130` | Interrupted with `Ctrl-C` | Do not assume a complete report |

With `runtime_policy.fail_fast: false` (the normal bundled policy), independent
items continue after an item error and the diagnostic report is written. With
`fail_fast: true`, collection stops at the first item error and does not write
a partial report.

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
- Operating-system inventory and charts from the collector in `local` mode or
  the SSH target in `remote` mode.
- Session activity, connection pressure, locks, and waits.
- Statement workload capability checks and top SQL reports.
- Snapshot delta/rate workload summaries.
- Table, index, and function workload counters.
- Optional wait sampling data when available.
- Replication, WAL, checkpoints, and I/O views.
- Storage, vacuum, wraparound, sequence, and XID horizon diagnostics.
- Index health checks.
- Cluster inventory, security, and configuration checks.
- Point-in-time `ldd` dependencies for the PostgreSQL main process selected by
  the connected backend PID, including instance port and PID-chain evidence in
  `local` and `remote` modes.
- Per-backend process statistics calculated from two `/proc` window endpoints
  in `local` and `remote` snapshots modes.

Availability depends on PostgreSQL version, installed extensions, database
permissions, collection mode, and host permissions.

Repeated table samples store their column schema once in `snapshot_schemas` and
keep only status, rows, and an optional failure reason in each snapshot point.
Raw snapshot points are not duplicated into the self-contained HTML after
derived metric items have been built. Reports use artifact schema version 4.
The renderer accepts that version only and requires the complete unified
content document and source provenance stored by the collector.

## Content Layout

```text
pg_diag/content/
  README.md                 # content-pack overview and contracts
  report.yaml               # report structure and item ordering
  presentation.yaml         # units, formatting, and renderer rules
  queries.yaml              # query catalog index
  scripts.yaml              # host script catalog
  python.yaml               # trusted Python source catalog
  metrics.yaml              # chart/table metrics and sampler providers
  field_reference.yaml      # inline help for declarative fields
  catalog/                  # query manifests and version ranges
  queries/                  # SQL source files
  scripts/                  # host shell source files
  python/                   # trusted Python source files
  instructions/             # reusable and per-item diagnostic guidance
  EXTENDING.md              # examples for adding report items
  ITEM_DEVELOPMENT_SPEC.md  # normative item/result contract
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

Run the test suite:

```bash
cd pg_diag
. .venv/bin/activate

PYTHONDONTWRITEBYTECODE=1 python -m pytest -q
```

### Test with the minimum Python version

On Linux, the complete suite can be run under Python 3.10 without installing
that interpreter on the host. The Docker socket and CLI are passed into the
Python container so the integration tests can create and reuse their PostgreSQL
14-18 containers:

```bash
cd /home/oleg/Desktop/dev/pg_diag

docker run --rm --init \
  --volume "$PWD:/workspace:ro" \
  --volume /var/run/docker.sock:/var/run/docker.sock \
  --volume "$(command -v docker):/usr/local/bin/docker:ro" \
  --workdir /workspace \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --env PG_DIAG_DOCKER_INTEGRATION=1 \
  python:3.10-slim-bookworm \
  sh -ec 'python -m pip install --quiet ".[test]"; python -m pytest -q -p no:cacheprovider'
```

The PostgreSQL matrix defaults to all supported majors. Restrict it during a
targeted compatibility check by adding, for example,
`--env PG_DIAG_DOCKER_VERSIONS=14,18`. Without
`PG_DIAG_DOCKER_INTEGRATION=1`, only the unit suite runs and the ten Docker
cases are skipped. The derived PostgreSQL images remain in the Docker build
cache; temporary database containers are removed after their version's tests.

Validate content before committing content changes:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pg_diag.cli validate
```

Compile Python files:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m compileall -q pg_diag
```

Run static checks:

```bash
python -m ruff check pg_diag tests
```

## Notes

- Runtime dependencies are intentionally focused: YAML parsing, PostgreSQL
  access, and SSH transport.
- Every PostgreSQL connection requests `default_transaction_read_only=on` in
  the startup settings and verifies both the session default and current
  transaction before collection starts. SQL source transactions additionally
  use an explicit read-only transaction.
- pg_diag never resets PostgreSQL statistics counters. Counter discontinuities
  are only detected and reported; reset functions are never invoked.
- Unsupported PostgreSQL versions fail at runtime planning.
- Report JSON uses strict JSON values. Non-finite runtime/source numbers are
  normalized to `null`, and invalid external artifacts are rejected.
- Local host data and local-only Python sources are omitted without execution
  in `remote-db-only` mode; their skip reasons are logged.
- Host shell items and host-dependent Python checks have a strict one-second
  timeout. A timeout is recorded and rendered inside the affected item; other
  items continue when `fail_fast` is disabled.
- Full `remote` mode authenticates only with the configured key, verifies the
  configured `known_hosts` file, and keeps PostgreSQL sessions read-only through
  the forwarded connection.
- Blocking work requested by trusted Python sources runs in a killable child
  process, so a source timeout does not leave its filesystem or command probe
  running in the collector background.
- A declared sampler provider may own a window-length command. Its command and
  provider grace bounds are explicit in the content/provider contract; ordinary
  host commands remain limited to one second.
- Generated reports are ignored by Git by default.

## License

`pg_diag` is distributed under the [MIT License](https://github.com/O2eg/pg_diag/blob/main/LICENSE).
