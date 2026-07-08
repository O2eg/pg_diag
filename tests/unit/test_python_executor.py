from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pg_diag.content_loader import load_content
from pg_diag.executors.python import execute_python_item
from pg_diag.planner import build_plan
from pg_diag.runtime_config import LOCAL_COLLECTION_MODE


class FakeConn:
    def __init__(
        self,
        hba_file: Path,
        *,
        listen_addresses: str = "*",
        current_user: str = "postgres",
    ) -> None:
        self.hba_file = hba_file
        self.listen_addresses = listen_addresses
        self.current_user = current_user

    async def fetchval(self, sql: str) -> str:
        if "hba_file" in sql:
            return str(self.hba_file)
        if "listen_addresses" in sql:
            return self.listen_addresses
        if "current_user" in sql:
            return self.current_user
        raise AssertionError(sql)

    async def fetch(self, sql: str) -> list[dict[str, Any]]:
        if "where rolsuper" in sql and "role_membership" not in sql:
            return [{"rolname": "postgres", "rolcanlogin": True}]
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
    assert item["issues"]["summary"]["title"] == "Externally reachable superuser host access is allowed"
    assert "Matched login superusers: postgres" in item["issues"]["summary"]["description"]
    assert "Current database user 'postgres' is a superuser" in item["issues"]["summary"]["description"]
    assert item["result"]["row_count"] == 1
    row = item["result"]["rows"][0]
    column_names = [column["name"] for column in item["result"]["columns"]]
    assert row[column_names.index("allows_superuser")] is True
    assert row[column_names.index("allowed_superusers")] == "postgres"
    assert row[column_names.index("matched_superuser_roles")] == "postgres"
    assert row[column_names.index("database_scope")] == "all"
    assert row[column_names.index("network_scope")] == "external"
    assert row[column_names.index("listen_addresses")] == "*"
    assert row[column_names.index("listen_reachable")] == "yes"
    assert row[column_names.index("auth_risk")] == "password"
    assert row[column_names.index("risk_level")] == "high"
    assert row[column_names.index("current_user_is_matched_superuser")] is True


def test_remote_superuser_access_classifies_loopback_trust(content_path: Path, tmp_path: Path) -> None:
    hba_file = tmp_path / "pg_hba.conf"
    hba_file.write_text(
        "local all all peer\n"
        "host all postgres 127.0.0.1/32 trust\n",
        encoding="utf-8",
    )
    content = load_content(content_path)
    plan = build_plan(content, 180000, collection_mode=LOCAL_COLLECTION_MODE)
    planned = {
        item.item_id: item for item in plan.items
    }["cluster_inventory.remote_superuser_access"]

    item = asyncio.run(
        execute_python_item(
            content,
            FakeConn(hba_file, listen_addresses="localhost"),
            planned,
        )
    )

    assert item["severity_level"] == "high"
    assert item["issues"]["summary"]["title"] == "Trust authentication allows local superuser access"
    assert "1 loopback/samehost rule(s)" in item["issues"]["summary"]["description"]
    assert "1 trust-auth rule(s)" in item["issues"]["summary"]["description"]
    row = item["result"]["rows"][0]
    column_names = [column["name"] for column in item["result"]["columns"]]
    assert row[column_names.index("network_scope")] == "loopback"
    assert row[column_names.index("listen_reachable")] == "yes"
    assert row[column_names.index("auth_risk")] == "trust"
    assert row[column_names.index("risk_level")] == "high"


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
    row = item["result"]["rows"][0]
    column_names = [column["name"] for column in item["result"]["columns"]]
    assert row[column_names.index("allows_superuser")] is False
    assert row[column_names.index("network_scope")] == "private"
    assert row[column_names.index("risk_level")] == "ok"


def test_remote_superuser_access_reports_missing_hba_as_unsupported(content_path: Path, tmp_path: Path) -> None:
    content = load_content(content_path)
    plan = build_plan(content, 180000, collection_mode=LOCAL_COLLECTION_MODE)
    planned = {
        item.item_id: item for item in plan.items
    }["cluster_inventory.remote_superuser_access"]

    item = asyncio.run(execute_python_item(content, FakeConn(tmp_path / "missing_pg_hba.conf"), planned))

    assert item["collection_status"] == "unsupported"
    assert item["result"]["row_count"] == 0
    assert "not visible locally" in item["reason"]
    assert item["diagnostics"][0]["level"] == "warning"
    assert item["diagnostics"][0]["code"] == "security_remote_superuser_access_hba_file_missing"
