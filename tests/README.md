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

- `test_cli.py` - CLI command behavior for validation, planning, query inspection,
  and rendering from JSON.
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
- `test_os_metrics.py` - local OS sampler parsing, derived values, and backend
  process window-endpoint rates.
- `test_python_executor.py` - trusted content Python source execution and
  source-specific behavior.
- `test_public_output.py` - public artifact shape, column-name cleanup,
  redaction, source text embedding, and item-level error diagnostics.
- `test_render.py` - generated HTML/JS/CSS behavior used by the report UI.
- `test_report_output_paths.py` - snapshot and snapshots JSON/HTML output path,
  including once/endpoints/chart-window execution order
  selection.

## Integration Tests

Integration tests are opt-in. They are skipped unless
`PG_DIAG_DOCKER_INTEGRATION` is set to a true value.

Requirements:

- installed project development dependencies;
- Docker CLI available to the current user;
- `psql` and `pgbench` available in `PATH`;
- a local `.venv` in the repository, because the integration test invokes
  `.venv/bin/python -m pg_diag.cli`.

Install useful extras:

```bash
cd /home/oleg/Desktop/dev/pg_diag
. .venv/bin/activate

python -m pip install -e ".[dev]"
python -m pip install -e ".[docker]"
```

Run the Docker integration test:

```bash
PG_DIAG_DOCKER_INTEGRATION=1 \
PYTHONDONTWRITEBYTECODE=1 \
python -m pytest -q tests/integration
```

Use a different PostgreSQL image:

```bash
PG_DIAG_DOCKER_INTEGRATION=1 \
PG_DIAG_DOCKER_IMAGE=postgres:17 \
PYTHONDONTWRITEBYTECODE=1 \
python -m pytest -q tests/integration
```

The current integration test starts PostgreSQL, initializes pgbench data, runs a
short background load, collects a report, checks `report.json` and
`report.html`, and removes the container in `finally`.

## Full Test Run

Run the default suite:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q
```

Without `PG_DIAG_DOCKER_INTEGRATION=1`, the Docker integration test is reported
as skipped.

## When Adding Tests

- Add content contract tests for new rules in `content/*.yaml`, query catalogs,
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
PYTHONDONTWRITEBYTECODE=1 python -m pg_diag.cli validate --content content
```

Preview a PostgreSQL 18 snapshots plan:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pg_diag.cli explain-plan \
  --content content \
  --pg-version 180000 \
  --run-mode snapshots \
  --collection-mode local
```

Compile Python files:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m py_compile \
  pg_diag/*.py \
  pg_diag/executors/*.py \
  pg_diag/render/*.py
```
