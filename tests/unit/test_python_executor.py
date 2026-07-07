from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pg_diag.content_loader import load_content
from pg_diag.executors.python import execute_python_item
from pg_diag.planner import build_plan
from pg_diag.runtime_config import LOCAL_COLLECTION_MODE


class FakeConn:
    def __init__(self, hba_file: Path) -> None:
        self.hba_file = hba_file

    async def fetchval(self, sql: str) -> str:
        assert "hba_file" in sql
        return str(self.hba_file)

    async def fetch(self, sql: str) -> list[dict[str, Any]]:
        if "where rolsuper" in sql and "role_membership" not in sql:
            return [{"rolname": "postgres"}]
        if "role_membership" in sql:
            return []
        raise AssertionError(sql)


def test_remote_superuser_access_python_source_detects_hba_rule(content_path: Path, tmp_path: Path) -> None:
    hba_file = tmp_path / "pg_hba.conf"
    hba_file.write_text(
        "local all all peer\n"
        "host all postgres 0.0.0.0/0 scram-sha-256\n",
        encoding="utf-8",
    )
    content = load_content(content_path)
    plan = build_plan(content, 180000, collection_mode=LOCAL_COLLECTION_MODE)
    planned = {
        item.item_id: item for item in plan.items
    }["cluster_inventory.remote_superuser_access"]

    item = asyncio.run(execute_python_item(content, FakeConn(hba_file), planned))

    assert item["collection_status"] == "ok"
    assert item["severity_level"] == "high"
    assert item["source_kind"] == "python"
    assert item["issues"]["summary"]["severity"] == "high"
    assert item["issues"]["summary"]["status"] == "fail"
    assert item["result"]["row_count"] == 1
    row = item["result"]["rows"][0]
    column_names = [column["name"] for column in item["result"]["columns"]]
    assert row[column_names.index("allows_superuser")] is True
    assert row[column_names.index("allowed_superusers")] == "postgres"


def test_remote_superuser_access_python_source_returns_ok_when_no_issue(content_path: Path, tmp_path: Path) -> None:
    hba_file = tmp_path / "pg_hba.conf"
    hba_file.write_text(
        "local all all peer\n"
        "host all app_user 10.0.0.0/8 scram-sha-256\n",
        encoding="utf-8",
    )
    content = load_content(content_path)
    plan = build_plan(content, 180000, collection_mode=LOCAL_COLLECTION_MODE)
    planned = {
        item.item_id: item for item in plan.items
    }["cluster_inventory.remote_superuser_access"]

    item = asyncio.run(execute_python_item(content, FakeConn(hba_file), planned))

    assert item["collection_status"] == "ok"
    assert item["severity_level"] == "ok"
    assert item["issues"]["summary"]["severity"] == "ok"
    assert item["issues"]["summary"]["status"] == "pass"
