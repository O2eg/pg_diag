"""Trusted Python source executor."""

from __future__ import annotations

import asyncio
from hashlib import sha256
import importlib.util
import inspect
import multiprocessing
import os
import pickle
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

from pg_diag.artifact import item_error_from_exception, item_from_plan
from pg_diag.content_loader import ContentPack
from pg_diag.contracts import COLLECTION_STATUSES, RESULT_KINDS, SEVERITY_LEVELS
from pg_diag.errors import CommandTimeoutError
from pg_diag.executors.common import elapsed_ms, read_source_text, table_result_from_records
from pg_diag.host_access import HostAccess, LocalHostAccess
from pg_diag.planner import PlannedItem

if TYPE_CHECKING:
    from pg_diag.executors.sql import DatabaseConnector
    from pg_diag.ssh_transport import SshTransport


_MODULE_LOAD_LOCK = threading.RLock()
_MISSING_MODULE = object()


@dataclass(frozen=True)
class PythonSourceContext:
    content: ContentPack
    conn: Any
    planned: PlannedItem
    source: dict[str, Any]
    source_path: Path
    host: HostAccess
    database_connector: DatabaseConnector | None = None

    def connect_database(
        self,
        database_name: str,
        *,
        timeout_seconds: float | None = None,
    ) -> Any:
        if self.database_connector is None:
            raise RuntimeError("Python source database connector is unavailable")
        return self.database_connector.connect(
            database_name,
            timeout_seconds=timeout_seconds,
        )


@dataclass
class PythonSourceResult:
    collection_status: str
    result: dict[str, Any] = field(default_factory=lambda: {"kind": "none"})
    reason: str | None = None
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    issues: dict[str, Any] = field(default_factory=dict)
    severity_level: str | None = None


async def execute_python_item(
    content: ContentPack,
    conn: Any,
    planned: PlannedItem,
    ssh_transport: SshTransport | None = None,
    database_connector: DatabaseConnector | None = None,
) -> dict[str, Any]:
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
        host: HostAccess = (
            ssh_transport.host_access if ssh_transport is not None else LocalHostAccess()
        )
        context = PythonSourceContext(
            content=content,
            conn=conn,
            planned=planned,
            source=source,
            source_path=source_path,
            host=host,
            database_connector=database_connector,
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
    except (TimeoutError, CommandTimeoutError):
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
    module = _load_module(source_id, source_path)
    function = getattr(module, function_name)
    return await _call_source(function, context)


async def _call_source(function: Any, context: PythonSourceContext) -> Any:
    if inspect.iscoroutinefunction(function):
        return await function(context)
    return await _run_sync_process(function, context)


def _sync_process_entry(send_conn: Any, function: Any, args: tuple[Any, ...]) -> None:
    try:
        os.setsid()
    except OSError:
        pass
    try:
        value = function(*args)
        if inspect.isawaitable(value):
            value = asyncio.run(value)
        payload = ("ok", value)
    except BaseException as exc:  # pragma: no cover - defensive plugin boundary
        payload = ("error", type(exc).__name__, str(exc))
    try:
        send_conn.send_bytes(pickle.dumps(payload))
    except BaseException as exc:  # pragma: no cover - unpicklable plugin result
        error_payload = ("error", type(exc).__name__, f"Cannot return Python source result: {exc}")
        try:
            send_conn.send_bytes(pickle.dumps(error_payload))
        except BaseException:
            pass
    finally:
        send_conn.close()


async def _run_sync_process(function: Any, *args: Any) -> Any:
    """Run blocking trusted-source code in a process that can be terminated."""
    try:
        context = multiprocessing.get_context("fork")
    except ValueError as exc:  # pragma: no cover - pg_diag local mode targets Linux
        raise RuntimeError("Killable Python source execution requires multiprocessing fork") from exc

    recv_conn, send_conn = context.Pipe(duplex=False)
    process = context.Process(
        target=_sync_process_entry,
        args=(send_conn, function, args),
        name="pg_diag_python_source",
    )
    process.start()
    send_conn.close()
    loop = asyncio.get_running_loop()
    readable = loop.create_future()

    def mark_readable() -> None:
        if not readable.done():
            readable.set_result(None)

    loop.add_reader(recv_conn.fileno(), mark_readable)
    try:
        await readable
        raw_payload = recv_conn.recv_bytes()
    except BaseException:
        _terminate_process_group(process)
        raise
    finally:
        loop.remove_reader(recv_conn.fileno())
        recv_conn.close()
        process.join(0.2)
        if process.is_alive():
            _terminate_process_group(process, force=True)
            process.join(0.2)

    status, *payload = pickle.loads(raw_payload)
    if status == "ok":
        return payload[0]
    error_type, message = payload
    raise RuntimeError(f"Python source process failed ({error_type}): {message}")


def _terminate_process_group(process: Any, *, force: bool = False) -> None:
    if not process.is_alive():
        return
    terminate_signal = signal.SIGKILL if force else signal.SIGTERM
    try:
        os.killpg(process.pid, terminate_signal)
    except OSError:
        if force:
            process.kill()
        else:
            process.terminate()


async def run_blocking(function: Any, *args: Any, **kwargs: Any) -> Any:
    """Run blocking work outside the collector process so cancellation can stop it."""
    if kwargs:
        from functools import partial

        function = partial(function, **kwargs)
    return await _run_sync_process(function, *args)


def _load_module(source_id: str, source_path: Path) -> Any:
    path_digest = sha256(str(source_path.resolve()).encode("utf-8")).hexdigest()[:16]
    module_name = "pg_diag_content_python_" + path_digest + "_" + "".join(
        char if char.isalnum() else "_" for char in source_id
    )
    source_dir = str(source_path.parent)
    local_module_names = {
        path.stem
        for path in source_path.parent.glob("*.py")
        if path.name != "__init__.py"
    }

    with _MODULE_LOAD_LOCK:
        previous_modules = {
            name: sys.modules.get(name, _MISSING_MODULE)
            for name in local_module_names
        }
        for name in local_module_names:
            sys.modules.pop(name, None)
        sys.path.insert(0, source_dir)
        try:
            spec = importlib.util.spec_from_file_location(module_name, source_path)
            if spec is None or spec.loader is None:
                raise RuntimeError(f"Cannot load Python source file: {source_path}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(module_name, None)
            raise
        finally:
            try:
                sys.path.remove(source_dir)
            except ValueError:
                pass
            for name, previous in previous_modules.items():
                sys.modules.pop(name, None)
                if previous is not _MISSING_MODULE:
                    sys.modules[name] = previous
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
    return float(source["timeout_ms"]) / 1000.0
