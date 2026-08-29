from __future__ import annotations

import asyncio
import json
from typing import Any

from pg_diag.cli import build_parser
from pg_diag.collection import CollectionRun, collect_report_object_ddl
from pg_diag.object_ddl import (
    MAX_DDL_CHARS,
    _entry,
    collect_object_ddl,
    harvest_object_oids,
)


def _table_item(columns: list[str], rows: list[list[Any]]) -> dict[str, Any]:
    return {
        "result": {
            "kind": "table",
            "columns": [{"name": name} for name in columns],
            "rows": rows,
        }
    }


def test_harvest_object_oids_allowlist_and_dedup() -> None:
    artifact = {
        "items": {
            "a": _table_item(
                ["table_oid", "redundant_index_oid", "function_oid", "sample_oid"],
                [
                    [1001, 2001, 4001, 9001],
                    [1001, None, "4002", 9002],
                    ["not-an-oid", True, {"status": "error"}, 9003],
                ],
            ),
            "b": _table_item(
                ["constraint_oid", "role_oid", "relid", "datid", "trigger_oid"],
                [[3001, 8001, 1003, 5, 5001]],
            ),
            "c": _table_item(
                ["dbid", "userid", "owner_oid", "grantee_oid", "tablespace_oid", "usesysid",
                 "funcid"],
                [[7, 8002, 8003, 8004, 1663, 8005, 4003]],
            ),
            "d": {"result": {"kind": "none"}},
        }
    }
    harvested = harvest_object_oids(artifact)
    assert harvested["relation"] == {1001, 2001, 1003}
    assert harvested["function"] == {4001, 4002, 4003}
    assert harvested["constraint"] == {3001}
    assert harvested["trigger"] == {5001}
    assert harvested["database"] == {5, 7}
    assert harvested["role"] == {8001, 8002, 8003, 8004, 8005}
    assert harvested["tablespace"] == {1663}


def test_harvest_object_oids_from_snapshots() -> None:
    artifact = {
        "items": {},
        "snapshot_schemas": {
            "metrics.tables": {"columns": [{"name": "relid"}, {"name": "relname"}]}
        },
        "snapshots": [
            {"items": {"metrics.tables": {"result": {"kind": "table", "rows": [[1007, "t"]]}}}},
            {"items": {"metrics.tables": {"result": {"kind": "table", "rows": [[1008, "u"]]}}}},
        ],
    }
    harvested = harvest_object_oids(artifact)
    assert harvested["relation"] == {1007, 1008}


def test_entry_truncates_long_ddl() -> None:
    entry = _entry("table", "public.t", "x" * (MAX_DDL_CHARS + 10))
    assert len(entry["ddl"]) < MAX_DDL_CHARS + 100
    assert entry["ddl"].endswith("-- [pg_diag] DDL truncated")


class RoutedConn:
    def __init__(self, routes: list[tuple[str, list[dict[str, Any]]]]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        self.calls.append((sql, args))
        for needle, rows in self.routes:
            if needle in sql:
                return rows
        raise AssertionError("no route for sql: " + " ".join(sql.split())[:120])

    async def fetchval(self, sql: str, *args: Any) -> Any:
        return 150000


def sec(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"section": name, "payload": json.dumps(payload)}


def _rel(oid: int, relkind: str, identifier: str, **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "oid": oid,
        "relkind": relkind,
        "relpersistence": "p",
        "identifier": identifier,
        "reltype": 0,
        "relispartition": False,
        "relispopulated": True,
        "relhasoids": False,
        "partition_bound": None,
        "partition_key": None,
        "of_type": None,
        "reloptions": None,
        "access_method": "heap",
        "tablespace": None,
        "view_definition": None,
        "index_definition": None,
        "parents": None,
        "foreign_server": None,
        "foreign_options_sql": None,
    }
    base.update(extra)
    return base


def _routes() -> list[tuple[str, list[dict[str, Any]]]]:
    column = {
        "table_oid": 1001,
        "attnum": 1,
        "name_q": "id",
        "type_name": "integer",
        "not_null": True,
        "is_local": True,
        "identity": "",
        "generated": "",
        "default_expr": None,
        "collation_sql": None,
        "fdw_options_sql": None,
    }
    bundle_rows = [
        sec("relation", _rel(1001, "r", "public.t")),
        sec("column", column),
        sec(
            "index",
            {
                "oid": 6001,
                "table_oid": 1001,
                "identifier": "public.t_idx",
                "index_definition": "CREATE INDEX t_idx ON public.t USING btree (id)",
                "is_valid": True,
                "backs_constraint": False,
            },
        ),
        sec(
            "trigger",
            {
                "oid": 5001,
                "table_oid": 1001,
                "function_oid": 4001,
                "name_q": "trg",
                "table_identifier": "public.t",
                "definition": "CREATE TRIGGER trg ...",
                "enabled": "O",
            },
        ),
        sec(
            "function",
            {
                "oid": 4001,
                "identifier": "public.touch()",
                "prokind": "f",
                "definition": "CREATE OR REPLACE FUNCTION public.touch() ...",
            },
        ),
    ]
    relation_rows = [
        sec("relation", _rel(1002, "v", "public.v", view_definition=" SELECT 1;")),
    ]
    function_rows = [
        {
            "oid": 4009,
            "identifier": "public.f()",
            "prokind": "f",
            "definition": "CREATE OR REPLACE FUNCTION public.f() ...",
        }
    ]
    constraint_rows = [
        {
            "oid": 3001,
            "table_oid": 1001,
            "domain_oid": 0,
            "name_q": "t_check",
            "contype": "c",
            "is_local": True,
            "definition": "CHECK ((id > 0))",
            "table_identifier": "public.t",
            "domain_identifier": None,
        }
    ]
    return [
        ("'trigger'::text as section", bundle_rows),
        ("'sequence'::text as section", relation_rows),
        ("from pg_catalog.pg_proc p", function_rows),
        ("from pg_catalog.pg_constraint c", constraint_rows),
    ]


def _artifact_with_oids() -> dict[str, Any]:
    return {
        "items": {
            "a": _table_item(
                ["table_oid", "relation_oid", "function_oid", "constraint_oid"],
                [[1001, 1002, 4009, 3001]],
            )
        }
    }


def test_collect_object_ddl_builds_catalog() -> None:
    conn = RoutedConn(_routes())
    catalog = asyncio.run(collect_object_ddl(conn, 150000, _artifact_with_oids()))

    assert set(catalog) == {"1001", "1002", "4009", "3001"}
    table_entry = catalog["1001"]
    assert table_entry["kind"] == "table"
    assert table_entry["identifier"] == "public.t"
    assert "CREATE TABLE public.t (" in table_entry["ddl"]
    assert "CREATE INDEX t_idx" in table_entry["ddl"]
    assert "CREATE TRIGGER trg" in table_entry["ddl"]
    assert "FUNCTION public.touch()" in table_entry["ddl"]
    assert catalog["1002"]["kind"] == "view"
    assert catalog["4009"]["ddl"].startswith("CREATE OR REPLACE FUNCTION public.f()")
    assert catalog["3001"]["ddl"].startswith(
        "ALTER TABLE public.t\n    ADD CONSTRAINT t_check"
    )

    relations_calls = [
        args for sql, args in conn.calls if "'sequence'::text as section" in sql
    ]
    assert relations_calls == [([1002],)]


def _run(conn: Any, *, connected: bool = True, items: dict[str, Any] | None = None) -> CollectionRun:
    return CollectionRun(
        content=None,  # type: ignore[arg-type]
        conn=conn,
        plan=None,  # type: ignore[arg-type]
        artifact={
            "runtime": {"database_connected": connected, "server_version_num": 150000},
            "items": items if items is not None else _artifact_with_oids()["items"],
        },
        fail_fast=False,
        json_path=None,
        html_path=None,
        database_connector=None,
    )


def test_collect_report_object_ddl_disabled_and_unavailable() -> None:
    run = _run(RoutedConn([]))
    asyncio.run(collect_report_object_ddl(run, enabled=False))
    assert run.artifact["object_ddl"] == {}
    assert run.artifact["runtime"]["ddl_extraction"] == "disabled"

    run = _run(None)
    asyncio.run(collect_report_object_ddl(run, enabled=True))
    assert run.artifact["object_ddl"] == {}
    assert run.artifact["runtime"]["ddl_extraction"] == "unavailable"


def test_collect_report_object_ddl_collects_and_survives_errors() -> None:
    run = _run(RoutedConn(_routes()))
    asyncio.run(collect_report_object_ddl(run, enabled=True))
    assert run.artifact["runtime"]["ddl_extraction"] == "collected"
    assert "1001" in run.artifact["object_ddl"]

    class BrokenConn:
        async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
            raise RuntimeError("boom")

    run = _run(BrokenConn())
    asyncio.run(collect_report_object_ddl(run, enabled=True))
    assert run.artifact["object_ddl"] == {}
    assert run.artifact["runtime"]["ddl_extraction"].startswith("failed: RuntimeError")


def test_cli_disable_ddl_flag() -> None:
    parser = build_parser()
    args = parser.parse_args(["one-shot", "--disable-ddl"])
    assert args.disable_ddl is True
    args = parser.parse_args(["snapshots"])
    assert args.disable_ddl is False


def test_redact_function_ddl_and_entry() -> None:
    from pg_diag.object_ddl import _entry, redact_function_ddl

    src = (
        "CREATE OR REPLACE FUNCTION public.f()\n"
        "AS $fn$\n"
        "  v_token := 'super-secret';\n"
        "  return 1;\n"
        "$fn$;"
    )
    redacted = redact_function_ddl(src)
    assert "super-secret" not in redacted
    assert "[REDACTED]" in redacted
    assert "return 1;" in redacted
    kept = redact_function_ddl("SET app.password TO '[REDACTED]';")
    assert kept == "SET app.password TO '[REDACTED]';"

    entry = _entry("function", "public.f()", src)
    assert "super-secret" not in entry["ddl"]
    table_entry = _entry("table", "public.t", "    password_hash text,")
    assert table_entry["ddl"] == "    password_hash text,"


def test_bundle_document_order_and_constraint_index_skip() -> None:
    from pg_diag.ddlx import ObjectDdl, TableBundle
    from pg_diag.object_ddl import bundle_document

    bundle = TableBundle(
        table=ObjectDdl(1, "table", "public.t", "CREATE TABLE public.t ();"),
        indexes=(ObjectDdl(2, "index", "public.t_idx", "CREATE INDEX t_idx ...;"),),
        triggers=(ObjectDdl(3, "trigger", "trg ON public.t", "CREATE TRIGGER trg ...;"),),
        trigger_functions=(
            ObjectDdl(4, "function", "public.touch()", "CREATE FUNCTION public.touch() ...;"),
        ),
    )
    document = bundle_document(bundle)
    assert document.index("CREATE FUNCTION public.touch()") < document.index(
        "CREATE TRIGGER trg"
    )
