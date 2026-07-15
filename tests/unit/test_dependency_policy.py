from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib


def test_runtime_dependency_policy(repo_root: Path) -> None:
    data = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["requires-python"] == ">=3.10"
    assert data["tool"]["ruff"]["target-version"] == "py310"
    assert data["tool"]["setuptools"]["packages"]["find"]["namespaces"] is False
    assert "content/**/*" in data["tool"]["setuptools"]["package-data"]["pg_diag"]
    dependencies = data["project"]["dependencies"]
    normalized = "\n".join(dependencies).lower()

    assert "asyncpg" in normalized
    assert "asyncssh" in normalized
    assert "pyyaml" in normalized
    assert "pydantic" not in normalized
    assert "psycopg" not in normalized
    assert "click" not in normalized
    assert "typer" not in normalized


def test_distribution_metadata_policy(repo_root: Path) -> None:
    data = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))

    assert data["build-system"]["requires"] == ["setuptools>=77.0.3"]

    project = data["project"]
    assert project["license"] == "MIT AND BSD-3-Clause AND Apache-2.0"
    assert project["license-files"] == [
        "LICENSE",
        "pg_diag/render/vendor/*LICENSE*",
        "pg_diag/render/vendor/*NOTICE*",
        "pg_diag/render/vendor/THIRD_PARTY_LICENSES.txt",
    ]
    assert project["authors"] == [{"name": "O2eg", "email": "oleg.ispu@yandex.ru"}]
    assert project["keywords"] == ["postgresql", "diagnostics", "dba"]
    assert project["urls"] == {
        "Homepage": "https://github.com/O2eg/pg_diag",
        "Repository": "https://github.com/O2eg/pg_diag",
        "Issues": "https://github.com/O2eg/pg_diag/issues",
    }
