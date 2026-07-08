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
from pg_diag.executors.common import elapsed_ms, read_source_text, table_result_from_records
from pg_diag.planner import PlannedItem


COLLECTION_STATUSES = {"ok", "empty", "error", "unsupported", "skipped"}
RESULT_KINDS = {"none", "plain_text", "table", "chart"}
SEVERITY_LEVELS = {"high", "medium", "ok", "unknown"}


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
    source_text = read_source_text(source_path)
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
            timing_ms=elapsed_ms(started),
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
            timing_ms=elapsed_ms(started),
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
        result = value
        _validate_result_contract(result)
        return result
    if isinstance(value, dict):
        if "collection_status" not in value:
            raise ValueError("Python source result must define collection_status")
        result = PythonSourceResult(
            collection_status=str(value.get("collection_status")),
            reason=value.get("reason"),
            result=value.get("result") or {"kind": "none"},
            diagnostics=list(value.get("diagnostics") or []),
            issues=dict(value.get("issues") or {}),
            severity_level=value.get("severity_level"),
        )
        _validate_result_contract(result)
        return result
    raise TypeError("Python source must return PythonSourceResult or dict")


def _validate_result_contract(result: PythonSourceResult) -> None:
    if result.collection_status not in COLLECTION_STATUSES:
        raise ValueError(f"unsupported Python source collection_status {result.collection_status!r}")
    if result.severity_level is not None and result.severity_level not in SEVERITY_LEVELS:
        raise ValueError(f"unsupported Python source severity_level {result.severity_level!r}")
    if not isinstance(result.result, dict):
        raise ValueError("Python source result must be a mapping")
    kind = result.result.get("kind", "none")
    if kind not in RESULT_KINDS:
        raise ValueError(f"unsupported Python source result kind {kind!r}")
    if not isinstance(result.diagnostics, list):
        raise ValueError("Python source diagnostics must be a list")
    if not isinstance(result.issues, dict):
        raise ValueError("Python source issues must be a mapping")


def table_result(records: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> dict[str, Any]:
    return table_result_from_records(records)


def _timeout_seconds(content: ContentPack, source: dict[str, Any]) -> float:
    defaults = (content.python_catalog.get("python_catalog") or {}).get("defaults") or {}
    timeout_ms = source.get("timeout_ms", defaults.get("timeout_ms", 5000))
    return float(timeout_ms) / 1000.0
