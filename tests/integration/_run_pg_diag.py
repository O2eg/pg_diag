"""Run pg_diag with a shorter snapshots minimum for Docker smoke tests only."""

from __future__ import annotations

from pg_diag import runtime_config
from pg_diag.cli import main


runtime_config.SNAPSHOTS_MIN_DURATION_SECONDS = 5.0


if __name__ == "__main__":
    raise SystemExit(main())
