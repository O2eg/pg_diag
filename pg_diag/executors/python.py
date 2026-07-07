"""Trusted Python source executor."""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pg_diag.artifact import item_error_from_exception, item_from_plan
from pg_diag.content_loader import ContentPack
from pg_diag.planner import PlannedItem
from pg_diag.security import json_safe, redact_row


@dataclass(frozen=True)
class PythonSourceContext:
    content: ContentPack
    conn: Any
    planned: PlannedItem
    source: dict[str, Any]
    source_path: Path


@dataclass
class PythonSourceResult:
    collection_status: str
    result: dict[str, Any] = field(default_factory=lambda: {"kind": "none"})
    reason: str | None = None
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    issues: dict[str, Any] = field(default_factory=dict)
    severity_level: str | None = None


async def execute_python_item(content: ContentPack, conn: Any, planned: PlannedItem) -> dict[str, Any]:
    started = time.perf_counter()
    source_id = planned.source_id or ""
    source = content.pythons.get(source_id) or {}
    python_file = source.get("python_file")
    if not python_file:
        return item_from_plan(
            planned,
            collection_status="error",
            reason="python_file is missing",
            result={"kind": "none"},
        )

    source_path = content.path / "python" / python_file
    source_text = _read_source_text(source_path)
    try:
        module = _load_module(source_id, source_path)
        function_name = source.get("function") or "collect"
        function = getattr(module, function_name)
        context = PythonSourceContext(
            content=content,
            conn=conn,
            planned=planned,
            source=source,
            source_path=source_path,
        )
        raw_result = await asyncio.wait_for(
            _call_source(function, context),
            timeout=_timeout_seconds(content, source),
        )
        result = _normalize_result(raw_result)
        return item_from_plan(
            planned,
            collection_status=result.collection_status,
            reason=result.reason,
            timing_ms=_elapsed_ms(started),
            result=result.result,
            diagnostics=result.diagnostics,
            issues=result.issues,
            severity_level=result.severity_level,
            source_text=source_text,
            source_language="python",
        )
    except Exception as exc:
        return item_error_from_exception(
            planned,
            exc,
            timing_ms=_elapsed_ms(started),
            source_text=source_text,
            source_language="python",
        )


async def _call_source(function: Any, context: PythonSourceContext) -> Any:
    value = function(context)
    if inspect.isawaitable(value):
        return await value
    return value


def _load_module(source_id: str, source_path: Path) -> Any:
    module_name = "pg_diag_content_python_" + "".join(
        char if char.isalnum() else "_" for char in source_id
    )
    spec = importlib.util.spec_from_file_location(module_name, source_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load Python source file: {source_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _normalize_result(value: Any) -> PythonSourceResult:
    if isinstance(value, PythonSourceResult):
        return value
    if isinstance(value, dict):
        if "collection_status" not in value:
            raise ValueError("Python source result must define collection_status")
        return PythonSourceResult(
            collection_status=str(value.get("collection_status")),
            reason=value.get("reason"),
            result=value.get("result") or {"kind": "none"},
            diagnostics=list(value.get("diagnostics") or []),
            issues=dict(value.get("issues") or {}),
            severity_level=value.get("severity_level"),
        )
    raise TypeError("Python source must return PythonSourceResult or dict")


def table_result(records: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> dict[str, Any]:
    normalized_records = [record if isinstance(record, dict) else {"value": record} for record in records]
    columns = _columns_from_records(normalized_records)
    rows = [_row_from_record(columns, record) for record in normalized_records]
    return {"kind": "table", "columns": columns, "rows": rows, "row_count": len(rows)}


def _columns_from_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    columns: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        for key in record:
            name = str(key)
            if name in seen:
                continue
            seen.add(name)
            columns.append({"name": name, "pg_type": "json", "pg_type_oid": None})
    return columns


def _row_from_record(columns: list[dict[str, Any]], record: dict[str, Any]) -> list[Any]:
    row = [json_safe(record.get(column["name"])) for column in columns]
    return redact_row(columns, row)


def _timeout_seconds(content: ContentPack, source: dict[str, Any]) -> float:
    defaults = (content.python_catalog.get("python_catalog") or {}).get("defaults") or {}
    timeout_ms = source.get("timeout_ms", defaults.get("timeout_ms", 5000))
    return float(timeout_ms) / 1000.0


def _read_source_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)
