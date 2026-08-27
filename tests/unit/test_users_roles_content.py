from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import re
from types import SimpleNamespace

from pg_diag.content_loader import load_content
from pg_diag.planner import build_plan
from pg_diag.runtime_config import ONE_SHOT_MODE, REMOTE_DB_ONLY_COLLECTION_MODE
from pg_diag.versioning import select_query_variant


SECTION_ID = "users_roles"
EXPECTED_ITEMS = (
    "roles_inventory",
    "password_validity",
    "group_roles_without_members",
    "object_ownership_by_role",
    "role_membership",
    "effective_role_membership",
    "admin_option_holders",
    "role_database_settings",
    "database_privileges",
    "tablespace_privileges",
    "parameter_privileges",
    "language_privileges",
    "foreign_server_access",
    "object_privileges_by_grantee",
    "relation_privileges_detail",
    "column_privileges",
    "default_privileges",
    "rls_policies_by_role",
    "large_object_privileges",
    "publication_ownership",
    "subscription_ownership",
    "session_usage",
    "connection_security",
    "hba_rules",
    "ident_mappings",
)
CURRENT_DATABASE_ITEMS = {
    "object_ownership_by_role",
    "foreign_server_access",
    "object_privileges_by_grantee",
    "relation_privileges_detail",
    "column_privileges",
    "default_privileges",
    "rls_policies_by_role",
    "large_object_privileges",
    "publication_ownership",
}
VERSION_VARIANTS = {
    "roles.membership": {
        100000: "roles_membership_pg10_pg15",
        150000: "roles_membership_pg10_pg15",
        160000: "roles_membership_pg16_plus",
        180000: "roles_membership_pg16_plus",
    },
    "roles.effective_membership": {
        100000: "roles_effective_membership_pg10_pg15",
        160000: "roles_effective_membership_pg16_plus",
    },
    "roles.admin_option_holders": {
        100000: "roles_admin_option_holders_pg10_pg15",
        160000: "roles_admin_option_holders_pg16_plus",
    },
    "roles.connection_security": {
        100000: "roles_connection_security_pg10_pg11",
        110000: "roles_connection_security_pg10_pg11",
        120000: "roles_connection_security_pg12_plus",
        180000: "roles_connection_security_pg12_plus",
    },
    "roles.parameter_privileges": {
        150000: "roles_parameter_privileges_pg15_plus",
        180000: "roles_parameter_privileges_pg15_plus",
    },
    "roles.publication_ownership": {
        100000: "roles_publication_ownership_pg10",
        110000: "roles_publication_ownership_pg11_pg12",
        120000: "roles_publication_ownership_pg11_pg12",
        130000: "roles_publication_ownership_pg13_plus",
        180000: "roles_publication_ownership_pg13_plus",
    },
}


def _roles_sql_files(content_path: Path) -> list[Path]:
    return sorted((content_path / "queries" / "roles").glob("*.sql"))


def test_users_roles_section_declares_expected_items(content_path: Path) -> None:
    content = load_content(content_path)
    sections = list(content.report["sections"])
    assert sections.index(SECTION_ID) == sections.index("cluster_inventory") + 1
    section = content.report["sections"][SECTION_ID]
    assert tuple(section["items"]) == EXPECTED_ITEMS
    expanded = [key for key, item in section["items"].items() if item.get("state") == "expanded"]
    assert expanded == [
        "roles_inventory",
        "role_membership",
        "role_database_settings",
        "database_privileges",
        "object_privileges_by_grantee",
    ]
    for key, item in section["items"].items():
        assert "Security" in item["tags"], key
        source_kind = next(iter({"query", "python"}.intersection(item)))
        assert item[source_kind].startswith("roles."), key


def test_users_roles_items_resolve_database_scope(content_path: Path) -> None:
    content = load_content(content_path)
    plan = build_plan(content, 180000, mode=ONE_SHOT_MODE, collection_mode="local")
    by_key = {item.item_key: item for item in plan.items if item.section_id == SECTION_ID}
    assert set(by_key) == set(EXPECTED_ITEMS)
    for key, item in by_key.items():
        expected = "current_database" if key in CURRENT_DATABASE_ITEMS else "all_databases"
        assert item.source_metadata["database_scope"] == expected, key


def test_users_roles_version_variants_cover_postgresql_10_to_18(content_path: Path) -> None:
    content = load_content(content_path)
    for query_id, expected in VERSION_VARIANTS.items():
        manifest = content.queries[query_id]
        for version, variant_id in expected.items():
            selection = select_query_variant(query_id, manifest, version)
            assert selection.status == "ok", (query_id, version)
            assert selection.variant["id"] == variant_id, (query_id, version)
    for version in (100000, 140000):
        selection = select_query_variant(
            "roles.parameter_privileges",
            content.queries["roles.parameter_privileges"],
            version,
        )
        assert selection.status == "unsupported"
        assert "PostgreSQL 15" in selection.reason
    for query_id in content.queries:
        if not query_id.startswith("roles."):
            continue
        if query_id == "roles.parameter_privileges":
            continue
        for version in (100000, 120000, 150000, 160000, 180000):
            selection = select_query_variant(query_id, content.queries[query_id], version)
            assert selection.status == "ok", (query_id, version)


def test_users_roles_pg10_variants_declare_unsupported_columns(content_path: Path) -> None:
    content = load_content(content_path)
    membership = select_query_variant(
        "roles.membership", content.queries["roles.membership"], 150000
    ).variant
    assert set(membership["column_statuses"]) == {"inherit_option", "set_option"}
    modern = select_query_variant(
        "roles.membership", content.queries["roles.membership"], 160000
    ).variant
    assert not modern.get("column_statuses")
    security = select_query_variant(
        "roles.connection_security", content.queries["roles.connection_security"], 110000
    ).variant
    assert set(security["column_statuses"]) == {"gss_encrypted_session_count"}
    publication = content.queries["roles.publication_ownership"]
    assert set(select_query_variant("roles.publication_ownership", publication, 100000).variant["column_statuses"]) == {
        "publishes_truncate",
        "publish_via_partition_root",
    }
    assert set(select_query_variant("roles.publication_ownership", publication, 120000).variant["column_statuses"]) == {
        "publish_via_partition_root",
    }
    assert not select_query_variant("roles.publication_ownership", publication, 130000).variant.get("column_statuses")


def test_users_roles_queries_are_bounded_and_surface_coverage(content_path: Path) -> None:
    for sql_path in _roles_sql_files(content_path):
        sql = sql_path.read_text(encoding="utf-8").lower()
        assert re.search(r"\blimit\s+\d+\b", sql), sql_path.name
        assert "_truncated" in sql, sql_path.name
        assert "pg_diag_internal_severity" in sql or "risk_level" in sql, sql_path.name
        assert "'unknown'" in sql, sql_path.name


def test_users_roles_catalog_queries_bound_candidates_before_acl_expansion(
    content_path: Path,
) -> None:
    for name in (
        "object_privileges_by_grantee.sql",
        "relation_privileges_detail.sql",
        "object_ownership_by_role.sql",
    ):
        sql = (content_path / "queries" / "roles" / name).read_text(encoding="utf-8").lower()
        assert "order by c.relpages desc" in sql, name
        assert "candidate_sample_truncated" in sql, name
        first_limit = sql.index("limit ")
        assert first_limit < sql.find("aclexplode") if "aclexplode" in sql else True, name
    large_objects = (
        content_path / "queries" / "roles" / "large_object_privileges.sql"
    ).read_text(encoding="utf-8").lower()
    assert large_objects.index("limit 10001") < large_objects.index("aclexplode")
    assert "lo_compat_privileges" in large_objects
    subscription = (
        content_path / "python" / "roles" / "subscription_ownership.py"
    ).read_text(encoding="utf-8").lower()
    assert "subconninfo" not in subscription
    assert "limit " in subscription
    matrix = (
        content_path / "queries" / "roles" / "object_privileges_by_grantee.sql"
    ).read_text(encoding="utf-8").lower()
    assert "group by nspname, relkind, relowner, acl_signature" in matrix
    assert "acl_expansion_truncated" in matrix
    assert "result_truncated" in matrix
    assert "'[coverage]'" in matrix
    column = (content_path / "queries" / "roles" / "column_privileges.sql").read_text(
        encoding="utf-8"
    ).lower()
    assert column.index("limit 5001") < column.index("pg_attribute")
    assert "column_sample_truncated" in column


def test_users_roles_heavy_catalog_queries_declare_bounded_timeouts(content_path: Path) -> None:
    content = load_content(content_path)
    for query_id in (
        "roles.object_ownership_by_role",
        "roles.object_privileges_by_grantee",
        "roles.relation_privileges_detail",
        "roles.column_privileges",
    ):
        manifest = content.queries[query_id]
        assert manifest["timeout_ms"] == 3000, query_id
        assert manifest["cost"] == "medium", query_id


def test_users_roles_python_sources_run_in_remote_db_only_mode(content_path: Path) -> None:
    content = load_content(content_path)
    for python_id in ("roles.hba_rules", "roles.ident_mappings", "roles.subscription_ownership"):
        manifest = content.pythons[python_id]
        assert manifest["targets"] == ["db"]
        assert manifest["local_only"] is False
        assert manifest["timeout_ms"] == 5000
    plan = build_plan(
        content,
        180000,
        mode=ONE_SHOT_MODE,
        collection_mode=REMOTE_DB_ONLY_COLLECTION_MODE,
    )
    by_key = {item.item_key: item for item in plan.items if item.section_id == SECTION_ID}
    assert by_key["hba_rules"].status == "planned"
    assert by_key["ident_mappings"].status == "planned"
    assert by_key["subscription_ownership"].status == "planned"
    assert by_key["parameter_privileges"].status == "planned"
    legacy = build_plan(
        content,
        100000,
        mode=ONE_SHOT_MODE,
        collection_mode=REMOTE_DB_ONLY_COLLECTION_MODE,
    )
    legacy_by_key = {item.item_key: item for item in legacy.items if item.section_id == SECTION_ID}
    assert legacy_by_key["parameter_privileges"].status == "unsupported"
    assert legacy_by_key["role_membership"].variant_id == "roles_membership_pg10_pg15"


class _FakeRecord(dict):
    pass


class _FakeConn:
    def __init__(self, version: int, rows: list[dict] | None = None, error: Exception | None = None):
        self.version = version
        self.rows = rows or []
        self.error = error
        self.queries: list[str] = []

    async def fetchval(self, sql: str) -> str:
        assert "server_version_num" in sql
        return str(self.version)

    async def fetch(self, sql: str) -> list[_FakeRecord]:
        self.queries.append(sql)
        if self.error is not None:
            raise self.error
        return [_FakeRecord(row) for row in self.rows]


def _load_source(content_path: Path, relative: str):
    path = content_path / "python" / relative
    spec = importlib.util.spec_from_file_location("test_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ctx(conn: _FakeConn) -> SimpleNamespace:
    return SimpleNamespace(conn=conn)


def test_hba_rules_source_flags_parse_errors_and_orders_by_rule_number(content_path: Path) -> None:
    module = _load_source(content_path, "roles/hba_rules.py")
    rows = [
        {
            "evaluation_order": 8,
            "file_name": "/etc/postgresql/extra.conf",
            "rule_number": 8,
            "line_number": 1,
            "connection_type": "host",
            "databases": "all",
            "user_names": "all",
            "address": "10.0.0.0",
            "netmask": "255.0.0.0",
            "auth_method": "scram-sha-256",
            "options": None,
            "error": None,
        },
        {
            "evaluation_order": 9,
            "file_name": "/etc/postgresql/pg_hba.conf",
            "rule_number": None,
            "line_number": 11,
            "connection_type": None,
            "databases": None,
            "user_names": None,
            "address": None,
            "netmask": None,
            "auth_method": None,
            "options": None,
            "error": "invalid authentication method \"scram\"",
        },
    ]
    conn = _FakeConn(160000, rows)
    result = asyncio.run(module.collect(_ctx(conn)))
    assert "r.rule_number::int8 as evaluation_order" in conn.queries[0]
    assert "order by r.rule_number nulls last, r.line_number" in conn.queries[0]
    assert result.collection_status == "ok"
    assert result.severity_level == "high"
    columns = [column["name"] for column in result.result["columns"]]
    assert columns[0] == "evaluation_order"
    risk_index = columns.index("risk_level")
    assert [row[risk_index] for row in result.result["rows"]] == ["ok", "high"]
    assert result.issues["summary"]["status"] == "fail"


def test_hba_rules_source_uses_line_order_before_pg16(content_path: Path) -> None:
    module = _load_source(content_path, "roles/hba_rules.py")
    for version in (100000, 150000):
        conn = _FakeConn(version, [])
        result = asyncio.run(module.collect(_ctx(conn)))
        sql = conn.queries[0]
        assert "r.line_number::int8 as evaluation_order" in sql, version
        assert "null::text as file_name" in sql, version
        assert "r.file_name" not in sql and "r.rule_number" not in sql, version
        assert result.collection_status == "empty"


def test_hba_rules_source_propagates_unexpected_sql_errors(content_path: Path) -> None:
    module = _load_source(content_path, "roles/hba_rules.py")
    error = Exception('column "file_name" does not exist')
    error.sqlstate = "42703"
    try:
        asyncio.run(module.collect(_ctx(_FakeConn(150000, error=error))))
    except Exception as raised:
        assert raised is error
    else:
        raise AssertionError("unexpected SQL errors must propagate to the executor")


def test_hba_rules_source_reports_permission_denied_as_unsupported(content_path: Path) -> None:
    module = _load_source(content_path, "roles/hba_rules.py")
    error = Exception("permission denied for view pg_hba_file_rules")
    error.sqlstate = "42501"
    result = asyncio.run(module.collect(_ctx(_FakeConn(150000, error=error))))
    assert result.collection_status == "unsupported"
    assert "requires superuser" in result.reason
    assert result.diagnostics[0]["code"] == "roles_hba_rules_permission_denied"


def test_ident_mappings_source_handles_pg14_pg15_and_pg16(content_path: Path) -> None:
    module = _load_source(content_path, "roles/ident_mappings.py")
    conn = _FakeConn(140000)
    result = asyncio.run(module.collect(_ctx(conn)))
    assert result.collection_status == "unsupported"
    assert conn.queries == []

    pg15 = _FakeConn(
        150000,
        [
            {
                "evaluation_order": 3,
                "file_name": None,
                "map_number": None,
                "line_number": 3,
                "map_name": "ops",
                "system_user_name": "alice",
                "role_name": "postgres",
                "error": None,
            }
        ],
    )
    result = asyncio.run(module.collect(_ctx(pg15)))
    assert "m.line_number::int8 as evaluation_order" in pg15.queries[0]
    assert "m.file_name" not in pg15.queries[0] and "m.map_number" not in pg15.queries[0]
    assert result.collection_status == "ok"
    assert result.severity_level == "ok"
    assert result.issues == {}

    pg16 = _FakeConn(160000, [])
    asyncio.run(module.collect(_ctx(pg16)))
    assert "m.map_number::int8 as evaluation_order" in pg16.queries[0]
    assert "m.file_name::text as file_name" in pg16.queries[0]

    error = Exception('column "file_name" does not exist')
    error.sqlstate = "42703"
    try:
        asyncio.run(module.collect(_ctx(_FakeConn(150000, error=error))))
    except Exception as raised:
        assert raised is error
    else:
        raise AssertionError("unexpected SQL errors must propagate to the executor")


def test_subscription_ownership_source_reports_permission_denied_as_unsupported(
    content_path: Path,
) -> None:
    module = _load_source(content_path, "roles/subscription_ownership.py")
    assert "subconninfo" not in module.SQL
    error = Exception("permission denied for table pg_subscription")
    error.sqlstate = "42501"
    result = asyncio.run(module.collect(_ctx(_FakeConn(140000, error=error))))
    assert result.collection_status == "unsupported"
    assert "PostgreSQL 14 and older" in result.reason
    rows = [
        {
            "database_name": "appdb",
            "subscription_name": "sub_app",
            "owner_name": "replication_owner",
            "owner_can_login": True,
            "owner_is_superuser": False,
            "enabled": True,
            "slot_name": "sub_app",
            "publications": "pub_app",
            "in_current_database": True,
        }
    ]
    result = asyncio.run(module.collect(_ctx(_FakeConn(150000, rows))))
    assert result.collection_status == "ok"
    assert result.severity_level == "ok"
    columns = [column["name"] for column in result.result["columns"]]
    assert columns[-1] == "result_truncated"
    assert result.result["rows"][0][columns.index("owner_name")] == "replication_owner"


def test_subscription_ownership_source_propagates_unexpected_sql_errors(content_path: Path) -> None:
    module = _load_source(content_path, "roles/subscription_ownership.py")
    error = Exception("canceling statement due to statement timeout")
    error.sqlstate = "57014"
    try:
        asyncio.run(module.collect(_ctx(_FakeConn(150000, error=error))))
    except Exception as raised:
        assert raised is error
    else:
        raise AssertionError("unexpected SQL errors must propagate to the executor")


def test_effective_membership_flags_strong_role_attributes(content_path: Path) -> None:
    for name in ("effective_membership_pg10_pg15.sql", "effective_membership_pg16_plus.sql"):
        sql = (content_path / "queries" / "roles" / name).read_text(encoding="utf-8").lower()
        assert "inherited_role_attributes" in sql, name
        for attribute in ("rolcreaterole", "rolcreatedb", "rolreplication", "rolbypassrls"):
            assert attribute in sql, (name, attribute)
        assert "through set role" in sql, name
    modern = (
        content_path / "queries" / "roles" / "effective_membership_pg16_plus.sql"
    ).read_text(encoding="utf-8").lower()
    assert "f.inherited_role_attributes <> '' and not f.member_is_superuser and f.can_set_role then 'medium'" in modern
    legacy = (
        content_path / "queries" / "roles" / "effective_membership_pg10_pg15.sql"
    ).read_text(encoding="utf-8").lower()
    assert "f.inherited_role_attributes <> '' and not f.member_is_superuser then 'medium'" in legacy
