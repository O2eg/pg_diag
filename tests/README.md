# Tests

This directory contains unit and integration tests for `pg_diag`.

## Layout

- `conftest.py` - shared pytest fixtures for the repository root and bundled
  content path.
- `unit/` - fast tests that do not require PostgreSQL, Docker, or network
  access.
- `integration/` - tests that start a real PostgreSQL container and collect a
  report from a loaded database.
- `data/` - reserved for small static fixtures when a test needs file-based
  input.

## Unit Tests

Run all unit tests:

```bash
cd /home/oleg/Desktop/dev/pg_diag
. .venv/bin/activate

PYTHONDONTWRITEBYTECODE=1 python -m pytest -q tests/unit
```

Run one test module:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q tests/unit/test_metric_engine.py
```

Run one test:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q \
  tests/unit/test_content_contract.py::test_content_manifests_are_valid
```

The main unit-test groups are:

- `test_cli.py` - CLI command behavior for validation, report selection by
  item-ID arrays or tag intersections, selection-list output, planning, query
  inspection, and rendering from JSON.
- `test_core_engine.py` - scheduler bounds, collection scopes, compact snapshots, strict artifact
  validation, secure output, Python timeouts, renderer substitution safety,
  metric source statuses, and content path/checksum contracts.
- `test_content_contract.py` - declarative content rules: report references,
  version ranges, collection policy, default sort hints, snapshot promotion, and
  semantic metric references.
- `test_dependency_policy.py` - runtime dependency policy. Keep the dependency
  set small.
- `test_metric_engine.py` - rate, delta, top-N, ratio, chart, and table metric
  calculations from snapshots.
- `test_os_metrics.py` - Linux provider parsing, derived values, and backend
  process window-endpoint rates.
- `test_sampler_runtime.py` - declarative provider dispatch, output/error
  contracts, and enforcement that core modules contain no bundled sampler or
  item implementation names.
- `test_python_executor.py` - trusted content Python source execution and
  source-specific behavior.
- `test_public_output.py` - public artifact shape, column-name cleanup,
  redaction, source text embedding, and item-level error diagnostics.
- `test_render.py` - generated HTML/JS/CSS behavior used by the report UI.
- `test_report_output_paths.py` - one-shot and snapshots output-format selection and JSON/HTML paths,
  secure mirrored progress logs, planner-skipped source suppression, and
  once/endpoints/chart-window execution order selection.
- `test_ssh_transport.py` - strict AsyncSSH key authentication, known-host
  verification, dynamic PostgreSQL forwarding, stdin shell execution, SFTP
  host access, remote OS sampling, local evaluation of every host-dependent
  Python item, passfile matching, and cleanup. It includes an in-process
  loopback SSH server and needs no external sshd or network access.

## Browser Renderer Test

Run the optional self-contained HTML renderer test in Chromium:

```bash
python -m pip install -e '.[browser]'
python -m playwright install chromium
PG_DIAG_BROWSER_TESTS=1 python -m pytest -q tests/browser/test_echarts_report.py
```

The browser test opens the generated report through `file://`, rejects external
HTTP requests and console errors, and checks SVG rendering, line/stacked chart
configuration, zoom, drag-pan, six-row scrollable legends, consistent
axis/tooltip unit scaling, theme switching, and SVG/PNG/CSV export.

## Integration Tests

Integration tests are opt-in. They are skipped unless
`PG_DIAG_DOCKER_INTEGRATION` is set to a true value.

Requirements:

- installed project development dependencies;
- Docker CLI available to the current user;
- the project and test dependencies installed in the active Python interpreter;
- Python 3.10 or newer.

Install useful extras:

```bash
cd /home/oleg/Desktop/dev/pg_diag
. .venv/bin/activate

python -m pip install -e ".[dev]"
python -m pip install -e ".[docker]"
```

Run the complete Docker matrix for PostgreSQL 10 through 18:

```bash
PG_DIAG_DOCKER_INTEGRATION=1 \
PYTHONDONTWRITEBYTECODE=1 \
python -m pytest -q tests/integration
```

Run only selected PostgreSQL majors while developing a fix:

```bash
PG_DIAG_DOCKER_INTEGRATION=1 \
PG_DIAG_DOCKER_VERSIONS=10,13,18 \
PYTHONDONTWRITEBYTECODE=1 \
python -m pytest -q tests/integration
```

Each major uses a cached image derived from an official PostgreSQL image:
PostgreSQL 10 uses `postgres:10-bullseye`, while PostgreSQL 11-18 use
`postgres:<major>-bookworm`. The image installs OpenSSH, host inspection
utilities, and the matching `postgresql-<major>-pg-wait-sampling` package. Set
`PG_DIAG_DOCKER_PULL=1` when the official base images must be refreshed.
The PostgreSQL 10 image intentionally retains Bullseye's legacy
`lshw 02.18.x` and `sysstat/iostat 12.5.x`; the test asserts those package
generations so compatibility is not accidentally proved with newer binaries.

For every PostgreSQL major, one module-scoped container is prepared and reused
by both report tests. Preparation is mandatory and verifies all of the
following before collection starts:

- `shared_preload_libraries` contains `pg_stat_statements,pg_wait_sampling`;
- `pg_stat_statements`, `pg_wait_sampling`, and `pg_buffercache` are created in
  the target database;
- pgbench data is initialized and a short background workload is started for
  each report;
- a fresh Ed25519 client key, root `authorized_keys`, SSH host keys, and a
  strict generated `known_hosts` file are installed;
- pg_diag reaches both PostgreSQL and the operating-system collectors through
  the container IP and the SSH tunnel used by `--collection-mode remote`.

The first test builds a complete remote `one-shot` report. The second builds a
remote `snapshots` report and exercises both `every_snapshot` and
`window_endpoints` sources. The integration-only launcher reduces the snapshots
window to five seconds with exactly two points; the production CLI minimum is
unchanged.

These tests are execution smoke tests, not semantic-output tests. They require
every applicable SQL, shell, Python, metric, and compact snapshot item to avoid
`collection_status=error`. Runtime `empty`, `unsupported`, and
configuration-dependent `skipped` results remain valid. Every planned shell and
Python report item must either appear in the report or have an explicit runtime
entry in `report.log`. Snapshot collection additionally rejects sampler-provider
errors and requires the `iostat`-backed disk charts to be materialized. The
container is removed after both tests for its major; the derived Docker image
remains cached for later test iterations.

## Full Test Run

Run the default suite:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q
```

Without `PG_DIAG_DOCKER_INTEGRATION=1`, the eighteen Docker matrix cases are reported
as skipped.

## When Adding Tests

- Add content contract tests for new rules in `src/pg_diag/content/*.yaml`, query catalogs,
  SQL files, scripts, Python sources, or metric declarations.
- Add Python executor tests for new trusted Python source behavior, especially
  local file access, diagnostics, issues, and result shape.
- Add metric engine tests for every new transform, top-N mode, ratio mode,
  chart shape, or table metric behavior.
- Add renderer tests when HTML, CSS, JavaScript, item controls, chart controls,
  search, filtering, or navigation behavior changes.
- Add public output tests when `report.json` shape, redaction, diagnostics,
  metadata, or public column naming changes.
- Add core engine tests when scheduling, orchestration policy, artifact storage,
  output security, or content loading contracts change.
- Add integration coverage only for behavior that needs a real PostgreSQL
  server or external command execution.

Prefer narrow tests with explicit fixture data. Do not make unit tests depend on
generated reports in `reports/`.

## When Correcting Tests

- If a test fails because the implementation is wrong, fix the implementation
  first.
- If a content contract intentionally changes, update the contract test and the
  relevant content documentation in the same change.
- If a renderer assertion becomes stale after an intentional UI change, keep the
  assertion tied to stable behavior rather than incidental formatting.
- If a metric output changes, verify whether the source data, transform, time
  axis, or units changed before updating expected values.
- Keep integration tests opt-in and self-cleaning. Containers, ports, and output
  directories must not leak into the developer environment.

## Useful Checks

Validate content:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pg_diag.cli validate
```

Preview a PostgreSQL 18 snapshots plan:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pg_diag.cli explain-plan \
  --pg-version 180000 \
  --run-mode snapshots \
  --collection-mode local
```

Compile Python files:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m py_compile \
  src/pg_diag/*.py \
  src/pg_diag/executors/*.py \
  src/pg_diag/render/*.py
```
