from __future__ import annotations

from pg_diag.artifact import extract_item_query_texts, item_error_from_exception, item_from_plan
from pg_diag.executors.shell import table_json_result
from pg_diag.executors.sql import publicize_table_result
from pg_diag.planner import PlannedItem


def test_sql_result_uses_public_column_names_and_omits_epoch() -> None:
    raw_columns = [
        {"name": "epoch_ns", "pg_type": "int8"},
        {"name": "tag_datname", "pg_type": "name"},
        {"name": "tag_setting_name", "pg_type": "text"},
        {"name": "setting_value", "pg_type": "text"},
    ]
    raw_rows = [[1783182080458119000, "pg_diag_loadtest", "work_mem", "4MB"]]

    columns, rows = publicize_table_result(raw_columns, raw_rows)

    assert [column["name"] for column in columns] == ["datname", "setting_name", "setting_value"]
    assert rows == [["pg_diag_loadtest", "work_mem", "4MB"]]


def test_item_metadata_uses_public_semantic_column_refs() -> None:
    planned = PlannedItem(
        item_id="overview.pg_settings",
        section_id="overview",
        item_key="pg_settings",
        title="PostgreSQL Settings",
        source_kind="query",
        status="planned",
        source_metadata={
            "query_id": "cluster.settings",
            "semantic_columns": {
                "dimensions": {
                    "database": "tag_datname",
                    "setting": "tag_setting_name",
                }
            },
        },
    )

    item = item_from_plan(planned, collection_status="ok")

    assert item["source_metadata"]["semantic_columns"]["dimensions"] == {
        "database": "datname",
        "setting": "setting_name",
    }
    assert item["collection_status"] == "ok"
    assert item["severity_level"] == "unknown"
    assert "status" not in item


def test_item_metadata_can_embed_source_text() -> None:
    planned = PlannedItem(
        item_id="overview.server_version",
        section_id="overview",
        item_key="server_version",
        title="PostgreSQL Full Version",
        source_kind="query",
        status="planned",
        source_metadata={"query_id": "cluster.server_version"},
    )

    item = item_from_plan(
        planned,
        collection_status="ok",
        source_text="select version()",
        source_language="sql",
    )

    assert item["source_metadata"]["source_text"] == "select version()"
    assert item["source_metadata"]["source_language"] == "sql"


def test_item_query_texts_are_moved_to_artifact_catalog() -> None:
    item = {
        "result": {
            "kind": "table",
            "columns": [
                {"name": "pid"},
                {"name": "query_id"},
                {"name": "query"},
                {"name": "blocked_query_id"},
                {"name": "blocked_query"},
            ],
            "rows": [
                [101, "11", "select 1", "22", "select blocked"],
                [102, "11", "select 1 from pg_catalog.pg_class", "", "ignored"],
            ],
            "row_count": 2,
        },
    }
    query_texts: dict[str, str] = {}

    extract_item_query_texts(
        item,
        query_texts,
        {"id_column_suffix": "query_id", "value_column_remove_suffix": "_id"},
    )

    assert [column["name"] for column in item["result"]["columns"]] == ["pid", "query_id", "blocked_query_id"]
    assert item["result"]["rows"] == [[101, "11", "22"], [102, "11", ""]]
    assert query_texts == {
        "11": "select 1 from pg_catalog.pg_class",
        "22": "select blocked",
    }


def test_item_error_from_exception_embeds_traceback_diagnostic() -> None:
    planned = PlannedItem(
        item_id="os.bad_script",
        section_id="os",
        item_key="bad_script",
        title="Bad Script",
        source_kind="script",
        status="planned",
        source_metadata={"script_id": "os.bad_script"},
    )

    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        item = item_error_from_exception(planned, exc, source_text="exit 1", source_language="bash")

    assert item["collection_status"] == "error"
    assert item["severity_level"] == "unknown"
    assert item["reason"] == "boom"
    assert item["result"]["kind"] == "plain_text"
    assert "RuntimeError: boom" in item["result"]["data"]
    assert item["diagnostics"][0]["code"] == "python_exception"
    assert "RuntimeError: boom" in item["diagnostics"][0]["traceback"]
    assert item["source_metadata"]["source_text"] == "exit 1"


def test_shell_table_json_result_builds_dynamic_table_and_redacts() -> None:
    result = table_json_result(
        '[{"id":"cpu","product":"Xeon"},{"id":"disk","password":"secret","size":1024}]'
    )

    assert result["kind"] == "table"
    assert [column["name"] for column in result["columns"]] == ["id", "product", "password", "size"]
    assert result["rows"] == [
        ["cpu", "Xeon", None, None],
        ["disk", None, "[REDACTED]", 1024],
    ]
    assert result["row_count"] == 2
