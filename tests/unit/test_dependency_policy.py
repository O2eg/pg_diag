from __future__ import annotations

import tomllib
from pathlib import Path


def test_runtime_dependency_policy(repo_root: Path) -> None:
    data = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = data["project"]["dependencies"]
    normalized = "\n".join(dependencies).lower()

    assert "asyncpg" in normalized
    assert "pyyaml" in normalized
    assert "pydantic" not in normalized
    assert "psycopg" not in normalized
    assert "click" not in normalized
    assert "typer" not in normalized
