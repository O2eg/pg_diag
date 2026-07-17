from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pg_diag.content_loader import load_content
from pg_diag.executors.python import execute_python_item
from pg_diag.planner import build_plan
from pg_diag.runtime_config import LOCAL_COLLECTION_MODE
from pg_diag.ssh_transport import SshCommandResult


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


class FakeLocalSettingsConn:
    def __init__(self, settings: dict[str, str]) -> None:
        self.settings = settings

    async def fetchval(self, sql: str, *args: Any) -> str | None:
        if "where name = $1" in sql:
            return self.settings.get(str(args[0]))
        raise AssertionError((sql, args))


class FakeReadOnlyTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class ControlDataConn:
    def transaction(self, *, readonly: bool):
        assert readonly is True
        return FakeReadOnlyTransaction()

    async def fetchrow(self, sql: str) -> dict[str, Any]:
        assert "current_setting('data_directory')" in sql
        assert "current_setting('server_version_num')" in sql
        return {
            "data_directory": "/var/lib/postgresql/18/main",
            "server_version_num": 180004,
        }


class ControlDataHost:
    def __init__(self, *, returncode: int = 0, stderr: str = "") -> None:
        self.returncode = returncode
        self.stderr = stderr
        self.arguments: tuple[str, ...] | None = None
        self.script: str | None = None

    async def run_script(
        self,
        script: str,
        *,
        arguments: tuple[str, ...] = (),
    ) -> SshCommandResult:
        self.script = script
        self.arguments = arguments
        return SshCommandResult(
            self.returncode,
            "PG_CONFIG: /usr/bin/pg_config\n"
            "PG_CONFIG_BINDIR: /usr/lib/postgresql/18/bin\n"
            "PG_CONTROLDATA: /usr/lib/postgresql/18/bin/pg_controldata\n"
            "pg_control version number:            1800\n"
            "Database system identifier:           123456\n",
            self.stderr,
        )


class PostgresMainLddConn:
    def __init__(
        self,
        *,
        backend_pid: int = 23117,
        server_port: int = 6432,
        database_name: str = "tenant_b",
    ) -> None:
        self.backend_pid = backend_pid
        self.server_port = server_port
        self.database_name = database_name

    def transaction(self, *, readonly: bool):
        assert readonly is True
        return FakeReadOnlyTransaction()

    async def fetchrow(self, sql: str) -> dict[str, Any]:
        assert "pg_catalog.pg_backend_pid()" in sql
        assert "pg_catalog.current_setting('port')" in sql
        return {
            "backend_pid": self.backend_pid,
            "server_port": self.server_port,
            "database_name": self.database_name,
        }


class PostgresMainLddHost:
    def __init__(
        self,
        *,
        returncode: int = 0,
        stdout: str | None = None,
        stderr: str = "",
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.arguments: tuple[str, ...] | None = None
        self.script: str | None = None

    async def run_script(
        self,
        script: str,
        *,
        arguments: tuple[str, ...] = (),
    ) -> SshCommandResult:
        self.script = script
        self.arguments = arguments
        stdout = self.stdout
        if stdout is None:
            stdout = (
                "PGDIAG_BACKEND_PID=23117\n"
                "PGDIAG_POSTGRES_MAIN_PID=22001\n"
                "PGDIAG_POSTGRES_EXECUTABLE=/usr/lib/postgresql/18/bin/postgres\n"
                "PGDIAG_LDD_PATH=/usr/bin/ldd\n"
                "PGDIAG_LDD_BEGIN\n"
                "linux-vdso.so.1 (0x0000ffffaabb0000)\n"
                "libpq.so.5 => /lib/aarch64-linux-gnu/libpq.so.5 (0x0000ffffaa100000)\n"
                "libmissing.so => not found\n"
                "/lib/ld-linux-aarch64.so.1 (0x0000ffffaac00000)\n"
            )
        return SshCommandResult(self.returncode, stdout, self.stderr)


class HugePagesConn:
    def __init__(self, **overrides: Any) -> None:
        self.context: dict[str, Any] = {
            "server_version_num": 180004,
            "backend_pid": 32117,
            "huge_pages_requested": "try",
            "huge_page_size_setting": "0",
            "huge_page_size_unit": "B",
            "huge_pages_status": "off",
            "shared_buffers_setting": "131072",
            "shared_buffers_unit": "8kB",
            "shared_memory_size_setting": "16384",
            "shared_memory_size_unit": "MB",
            "required_huge_pages": "8192",
        }
        self.context.update(overrides)

    def transaction(self, *, readonly: bool):
        assert readonly is True
        return FakeReadOnlyTransaction()

    async def fetchrow(self, sql: str) -> dict[str, Any]:
        assert "shared_memory_size_in_huge_pages" in sql
        assert "pg_catalog.pg_backend_pid()" in sql
        return self.context


class HugePagesHost:
    def __init__(
        self,
        *,
        returncode: int = 0,
        stdout: str | None = None,
        stderr: str = "",
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.script: str | None = None
        self.arguments: tuple[str, ...] | None = None

    async def run_script(
        self,
        script: str,
        *,
        arguments: tuple[str, ...] = (),
    ) -> SshCommandResult:
        self.script = script
        self.arguments = arguments
        stdout = self.stdout
        if stdout is None:
            stdout = (
                "MEM_TOTAL_BYTES=137438953472\n"
                "PAGE_TABLES_BYTES=2147483648\n"
                "SEC_PAGE_TABLES_BYTES=134217728\n"
                "POOL_TOTAL_PAGES=4096\n"
                "POOL_FREE_PAGES=1024\n"
                "POOL_RESERVED_PAGES=256\n"
                "POOL_SURPLUS_PAGES=0\n"
                "OS_DEFAULT_HUGE_PAGE_SIZE_BYTES=2097152\n"
                "HUGETLB_BYTES=8589934592\n"
                "ANON_HUGE_PAGES_BYTES=268435456\n"
                "THP_MODE=always\n"
                "INSTANCE_STATUS=available\n"
                "POSTGRES_PROCESS_COUNT=101\n"
                "POSTGRES_VMPTE_BYTES=1610612736\n"
                "POSTGRES_MAIN_HUGETLB_BYTES=0\n"
            )
        return SshCommandResult(self.returncode, stdout, self.stderr)


def _table_row(item: dict[str, Any]) -> dict[str, Any]:
    columns = [column["name"] for column in item["result"]["columns"]]
    assert item["result"]["row_count"] == 1
    return dict(zip(columns, item["result"]["rows"][0], strict=True))


def test_postgresql_huge_pages_correlates_settings_pool_and_page_tables(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    plan = build_plan(content, 180004, collection_mode=LOCAL_COLLECTION_MODE)
    planned = {item.item_id: item for item in plan.items}["os.postgresql_huge_pages"]
    host = HugePagesHost()

    item = asyncio.run(
        execute_python_item(
            content,
            HugePagesConn(),
            planned,
            ssh_transport=SimpleNamespace(host_access=host),
        )
    )

    assert item["collection_status"] == "ok"
    assert item["severity_level"] == "medium"
    assert planned.collection_scope == "once"
    assert host.arguments == ("32117",)
    assert "/proc/meminfo" in str(host.script)
    assert "/proc/$backend_pid/status" in str(host.script)
    assert "sys_memory_total" not in str(host.script)
    row = _table_row(item)
    assert set(row) == set(
        content.presentation_catalog["presentation_catalog"]["source_overrides"][
            "os.postgresql_huge_pages"
        ]
    )
    assert row["huge_pages_requested"] == "try"
    assert row["huge_pages_actual"] == "off"
    assert row["shared_buffers_bytes"] == 1024**3
    assert row["required_huge_pages"] == 8192
    assert row["required_huge_pages_bytes"] == 16 * 1024**3
    assert row["default_pool_shortfall_pages"] == 4096
    assert row["default_pool_free_unreserved_pages"] == 768
    assert row["host_page_tables_pct_ram"] == 1.5625
    assert row["postgres_vmpte_share_pct"] == 75.0
    assert row["risk_level"] == "medium"
    assert "consider explicit PostgreSQL huge pages" in row["recommendation"]
    titles = {issue["title"] for issue in item["issues"]["items"]}
    assert titles == {
        "PostgreSQL fell back to regular pages",
        "Default HugeTLB pool is smaller than PostgreSQL requirement",
        "Host page-table memory is elevated",
        "Transparent Huge Pages are set to always",
    }


def test_postgresql_huge_pages_healthy_state_is_ok(content_path: Path) -> None:
    content = load_content(content_path)
    plan = build_plan(content, 180004, collection_mode=LOCAL_COLLECTION_MODE)
    planned = {item.item_id: item for item in plan.items}["os.postgresql_huge_pages"]
    host = HugePagesHost(
        stdout=(
            "MEM_TOTAL_BYTES=137438953472\n"
            "PAGE_TABLES_BYTES=268435456\n"
            "SEC_PAGE_TABLES_BYTES=0\n"
            "POOL_TOTAL_PAGES=8192\n"
            "POOL_FREE_PAGES=1024\n"
            "POOL_RESERVED_PAGES=128\n"
            "POOL_SURPLUS_PAGES=0\n"
            "OS_DEFAULT_HUGE_PAGE_SIZE_BYTES=2097152\n"
            "HUGETLB_BYTES=17179869184\n"
            "ANON_HUGE_PAGES_BYTES=0\n"
            "THP_MODE=madvise\n"
            "INSTANCE_STATUS=available\n"
            "POSTGRES_PROCESS_COUNT=50\n"
            "POSTGRES_VMPTE_BYTES=67108864\n"
            "POSTGRES_MAIN_HUGETLB_BYTES=17179869184\n"
        )
    )

    item = asyncio.run(
        execute_python_item(
            content,
            HugePagesConn(huge_pages_requested="on", huge_pages_status="on"),
            planned,
            ssh_transport=SimpleNamespace(host_access=host),
        )
    )

    assert item["collection_status"] == "ok"
    assert item["severity_level"] == "ok"
    assert item["issues"]["items"] == []
    row = _table_row(item)
    assert row["huge_pages_actual"] == "on"
    assert row["default_pool_shortfall_pages"] == 0
    assert row["risk_level"] == "ok"


def test_postgresql_huge_pages_host_probe_failure_is_unsupported(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    plan = build_plan(content, 180004, collection_mode=LOCAL_COLLECTION_MODE)
    planned = {item.item_id: item for item in plan.items}["os.postgresql_huge_pages"]

    item = asyncio.run(
        execute_python_item(
            content,
            HugePagesConn(),
            planned,
            ssh_transport=SimpleNamespace(
                host_access=HugePagesHost(
                    returncode=3,
                    stdout="",
                    stderr="/proc/meminfo is unavailable",
                )
            ),
        )
    )

    assert item["collection_status"] == "unsupported"
    assert item["severity_level"] == "unknown"
    assert item["result"]["row_count"] == 0
    assert "/proc/meminfo is unavailable" in item["reason"]
    assert item["diagnostics"][0]["code"] == "postgresql_huge_pages_host_probe_failed"


def test_postgres_main_ldd_uses_connected_backend_parent_and_parses_dependencies(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    plan = build_plan(content, 180004, collection_mode=LOCAL_COLLECTION_MODE)
    planned = {item.item_id: item for item in plan.items}[
        "backend_os.postgres_main_process_linked_libraries"
    ]
    host = PostgresMainLddHost()

    item = asyncio.run(
        execute_python_item(
            content,
            PostgresMainLddConn(),
            planned,
            ssh_transport=SimpleNamespace(host_access=host),
        )
    )

    assert item["collection_status"] == "ok"
    assert item["severity_level"] == "unknown"
    assert host.arguments == ("23117",)
    assert "/proc/$backend_pid/status" in str(host.script)
    assert "PPid" in str(host.script)
    assert '"$ldd_bin" "/proc/$postgres_main_pid/exe"' in str(host.script)
    assert "pgrep" not in str(host.script)
    columns = [column["name"] for column in item["result"]["columns"]]
    rows = item["result"]["rows"]
    assert item["result"]["row_count"] == 4
    assert {row[columns.index("server_port")] for row in rows} == {6432}
    assert {row[columns.index("database_name")] for row in rows} == {"tenant_b"}
    assert {row[columns.index("backend_pid")] for row in rows} == {23117}
    assert {row[columns.index("postgres_main_pid")] for row in rows} == {22001}
    by_library = {row[columns.index("library")]: row for row in rows}
    libpq = by_library["libpq.so.5"]
    assert libpq[columns.index("resolved_path")] == "/lib/aarch64-linux-gnu/libpq.so.5"
    assert libpq[columns.index("link_status")] == "resolved"
    assert by_library["linux-vdso.so.1"][columns.index("link_status")] == "virtual"
    assert by_library["libmissing.so"][columns.index("link_status")] == "not_found"
    assert by_library["ld-linux-aarch64.so.1"][columns.index("link_status")] == "loader"
    assert any(
        diagnostic["code"] == "postgres_main_ldd_dependency_not_found"
        for diagnostic in item["diagnostics"]
    )


def test_postgres_main_ldd_does_not_fall_back_to_another_postgres_instance(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    plan = build_plan(content, 180004, collection_mode=LOCAL_COLLECTION_MODE)
    planned = {item.item_id: item for item in plan.items}[
        "backend_os.postgres_main_process_linked_libraries"
    ]
    host = PostgresMainLddHost(
        returncode=42,
        stdout="",
        stderr="PID 23117 is 'python3', not a PostgreSQL backend",
    )

    item = asyncio.run(
        execute_python_item(
            content,
            PostgresMainLddConn(),
            planned,
            ssh_transport=SimpleNamespace(host_access=host),
        )
    )

    assert item["collection_status"] == "unsupported"
    assert item["result"]["row_count"] == 0
    assert "PID 23117" in item["reason"]
    assert item["diagnostics"][0]["code"] == "postgres_main_process_unavailable"
    assert host.arguments == ("23117",)


def test_postgres_main_ldd_failure_is_an_item_error(content_path: Path) -> None:
    content = load_content(content_path)
    plan = build_plan(content, 180004, collection_mode=LOCAL_COLLECTION_MODE)
    planned = {item.item_id: item for item in plan.items}[
        "backend_os.postgres_main_process_linked_libraries"
    ]
    host = PostgresMainLddHost(
        returncode=1,
        stdout=(
            "PGDIAG_BACKEND_PID=23117\n"
            "PGDIAG_POSTGRES_MAIN_PID=22001\n"
            "PGDIAG_POSTGRES_EXECUTABLE=/usr/lib/postgresql/18/bin/postgres\n"
            "PGDIAG_LDD_PATH=/usr/bin/ldd\n"
            "PGDIAG_LDD_BEGIN\n"
        ),
        stderr="ldd: exited unexpectedly",
    )

    item = asyncio.run(
        execute_python_item(
            content,
            PostgresMainLddConn(),
            planned,
            ssh_transport=SimpleNamespace(host_access=host),
        )
    )

    assert item["collection_status"] == "error"
    assert "main process PID 22001" in item["reason"]
    assert item["diagnostics"][0]["code"] == "postgres_main_ldd_failed"


def test_pg_controldata_uses_running_server_binary_and_parses_output(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    plan = build_plan(content, 180004, collection_mode=LOCAL_COLLECTION_MODE)
    planned = {item.item_id: item for item in plan.items}["overview.pg_controldata"]
    host = ControlDataHost()

    item = asyncio.run(
        execute_python_item(
            content,
            ControlDataConn(),
            planned,
            ssh_transport=SimpleNamespace(host_access=host),
        )
    )

    assert item["collection_status"] == "ok"
    assert item["result"]["kind"] == "table"
    assert host.arguments == ("/var/lib/postgresql/18/main", "18")
    assert "pg_config_bin=$(command -v pg_config" in str(host.script)
    assert '\"$pg_controldata_bin\" -D \"$data_directory\"' in str(host.script)
    rows = {row[0]: row[1] for row in item["result"]["rows"]}
    assert rows["PG_CONTROLDATA"] == "/usr/lib/postgresql/18/bin/pg_controldata"
    assert rows["DATA_DIRECTORY"] == "/var/lib/postgresql/18/main"
    assert rows["SERVER_VERSION_NUM"] == "180004"
    assert rows["pg_control version number"] == "1800"
    assert rows["Database system identifier"] == "123456"


def test_pg_controldata_permission_failure_is_an_item_error(content_path: Path) -> None:
    content = load_content(content_path)
    plan = build_plan(content, 180004, collection_mode=LOCAL_COLLECTION_MODE)
    planned = {item.item_id: item for item in plan.items}["overview.pg_controldata"]
    host = ControlDataHost(
        returncode=1,
        stderr="pg_controldata: could not open global/pg_control: Permission denied",
    )

    item = asyncio.run(
        execute_python_item(
            content,
            ControlDataConn(),
            planned,
            ssh_transport=SimpleNamespace(host_access=host),
        )
    )

    assert item["collection_status"] == "error"
    assert "Permission denied" in item["reason"]
    assert item["diagnostics"][0]["code"] == "pg_controldata_failed"


class DatabaseVolumeMainConn:
    def transaction(self, *, readonly: bool):
        assert readonly is True
        return FakeReadOnlyTransaction()

    async def fetch(self, sql: str) -> list[dict[str, Any]]:
        assert "from pg_catalog.pg_database" in sql
        return [
            {
                "database_oid": 100,
                "database_name": "large_db",
                "allows_connections": True,
                "can_connect": True,
            },
            {
                "database_oid": 101,
                "database_name": "timeout_db",
                "allows_connections": True,
                "can_connect": True,
            },
        ]


class DatabaseVolumeConn:
    def __init__(self, size: int | None) -> None:
        self.size = size

    def transaction(self, *, readonly: bool):
        assert readonly is True
        return FakeReadOnlyTransaction()

    async def fetchval(self, sql: str, *args: Any) -> int:
        assert "pg_catalog.pg_database_size" in sql
        if self.size is None:
            raise TimeoutError
        return self.size

    async def fetchrow(self, sql: str) -> dict[str, int]:
        assert "relation_counts" in sql
        return {
            "schemas": 2,
            "tables": 10,
            "partitioned_tables": 1,
            "partitions": 20,
            "indexes": 15,
            "partitioned_indexes": 1,
            "index_partitions": 30,
            "views": 3,
            "materialized_views": 2,
            "sequences": 4,
            "foreign_tables": 0,
            "composite_types": 1,
            "functions": 5,
            "procedures": 1,
            "aggregates": 0,
            "window_functions": 0,
            "triggers": 6,
            "constraints": 12,
            "enum_types": 2,
            "range_types": 0,
            "domains": 1,
            "row_security_policies": 2,
            "rules": 0,
            "extensions": 3,
            "event_triggers": 0,
            "publications": 1,
            "subscriptions": 0,
            "foreign_data_wrappers": 1,
            "foreign_servers": 1,
            "collations": 1,
            "conversions": 0,
            "extended_statistics": 2,
            "large_objects": 3,
        }


class DatabaseVolumeConnector:
    def __init__(self) -> None:
        self.order: list[str] = []
        self.active = 0
        self.max_active = 0

    @asynccontextmanager
    async def connect(self, database_name: str, *, timeout_seconds: float | None = None):
        assert timeout_seconds == 10.0
        self.order.append(database_name)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            yield DatabaseVolumeConn(1024 if database_name == "large_db" else None)
        finally:
            self.active -= 1


def test_database_volume_collects_databases_sequentially_and_preserves_size_timeout(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    plan = build_plan(content, 180000, collection_mode=LOCAL_COLLECTION_MODE)
    planned = {item.item_id: item for item in plan.items}["overview.database_volume"]
    connector = DatabaseVolumeConnector()

    item = asyncio.run(
        execute_python_item(
            content,
            DatabaseVolumeMainConn(),
            planned,
            database_connector=connector,
        )
    )

    assert item["collection_status"] == "ok"
    assert item["severity_level"] == "unknown"
    assert connector.order == ["large_db", "timeout_db"]
    assert connector.max_active == 1
    columns = [column["name"] for column in item["result"]["columns"]]
    rows = item["result"]["rows"]
    assert rows[0][columns.index("database_name")] == "large_db"
    assert rows[0][columns.index("database_size_bytes")] == 1024
    assert rows[0][columns.index("tables")] == 10
    assert rows[0][columns.index("partitions")] == 20
    assert rows[0][columns.index("index_partitions")] == 30
    assert rows[1][columns.index("database_name")] == "timeout_db"
    assert rows[1][columns.index("database_size_bytes")] is None
    assert item["result"]["cell_statuses"] == [
        {
            "row_index": 1,
            "column": "database_size_bytes",
            "status": "timeout",
            "reason": "Database size calculation exceeded 10 seconds",
        }
    ]
    assert rows[1][columns.index("tables")] == 10
    assert rows[1][columns.index("collection_status")] == "database size timed out"

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        if "from pg_tablespace" in sql:
            return []
        raise AssertionError((sql, args))


def test_remote_superuser_access_python_source_detects_hba_rule(content_path: Path, tmp_path: Path) -> None:
    hba_file = tmp_path / "pg_hba.conf"
    hba_file.write_text(
        "local all all peer\n"
        "host all postgres 0.0.0.0 0.0.0.0 scram-sha-256\n",
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
    assert row[column_names.index("address")] == "0.0.0.0/0"
    assert row[column_names.index("auth_method")] == "scram-sha-256"
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
    assert generic["severity_level"] == "unknown"
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
    assert hba_permissions["severity_level"] == "medium"
    assert hba_permissions["result"]["row_count"] == 1
    hba_columns = [column["name"] for column in hba_permissions["result"]["columns"]]
    hba_row = hba_permissions["result"]["rows"][0]
    assert hba_row[hba_columns.index("file_mode")] == "0644"
    assert "0600/0640 are typical" in hba_row[hba_columns.index("expected_file_mode")]

    assert socket_permissions["collection_status"] == "ok"
    assert socket_permissions["severity_level"] == "medium"
    assert socket_permissions["result"]["row_count"] == 1
    socket_columns = [column["name"] for column in socket_permissions["result"]["columns"]]
    socket_row = socket_permissions["result"]["rows"][0]
    assert socket_row[socket_columns.index("configured_permissions")] == "0777"


def test_pg_hba_permissions_include_recursively_included_files(
    content_path: Path,
    tmp_path: Path,
) -> None:
    include_dir = tmp_path / "hba.d"
    include_dir.mkdir(mode=0o755)
    included = include_dir / "20_app.conf"
    included.write_text("host app app 127.0.0.1/32 scram-sha-256\n", encoding="utf-8")
    included.chmod(0o660)
    hba_file = tmp_path / "pg_hba.conf"
    hba_file.write_text("include_dir 'hba.d'\n", encoding="utf-8")
    hba_file.chmod(0o600)

    content = load_content(content_path)
    plan = build_plan(content, 180000, collection_mode=LOCAL_COLLECTION_MODE)
    planned = {
        item.item_id: item for item in plan.items
    }["cluster_inventory.pg_hba_file_permissions"]

    item = asyncio.run(execute_python_item(content, FakeConn(hba_file), planned))

    assert item["severity_level"] == "high"
    columns = [column["name"] for column in item["result"]["columns"]]
    rows = item["result"]["rows"]
    assert any(
        row[columns.index("file_path")] == str(included.resolve())
        and row[columns.index("file_mode")] == "0660"
        for row in rows
    )


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


def test_log_permission_check_does_not_pass_when_directory_is_missing(
    content_path: Path,
    tmp_path: Path,
) -> None:
    content = load_content(content_path)
    plan = build_plan(content, 180000, collection_mode=LOCAL_COLLECTION_MODE)
    planned = {item.item_id: item for item in plan.items}["os.log_file_permissions"]
    conn = FakeLocalSettingsConn(
        {
            "logging_collector": "on",
            "log_directory": str(tmp_path / "missing-log-directory"),
            "data_directory": str(tmp_path),
        }
    )

    item = asyncio.run(execute_python_item(content, conn, planned))

    assert item["collection_status"] == "ok"
    assert item["severity_level"] == "medium"
    assert item["result"]["row_count"] == 1
    assert "cannot enumerate" in item["issues"]["summary"]["description"]


def test_wal_archive_permission_check_reports_archive_library_as_unsupported(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    plan = build_plan(content, 180000, collection_mode=LOCAL_COLLECTION_MODE)
    planned = {item.item_id: item for item in plan.items}["os.wal_archive_directory_permissions"]
    conn = FakeLocalSettingsConn(
        {
            "archive_mode": "on",
            "archive_command": "",
            "archive_library": "custom_archive_library",
        }
    )

    item = asyncio.run(execute_python_item(content, conn, planned))

    assert item["collection_status"] == "unsupported"
    assert item["severity_level"] == "unknown"
    assert "archive_library" in item["reason"]


def test_tls_key_permission_check_is_skipped_when_tls_is_disabled(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    plan = build_plan(content, 180000, collection_mode=LOCAL_COLLECTION_MODE)
    planned = {item.item_id: item for item in plan.items}["os.tls_key_file_permissions"]

    item = asyncio.run(
        execute_python_item(content, FakeLocalSettingsConn({"ssl": "off"}), planned)
    )

    assert item["collection_status"] == "skipped"
    assert item["severity_level"] == "unknown"
    assert "disabled" in item["reason"]
