"""Repeated snapshot collection for chart-oriented reports."""

from __future__ import annotations

import asyncio
from collections import Counter
import threading
from pathlib import Path
from typing import Any

from . import runtime_config
from .artifact import (
    create_artifact,
    compact_snapshot_item,
    extract_item_query_texts,
    item_error_from_exception,
    item_from_plan,
    report_output_paths,
    utc_now,
    write_json,
    write_text_secure,
)
from .content_loader import ContentPack
from .executors.common import read_source_text
from .executors.remote_disabled_shell import skipped_python_item, skipped_shell_item
from .executors.python import execute_python_item
from .executors.shell import execute_shell_item
from .executors.sql import connect, detect_runtime_context, execute_query_item
from .errors import PgDiagError, UnsupportedServerVersion
from .metric_engine import build_metric_item
from .os_metrics import (
    build_backend_proc_window_samples,
    capture_backend_proc_state,
    collect_os_metrics,
)
from .planner import PlannedItem, build_plan
from .render.html import render_html
from .validator import has_errors, validate_content


async def collect_snapshots(
    content: ContentPack,
    out_dir: str | Path,
    dsn: str | None,
    connection_kwargs: dict[str, Any],
    collection_mode: str = runtime_config.LOCAL_COLLECTION_MODE,
    duration_seconds: float = runtime_config.SNAPSHOTS_DEFAULT_DURATION_SECONDS,
    interval_seconds: float = runtime_config.SNAPSHOTS_DEFAULT_INTERVAL_SECONDS,
    json_out: str | Path | None = None,
    html_out: str | Path | None = None,
) -> dict[str, Any]:
    window_error = runtime_config.validate_snapshots_window(duration_seconds, interval_seconds)
    if window_error:
        raise ValueError(window_error)

    issues = validate_content(content)
    if has_errors(issues):
        details = "; ".join(f"{issue.location}: {issue.message}" for issue in issues if issue.level == "error")
        raise ValueError(f"Content validation failed: {details}")

    json_path, html_path = report_output_paths(out_dir, json_out, html_out)
    conn = await connect(dsn=dsn, **connection_kwargs)
    os_task: asyncio.Task[tuple[dict[str, list[dict[str, Any]]], list[dict[str, str]]]] | None = None
    os_stop_event = threading.Event()
    backend_proc_start: dict[str, Any] | None = None
    backend_proc_samples: list[dict[str, Any]] = []
    backend_proc_errors: list[dict[str, str]] = []
    try:
        runtime_context = await detect_runtime_context(conn)
        server_version_num = int(runtime_context["server_version_num"])
        plan = build_plan(
            content,
            server_version_num,
            mode=runtime_config.SNAPSHOTS_MODE,
            collection_mode=collection_mode,
        )
        if not plan.supported_server_version:
            raise UnsupportedServerVersion(plan.reason or "Unsupported PostgreSQL server version")
        fail_fast = bool((content.report.get("runtime_policy") or {}).get("fail_fast", False))
        started_at = utc_now()
        artifact = create_artifact(content, plan, runtime_context, started_at)
        artifact["runtime"]["duration_seconds"] = duration_seconds
        artifact["runtime"]["interval_seconds"] = interval_seconds

        chart_queries = [
            item
            for item in plan.items
            if item.source_kind == "query"
            and item.status == "planned"
            and item.collection_scope == runtime_config.EVERY_SNAPSHOT_COLLECTION_SCOPE
        ]
        endpoint_queries = [
            item
            for item in plan.items
            if item.source_kind == "query"
            and item.status == "planned"
            and item.collection_scope == runtime_config.WINDOW_ENDPOINTS_COLLECTION_SCOPE
        ]
        once_items = [
            item
            for item in plan.items
            if item.status in {"planned", "skipped"}
            and item.source_kind in {"query", "script", "python"}
            and item.collection_scope not in {
                runtime_config.EVERY_SNAPSHOT_COLLECTION_SCOPE,
                runtime_config.WINDOW_ENDPOINTS_COLLECTION_SCOPE,
            }
        ]
        metric_items = [
            item
            for item in plan.items
            if item.source_kind == "metric" and item.status == "planned"
        ]
        artifact["runtime"]["once_item_count"] = len(once_items)
        artifact["runtime"]["chart_queries_per_sample"] = len(chart_queries)
        artifact["runtime"]["window_endpoint_query_count"] = len(endpoint_queries)
        artifact["runtime"]["window_endpoint_sampler_count"] = (
            1 if collection_mode == runtime_config.LOCAL_COLLECTION_MODE else 0
        )

        # Point-in-time tables describe the start of the diagnostic run, not an
        # arbitrary state after the sampling window has already elapsed.
        for planned in once_items:
            try:
                item = await _execute_once_item(
                    content,
                    conn,
                    planned,
                )
                extract_item_query_texts(item, artifact["query_texts"])
                artifact["items"][planned.item_id] = item
                _raise_if_fail_fast(fail_fast, item)
            except Exception as exc:
                if isinstance(exc, PgDiagError):
                    raise
                artifact["items"][planned.item_id] = item_error_from_exception(planned, exc)
                _raise_if_fail_fast(fail_fast, artifact["items"][planned.item_id])

        endpoint_snapshots: list[dict[str, Any]] = []
        endpoint_schemas: dict[str, dict[str, Any]] = {}
        source_latest_items: dict[str, dict[str, Any]] = {}
        if endpoint_queries:
            start_endpoint, endpoint_diagnostics, endpoint_items = await _collect_window_endpoint(
                content,
                conn,
                endpoint_queries,
                phase="start",
                fail_fast=fail_fast,
                query_texts=artifact["query_texts"],
                snapshot_schemas=endpoint_schemas,
            )
            endpoint_snapshots.append(start_endpoint)
            artifact["diagnostics"].extend(endpoint_diagnostics)
            source_latest_items.update(endpoint_items)

        if collection_mode == runtime_config.LOCAL_COLLECTION_MODE:
            try:
                backend_proc_start = await asyncio.to_thread(capture_backend_proc_state)
            except Exception as exc:  # pragma: no cover - host-specific /proc failure
                backend_proc_errors.append(
                    {"sampler": "os.backend_proc", "message": str(exc)}
                )
            os_task = asyncio.create_task(
                asyncio.to_thread(
                    collect_os_metrics,
                    duration_seconds,
                    interval_seconds,
                    os_stop_event,
                )
            )

        artifact["runtime"]["snapshot_window_started_at"] = utc_now()
        snapshots, db_sample_diagnostics, latest_sample_items = await _collect_db_samples(
            content,
            conn,
            chart_queries,
            duration_seconds,
            interval_seconds,
            fail_fast=fail_fast,
            query_texts=artifact["query_texts"],
            snapshot_schemas=artifact["snapshot_schemas"],
        )
        artifact["runtime"]["snapshot_window_finished_at"] = utc_now()
        artifact["diagnostics"].extend(db_sample_diagnostics)
        artifact["snapshots"] = snapshots
        source_latest_items.update(latest_sample_items)

        if backend_proc_start is not None:
            try:
                backend_proc_end = await asyncio.to_thread(capture_backend_proc_state)
                backend_proc_samples = build_backend_proc_window_samples(
                    backend_proc_start,
                    backend_proc_end,
                )
            except Exception as exc:  # pragma: no cover - host-specific /proc failure
                backend_proc_errors.append(
                    {"sampler": "os.backend_proc", "message": str(exc)}
                )

        if endpoint_queries:
            end_endpoint, endpoint_diagnostics, endpoint_items = await _collect_window_endpoint(
                content,
                conn,
                endpoint_queries,
                phase="end",
                fail_fast=fail_fast,
                query_texts=artifact["query_texts"],
                snapshot_schemas=endpoint_schemas,
            )
            endpoint_snapshots.append(end_endpoint)
            artifact["diagnostics"].extend(endpoint_diagnostics)
            source_latest_items.update(endpoint_items)

        os_samples: dict[str, list[dict[str, Any]]] = {}
        os_diagnostics_by_sampler: dict[str, list[dict[str, Any]]] = {}
        os_errors: list[dict[str, str]] = []
        if os_task is not None:
            os_samples, os_errors = await os_task
        if backend_proc_samples:
            os_samples["os.backend_proc"] = backend_proc_samples
        for error in [*os_errors, *backend_proc_errors]:
            diagnostic = {
                "level": "warning",
                "code": "os_sampler",
                "message": f"{error['sampler']}: {error['message']}",
            }
            artifact["diagnostics"].append(diagnostic)
            os_diagnostics_by_sampler.setdefault(error["sampler"], []).append(diagnostic)

        source_item_by_query: dict[str, str] = {}
        for item in plan.items:
            if item.source_kind == "query" and item.source_id:
                if item.source_metadata.get("internal"):
                    source_item_by_query[item.source_id] = item.item_id
                else:
                    source_item_by_query.setdefault(item.source_id, item.item_id)
        source_metadata_by_item = {}
        for source_plan in plan.items:
            item = source_latest_items.get(source_plan.item_id) or artifact["items"].get(source_plan.item_id)
            metadata = dict(
                (item or {}).get("source_metadata")
                or source_plan.source_metadata
                or {}
            )
            metadata["_collection_status"] = (
                item.get("collection_status") if item else source_plan.status
            )
            metadata["_reason"] = item.get("reason") if item else source_plan.reason
            schema = (
                artifact["snapshot_schemas"].get(source_plan.item_id)
                or endpoint_schemas.get(source_plan.item_id)
                or {}
            )
            if schema.get("columns"):
                metadata["_result_columns"] = schema["columns"]
            source_metadata_by_item[source_plan.item_id] = metadata
        metric_snapshots = [*endpoint_snapshots[:1], *snapshots, *endpoint_snapshots[1:]]
        for planned in metric_items:
            try:
                metric = content.metrics[planned.source_id or ""]
                artifact["items"][planned.item_id] = build_metric_item(
                    planned,
                    metric,
                    metric_snapshots,
                    os_samples,
                    source_item_by_query,
                    source_metadata_by_item,
                    os_diagnostics_by_sampler.get(str(metric.get("source_sampler") or ""), []),
                )
                _raise_if_fail_fast(fail_fast, artifact["items"][planned.item_id])
            except Exception as exc:
                if isinstance(exc, PgDiagError):
                    raise
                artifact["items"][planned.item_id] = item_error_from_exception(planned, exc)
                _raise_if_fail_fast(fail_fast, artifact["items"][planned.item_id])

        for planned in plan.items:
            if planned.source_metadata.get("internal"):
                continue
            if planned.item_id not in artifact["items"]:
                artifact["items"][planned.item_id] = item_from_plan(
                    planned,
                    collection_status=planned.status if planned.status != "planned" else "skipped",
                    reason=planned.reason,
                    result={"kind": "none"},
                )

        artifact["runtime"]["finished_at"] = utc_now()
        artifact["runtime"]["snapshot_count"] = len(snapshots)
        html_text = render_html(artifact)
        write_text_secure(html_path, html_text)
        write_json(json_path, artifact)
        return artifact
    finally:
        os_stop_event.set()
        if os_task is not None and not os_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(os_task), timeout=5.0)
            except (TimeoutError, asyncio.CancelledError):
                os_task.cancel()
        try:
            await conn.close()
        except Exception:
            pass


async def _collect_db_samples(
    content: ContentPack,
    conn: Any,
    sampled_queries: list[PlannedItem],
    duration_seconds: float,
    interval_seconds: float,
    *,
    fail_fast: bool = False,
    query_texts: dict[str, str] | None = None,
    snapshot_schemas: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    schedule_offsets = runtime_config.snapshots_schedule_offsets(duration_seconds, interval_seconds)
    loop = asyncio.get_running_loop()
    start = loop.time()
    deadline = start + duration_seconds
    snapshots: list[dict[str, Any]] = []
    latest_items: dict[str, dict[str, Any]] = {}
    sample_error_counts: Counter[str] = Counter()
    lagged_samples = 0
    skipped_samples = 0
    max_lag_seconds = 0.0
    lag_tolerance = max(0.1, min(interval_seconds * 0.25, 1.0))
    for index, offset in enumerate(schedule_offsets):
        target = start + offset
        delay = target - loop.time()
        if delay > 0:
            await asyncio.sleep(delay)
        lag_seconds = max(loop.time() - target, 0.0)
        if index > 0 and loop.time() > deadline + lag_tolerance:
            skipped_samples += 1
            continue
        if index > 0 and lag_seconds > lag_tolerance:
            lagged_samples += 1
            max_lag_seconds = max(max_lag_seconds, lag_seconds)
            skipped_samples += 1
            continue
        snapshot = {"timestamp": utc_now(), "items": {}}
        for planned in sampled_queries:
            try:
                item = await execute_query_item(content, conn, planned)
            except Exception as exc:
                item = item_error_from_exception(planned, exc)
            if query_texts is not None:
                extract_item_query_texts(item, query_texts)
            result = item.get("result") or {}
            if (
                snapshot_schemas is not None
                and result.get("kind") == "table"
                and result.get("columns")
            ):
                snapshot_schemas.setdefault(
                    planned.item_id,
                    {"columns": result["columns"]},
                )
            latest_items[planned.item_id] = item
            snapshot["items"][planned.item_id] = compact_snapshot_item(item)
            if item.get("collection_status") == "error":
                sample_error_counts[planned.item_id] += 1
            _raise_if_fail_fast(fail_fast, item)
        snapshots.append(snapshot)
    diagnostics = []
    if lagged_samples or skipped_samples:
        diagnostics.append(
            {
                "level": "warning",
                "code": "db_sampler_lag",
                "message": (
                    f"DB sampler skipped {skipped_samples} stale sample(s); "
                    f"max lag {max_lag_seconds:.3f}s"
                ),
            }
        )
    if sample_error_counts:
        details = ", ".join(
            f"{item_id}={count}" for item_id, count in sorted(sample_error_counts.items())
        )
        diagnostics.append(
            {
                "level": "error",
                "code": "db_sample_errors",
                "message": f"Repeated DB sample errors: {details}",
            }
        )
    return snapshots, diagnostics, latest_items


async def _collect_window_endpoint(
    content: ContentPack,
    conn: Any,
    endpoint_queries: list[PlannedItem],
    *,
    phase: str,
    fail_fast: bool = False,
    query_texts: dict[str, str] | None = None,
    snapshot_schemas: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    snapshot, items, error_counts = await _execute_query_batch(
        content,
        conn,
        endpoint_queries,
        fail_fast=fail_fast,
        query_texts=query_texts,
        snapshot_schemas=snapshot_schemas,
    )
    diagnostics: list[dict[str, Any]] = []
    if error_counts:
        details = ", ".join(
            f"{item_id}={count}" for item_id, count in sorted(error_counts.items())
        )
        diagnostics.append(
            {
                "level": "error",
                "code": "db_window_endpoint_errors",
                "message": f"Window {phase} endpoint errors: {details}",
            }
        )
    return snapshot, diagnostics, items


async def _execute_query_batch(
    content: ContentPack,
    conn: Any,
    queries: list[PlannedItem],
    *,
    fail_fast: bool = False,
    query_texts: dict[str, str] | None = None,
    snapshot_schemas: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], Counter[str]]:
    snapshot = {"timestamp": utc_now(), "items": {}}
    items: dict[str, dict[str, Any]] = {}
    error_counts: Counter[str] = Counter()
    for planned in queries:
        try:
            item = await execute_query_item(content, conn, planned)
        except Exception as exc:
            item = item_error_from_exception(planned, exc)
        if query_texts is not None:
            extract_item_query_texts(item, query_texts)
        result = item.get("result") or {}
        if (
            snapshot_schemas is not None
            and result.get("kind") == "table"
            and result.get("columns")
        ):
            snapshot_schemas.setdefault(
                planned.item_id,
                {"columns": result["columns"]},
            )
        items[planned.item_id] = item
        snapshot["items"][planned.item_id] = compact_snapshot_item(item)
        if item.get("collection_status") == "error":
            error_counts[planned.item_id] += 1
        _raise_if_fail_fast(fail_fast, item)
    return snapshot, items, error_counts


async def _execute_once_item(
    content: ContentPack,
    conn: Any,
    planned: PlannedItem,
) -> dict[str, Any]:
    if planned.status == "skipped":
        message = planned.source_metadata.get("remote_message") or planned.reason or "Collection skipped"
        if planned.source_kind == "script":
            source_text = (
                read_source_text(content.path / "scripts" / planned.script_file)
                if planned.script_file else None
            )
            return skipped_shell_item(planned, message, source_text=source_text)
        if planned.source_kind == "python":
            source_text = (
                read_source_text(content.path / "python" / planned.python_file)
                if planned.python_file else None
            )
            return skipped_python_item(planned, message, source_text=source_text)
        return item_from_plan(
            planned,
            collection_status="skipped",
            reason=planned.reason,
            result={"kind": "none"},
        )
    if planned.source_kind == "query":
        return await execute_query_item(content, conn, planned)
    if planned.source_kind == "script":
        return execute_shell_item(content, planned)
    if planned.source_kind == "python":
        return await execute_python_item(content, conn, planned)
    return item_from_plan(planned, collection_status="skipped", result={"kind": "none"})


def _raise_if_fail_fast(enabled: bool, item: dict[str, Any]) -> None:
    if enabled and item.get("collection_status") == "error":
        raise PgDiagError(
            f"fail_fast stopped collection at {item.get('item_id') or '<sample item>'}: "
            f"{item.get('reason') or 'collection error'}"
        )
