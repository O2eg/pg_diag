"""Trusted Python source executor."""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import sys
import threading
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
    timeout_seconds = _timeout_seconds(content, source)
    try:
        context = PythonSourceContext(
            content=content,
            conn=conn,
            planned=planned,
            source=source,
            source_path=source_path,
        )
        raw_result = await asyncio.wait_for(
            _load_and_call_source(
                source_id,
                source_path,
                source.get("function") or "collect",
                context,
            ),
            timeout=timeout_seconds,
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
    except TimeoutError:
        timeout_ms = int(round(timeout_seconds * 1000))
        message = f"Python source timed out after {timeout_ms} ms"
        return item_from_plan(
            planned,
            collection_status="error",
            reason=message,
            timing_ms=elapsed_ms(started),
            result={"kind": "none"},
            diagnostics=[{"level": "error", "code": "python_timeout", "message": message}],
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


async def _load_and_call_source(
    source_id: str,
    source_path: Path,
    function_name: str,
    context: PythonSourceContext,
) -> Any:
    module = await _run_sync_daemon(_load_module, source_id, source_path)
    function = getattr(module, function_name)
    return await _call_source(function, context)


async def _call_source(function: Any, context: PythonSourceContext) -> Any:
    if inspect.iscoroutinefunction(function):
        return await function(context)
    value = await _run_sync_daemon(function, context)
    if inspect.isawaitable(value):
        return await value
    return value


async def _run_sync_daemon(function: Any, *args: Any) -> Any:
    """Run blocking trusted-source code without pinning the asyncio event loop."""
    loop = asyncio.get_running_loop()
    future: asyncio.Future[Any] = loop.create_future()

    def settle_result(value: Any) -> None:
        if not future.done():
            future.set_result(value)

    def settle_exception(exc: BaseException) -> None:
        if future.done():
            return
        if isinstance(exc, Exception):
            future.set_exception(exc)
        else:
            future.set_exception(RuntimeError(f"Python source terminated: {exc}"))

    def runner() -> None:
        try:
            value = function(*args)
        except BaseException as exc:  # pragma: no cover - defensive plugin boundary
            try:
                loop.call_soon_threadsafe(settle_exception, exc)
            except RuntimeError:
                pass
        else:
            try:
                loop.call_soon_threadsafe(settle_result, value)
            except RuntimeError:
                pass

    threading.Thread(target=runner, name="pg_diag_python_source", daemon=True).start()
    return await future


async def run_blocking(function: Any, *args: Any, **kwargs: Any) -> Any:
    """Run bounded blocking work for an async trusted content source."""
    if kwargs:
        from functools import partial

        function = partial(function, **kwargs)
    return await _run_sync_daemon(function, *args)


def _load_module(source_id: str, source_path: Path) -> Any:
    module_name = "pg_diag_content_python_" + "".join(
        char if char.isalnum() else "_" for char in source_id
    )
    spec = importlib.util.spec_from_file_location(module_name, source_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load Python source file: {source_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    source_dir = str(source_path.parent)
    inserted_path = False
    if source_dir not in sys.path:
        sys.path.insert(0, source_dir)
        inserted_path = True
    try:
        spec.loader.exec_module(module)
    finally:
        if inserted_path:
            try:
                sys.path.remove(source_dir)
            except ValueError:
                pass
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
    if result.reason is not None and not isinstance(result.reason, str):
        raise ValueError("Python source reason must be a string or null")
    kind = result.result.get("kind", "none")
    if kind not in RESULT_KINDS:
        raise ValueError(f"unsupported Python source result kind {kind!r}")
    if not isinstance(result.diagnostics, list) or any(
        not isinstance(diagnostic, dict) for diagnostic in result.diagnostics
    ):
        raise ValueError("Python source diagnostics must be a list of mappings")
    if not isinstance(result.issues, dict):
        raise ValueError("Python source issues must be a mapping")
    if kind == "plain_text" and not isinstance(result.result.get("data", ""), str):
        raise ValueError("Python source plain_text data must be a string")
    if kind == "table":
        columns = result.result.get("columns", [])
        rows = result.result.get("rows", [])
        if not isinstance(columns, list) or not isinstance(rows, list):
            raise ValueError("Python source table columns and rows must be lists")
        if any(
            not isinstance(column, dict)
            or not isinstance(column.get("name"), str)
            or not column["name"]
            for column in columns
        ):
            raise ValueError("Python source table columns must be named mappings")
        if any(not isinstance(row, (list, tuple)) or len(row) != len(columns) for row in rows):
            raise ValueError("Python source table rows must match the column count")
    if kind == "chart":
        series = result.result.get("series", [])
        if not isinstance(series, list) or any(not isinstance(entry, dict) for entry in series):
            raise ValueError("Python source chart series must be a list of mappings")


def table_result(records: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> dict[str, Any]:
    return table_result_from_records(records)


def _timeout_seconds(content: ContentPack, source: dict[str, Any]) -> float:
    defaults = (content.python_catalog.get("python_catalog") or {}).get("defaults") or {}
    timeout_ms = source.get("timeout_ms", defaults.get("timeout_ms", 5000))
    return float(timeout_ms) / 1000.0
