"""Item presentation types: declaration checks and artifact consistency."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pg_diag.artifact import item_from_plan, item_type_mismatch
from pg_diag.artifact_schema import ValidationError, _validate_item_payload
from pg_diag.planner import PlannedItem, default_item_type
from pg_diag.validator import _validate_item_types


def _planned(item_type: str | None) -> PlannedItem:
    return PlannedItem(
        item_id="section.item",
        section_id="section",
        item_key="item",
        title="Item",
        source_kind="python",
        status="planned",
        collection_scope="once",
        item_type=item_type,
    )


def test_default_item_type_follows_the_source_manifest() -> None:
    assert default_item_type("query", {"result_shape": "dynamic_table"}) == "table"
    assert default_item_type("script", {"output": "plain_text"}) == "text"
    assert default_item_type("script", {"output": "table_json"}) == "table"
    assert default_item_type("metric", {"chart": {"kind": "line"}}) == "chart"
    assert default_item_type("metric", {"table": {}, "requires_collection": "window_endpoints"}) == "delta"
    assert default_item_type("metric", {"table": {}}) == "table"
    assert default_item_type("python", {}) == "table"


@pytest.mark.parametrize(
    ("item_type", "result", "status", "expect_warning"),
    [
        ("table", {"kind": "table", "rows": [], "columns": [], "row_count": 0}, "empty", False),
        ("table", {"kind": "table", "delta_window": {}}, "ok", True),
        ("delta", {"kind": "table", "delta_window": {}}, "ok", False),
        ("delta", {"kind": "table"}, "ok", False),  # sampler endpoint tables carry no window
        ("chart", {"kind": "chart", "series": []}, "ok", False),
        ("chart", {"kind": "table"}, "ok", True),
        ("text", {"kind": "plain_text", "data": ""}, "ok", False),
        ("text", {"kind": "table"}, "ok", True),
        ("chart", {"kind": "none"}, "unsupported", False),
        (None, {"kind": "table"}, "ok", False),
    ],
)
def test_item_type_mismatch_diagnostic(item_type, result, status, expect_warning) -> None:
    diagnostic = item_type_mismatch(item_type, status, result)
    assert (diagnostic is not None) is expect_warning
    if diagnostic is not None:
        assert diagnostic["code"] == "item_type_mismatch" and diagnostic["level"] == "warning"


def test_item_from_plan_records_type_and_mismatch() -> None:
    item = item_from_plan(_planned("chart"), collection_status="ok", result={"kind": "table"})
    assert item["item_type"] == "chart"
    assert [diagnostic["code"] for diagnostic in item["diagnostics"]] == ["item_type_mismatch"]
    clean = item_from_plan(_planned("table"), collection_status="ok", result={"kind": "table"})
    assert clean["item_type"] == "table" and clean["diagnostics"] == []


def test_artifact_schema_rejects_unknown_item_type() -> None:
    item = item_from_plan(_planned("table"), collection_status="ok", result={"kind": "table", "columns": [], "rows": [], "row_count": 0})
    item["source_metadata"] = {}
    _validate_item_payload("section.item", item, set())
    item["item_type"] = "graph"
    with pytest.raises(ValidationError, match="item_type"):
        _validate_item_payload("section.item", item, set())


def test_validator_rejects_contradicting_item_type_declarations() -> None:
    content = SimpleNamespace(
        queries={"q": {"item_type": "chart"}, "q_ok": {"item_type": "delta"}},
        scripts={"s": {"output": "plain_text", "item_type": "table"}},
        metrics={"m": {"chart": {"kind": "line"}, "item_type": "delta"}, "m_ok": {"table": {}, "item_type": "delta"}},
        pythons={"p": {"item_type": "graph"}, "p_ok": {"item_type": "text"}},
    )
    issues: list = []
    _validate_item_types(content, issues)
    locations = sorted(issue.location for issue in issues)
    assert locations == ["metric:m", "python:p", "query:q", "script:s"]
    assert all(issue.code == "item_type" for issue in issues)
