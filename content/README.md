# pg_diag Content Pack

This directory contains the first declarative report structure for `pg_diag`.

- `report.yaml` - report layout: sections and lightweight item references (`query`, `script`, `metric`).
- `queries.yaml` - query catalog index and defaults.
- `catalog/*.yaml` - grouped query manifests with PostgreSQL version variants.
- `metrics.yaml` - metric-series declarations for charts in `snapshots` mode.
- `scripts.yaml` - local shell source declarations and remote DB-only defaults.
- `queries/` - SQL files referenced only by query manifests.
- `scripts/` - shell scripts referenced only by `scripts.yaml`.

The report layout intentionally does not define SQL output columns. Table headers must be derived from the actual result metadata of the selected SQL variant. Query manifests may define display hints such as `display.default_sort.column` and `display.default_sort.direction`; these hints are applied by renderers without changing the raw JSON rows.

For extension examples, see `EXTENDING.md`.
