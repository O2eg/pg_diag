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
        ssl: str = "on",
        unix_socket_permissions: str = "0770",
        unix_socket_directories: str = "",
        port: str = "5432",
        data_directory: Path | None = None,
    ) -> None:
        self.hba_file = hba_file
        self.listen_addresses = listen_addresses
        self.current_user = current_user
        self.ssl = ssl
        self.unix_socket_permissions = unix_socket_permissions
        self.unix_socket_directories = unix_socket_directories
        self.port = port
        self.data_directory = data_directory or hba_file.parent

    async def fetchval(self, sql: str) -> str:
        if "hba_file" in sql:
            return str(self.hba_file)
        if "data_directory" in sql:
            return str(self.data_directory)
        if "listen_addresses" in sql:
            return self.listen_addresses
        if "current_user" in sql:
            return self.current_user
        if "name = 'ssl'" in sql:
            return self.ssl
        if "unix_socket_permissions" in sql:
            return self.unix_socket_permissions
        if "unix_socket_directories" in sql:
            return self.unix_socket_directories
        if "name = 'port'" in sql:
            return self.port
        raise AssertionError(sql)

    async def fetch(self, sql: str) -> list[dict[str, Any]]:
        if "pg_catalog.pg_shadow" in sql:
            return [
                {
                    "role_name": "legacy_app",
                    "is_superuser": False,
                    "can_create_database": False,
                    "role_oid": 12345,
                    "password_hash": "md5abcdef0123456789abcdef0123456789",
                },
                {
                    "role_name": "scram_app",
                    "is_superuser": False,
                    "can_create_database": False,
                    "role_oid": 12346,
                    "password_hash": "SCRAM-SHA-256$4096:salt$stored:server",
                },
            ]
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


def test_pg_hba_security_python_sources_detect_atomic_findings(
    content_path: Path,
    tmp_path: Path,
) -> None:
    include_dir = tmp_path / "conf.d"
    include_dir.mkdir()
    hba_file = tmp_path / "pg_hba.conf"
    hba_file.write_text(
        "local all all peer\n"
        "include_dir 'conf.d'\n"
        "hostssl appdb app 10.10.0.0/24 scram-sha-256\n",
        encoding="utf-8",
    )
    (include_dir / "20_remote.conf").write_text(
        "host all all 0.0.0.0 0.0.0.0 md5\n",
        encoding="utf-8",
    )

    content = load_content(content_path)
    plan = build_plan(content, 180000, collection_mode=LOCAL_COLLECTION_MODE)
    planned_by_id = {item.item_id: item for item in plan.items}

    insecure = asyncio.run(
        execute_python_item(
            content,
            FakeConn(hba_file),
            planned_by_id["cluster_inventory.pg_hba_insecure_auth_methods"],
        )
    )
    broad = asyncio.run(
        execute_python_item(
            content,
            FakeConn(hba_file),
            planned_by_id["cluster_inventory.pg_hba_broad_network_ranges"],
        )
    )
    generic = asyncio.run(
        execute_python_item(
            content,
            FakeConn(hba_file),
            planned_by_id["cluster_inventory.pg_hba_generic_database_or_user"],
        )
    )
    tls = asyncio.run(
        execute_python_item(
            content,
            FakeConn(hba_file),
            planned_by_id["cluster_inventory.pg_hba_tls_enforcement"],
        )
    )

    assert insecure["collection_status"] == "ok"
    assert insecure["severity_level"] == "medium"
    assert insecure["result"]["row_count"] == 1
    insecure_columns = [column["name"] for column in insecure["result"]["columns"]]
    insecure_row = insecure["result"]["rows"][0]
    assert insecure_row[insecure_columns.index("auth_method")] == "md5"
    assert insecure_row[insecure_columns.index("address")] == "0.0.0.0/0"

    assert broad["collection_status"] == "ok"
    assert broad["severity_level"] == "high"
    assert broad["result"]["row_count"] == 1

    assert generic["collection_status"] == "ok"
    assert generic["severity_level"] == "high"
    assert generic["result"]["row_count"] == 2

    assert tls["collection_status"] == "ok"
    assert tls["severity_level"] == "high"
    assert tls["result"]["row_count"] == 1


def test_local_security_python_sources_detect_permission_findings(
    content_path: Path,
    tmp_path: Path,
) -> None:
    hba_file = tmp_path / "pg_hba.conf"
    hba_file.write_text("local all all peer\n", encoding="utf-8")
    hba_file.chmod(0o644)

    content = load_content(content_path)
    plan = build_plan(content, 180000, collection_mode=LOCAL_COLLECTION_MODE)
    planned_by_id = {item.item_id: item for item in plan.items}

    hba_permissions = asyncio.run(
        execute_python_item(
            content,
            FakeConn(hba_file),
            planned_by_id["cluster_inventory.pg_hba_file_permissions"],
        )
    )
    socket_permissions = asyncio.run(
        execute_python_item(
            content,
            FakeConn(hba_file, unix_socket_permissions="0777"),
            planned_by_id["cluster_inventory.unix_socket_permissions"],
        )
    )

    assert hba_permissions["collection_status"] == "ok"
    assert hba_permissions["severity_level"] == "high"
    assert hba_permissions["result"]["row_count"] == 1
    hba_columns = [column["name"] for column in hba_permissions["result"]["columns"]]
    hba_row = hba_permissions["result"]["rows"][0]
    assert hba_row[hba_columns.index("file_mode")] == "0644"
    assert hba_row[hba_columns.index("expected_file_mode")] == "0600 or 0640"

    assert socket_permissions["collection_status"] == "ok"
    assert socket_permissions["severity_level"] == "high"
    assert socket_permissions["result"]["row_count"] == 1
    socket_columns = [column["name"] for column in socket_permissions["result"]["columns"]]
    socket_row = socket_permissions["result"]["rows"][0]
    assert socket_row[socket_columns.index("configured_permissions")] == "0777"


def test_p2_python_security_sources_detect_local_and_role_findings(
    content_path: Path,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    hba_file = tmp_path / "pg_hba.conf"
    hba_file.write_text("local all all peer\n", encoding="utf-8")
    data_directory = tmp_path / "pgdata"
    data_directory.mkdir()
    data_directory.chmod(0o755)
    pgpass_file = tmp_path / ".pgpass"
    pgpass_file.write_text("localhost:5432:*:app:secret\n", encoding="utf-8")
    pgpass_file.chmod(0o644)
    service_file = tmp_path / ".pg_service.conf"
    service_file.write_text("[app]\nhost=localhost\npassword=secret\n", encoding="utf-8")
    service_file.chmod(0o600)
    monkeypatch.setenv("PGPASSFILE", str(pgpass_file))
    monkeypatch.setenv("PGSERVICEFILE", str(service_file))
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))

    content = load_content(content_path)
    plan = build_plan(content, 180000, collection_mode=LOCAL_COLLECTION_MODE)
    planned_by_id = {item.item_id: item for item in plan.items}

    role_hashes = asyncio.run(
        execute_python_item(
            content,
            FakeConn(hba_file),
            planned_by_id["cluster_inventory.role_password_hashes"],
        )
    )
    pgdata_permissions = asyncio.run(
        execute_python_item(
            content,
            FakeConn(hba_file, data_directory=data_directory),
            planned_by_id["cluster_inventory.pgdata_permissions"],
        )
    )
    client_secret_files = asyncio.run(
        execute_python_item(
            content,
            FakeConn(hba_file),
            planned_by_id["cluster_inventory.postgres_client_secret_files"],
        )
    )

    assert role_hashes["collection_status"] == "ok"
    assert role_hashes["severity_level"] == "high"
    assert role_hashes["result"]["row_count"] == 1
    role_columns = [column["name"] for column in role_hashes["result"]["columns"]]
    role_row = role_hashes["result"]["rows"][0]
    assert role_row[role_columns.index("role_name")] == "legacy_app"
    assert role_row[role_columns.index("hash_type")] == "md5"

    assert pgdata_permissions["collection_status"] == "ok"
    assert pgdata_permissions["severity_level"] == "high"
    pgdata_columns = [column["name"] for column in pgdata_permissions["result"]["columns"]]
    pgdata_row = pgdata_permissions["result"]["rows"][0]
    assert pgdata_row[pgdata_columns.index("directory_mode")] == "0755"

    assert client_secret_files["collection_status"] == "ok"
    assert client_secret_files["severity_level"] == "high"
    secret_columns = [column["name"] for column in client_secret_files["result"]["columns"]]
    secret_rows = client_secret_files["result"]["rows"]
    finding_types = {row[secret_columns.index("finding_type")] for row in secret_rows}
    assert "pgpass_present" in finding_types
    assert "service_password" in finding_types
