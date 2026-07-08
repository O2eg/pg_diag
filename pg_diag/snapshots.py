"""Repeated snapshot collection for chart-oriented reports."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from . import runtime_config
from .artifact import (
    create_artifact,
    extract_item_query_texts,
    item_error_from_exception,
    item_from_plan,
    report_output_paths,
    utc_now,
    write_json,
)
from .content_loader import ContentPack
from .executors.common import read_source_text
from .executors.remote_disabled_shell import skipped_python_item, skipped_shell_item
from .executors.python import execute_python_item
from .executors.shell import execute_shell_item
from .executors.sql import connect, detect_runtime_context, execute_query_item
from .metric_engine import build_metric_item
from .os_metrics import collect_os_metrics
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

    conn = await connect(dsn=dsn, **connection_kwargs)
    os_task: asyncio.Task[tuple[dict[str, list[dict[str, Any]]], list[dict[str, str]]]] | None = None
    try:
        runtime_context = await detect_runtime_context(conn)
        server_version_num = int(runtime_context["server_version_num"])
        plan = build_plan(
            content,
            server_version_num,
            mode=runtime_config.SNAPSHOTS_MODE,
            collection_mode=collection_mode,
        )
        started_at = utc_now()
        artifact = create_artifact(content, plan, runtime_context, started_at)
        artifact["runtime"]["duration_seconds"] = duration_seconds
        artifact["runtime"]["interval_seconds"] = interval_seconds

        if collection_mode == runtime_config.LOCAL_COLLECTION_MODE:
            os_task = asyncio.create_task(
                asyncio.to_thread(collect_os_metrics, duration_seconds, interval_seconds)
            )

        sampled_queries = [
            item
            for item in plan.items
            if item.source_kind == "query" and item.status == "planned" and item.collection_scope == "every_snapshot"
        ]
        once_items = [
            item
            for item in plan.items
            if item.status in {"planned", "skipped"}
            and item.source_kind in {"query", "script", "python"}
            and item not in sampled_queries
        ]
        metric_items = [
            item
            for item in plan.items
            if item.source_kind == "metric" and item.status == "planned"
        ]

        snapshots, db_sample_diagnostics = await _collect_db_samples(
            content,
            conn,
            sampled_queries,
            duration_seconds,
            interval_seconds,
        )
        artifact["diagnostics"].extend(db_sample_diagnostics)
        _extract_snapshots_query_texts(artifact, snapshots)
        artifact["snapshots"] = snapshots
        _promote_last_sample_items(artifact, snapshots)

        for planned in once_items:
            try:
                item = await _execute_once_item(
                    content,
                    conn,
                    planned,
                    collection_mode,
                )
                extract_item_query_texts(item, artifact["query_texts"])
                artifact["items"][planned.item_id] = item
            except Exception as exc:
                artifact["items"][planned.item_id] = item_error_from_exception(planned, exc)

        os_samples: dict[str, list[dict[str, Any]]] = {}
        if os_task is not None:
            os_samples, os_errors = await os_task
            for error in os_errors:
                artifact["diagnostics"].append(
                    {"level": "warning", "code": "os_sampler", "message": f"{error['sampler']}: {error['message']}"}
                )

        source_item_by_query = {
            item.source_id: item.item_id
            for item in plan.items
            if item.source_kind == "query" and item.source_id
        }
        source_metadata_by_item = {
            item_id: item.get("source_metadata") or {}
            for item_id, item in artifact["items"].items()
        }
        for planned in metric_items:
            try:
                metric = content.metrics[planned.source_id or ""]
                artifact["items"][planned.item_id] = build_metric_item(
                    planned,
                    metric,
                    snapshots,
                    os_samples,
                    source_item_by_query,
                    source_metadata_by_item,
                )
            except Exception as exc:
                artifact["items"][planned.item_id] = item_error_from_exception(planned, exc)

        for planned in plan.items:
            if planned.item_id not in artifact["items"]:
                artifact["items"][planned.item_id] = item_from_plan(
                    planned,
                    collection_status=planned.status if planned.status != "planned" else "skipped",
                    reason=planned.reason,
                    result={"kind": "none"},
                )

        artifact["runtime"]["finished_at"] = utc_now()
        json_path, html_path = report_output_paths(out_dir, json_out, html_out)
        write_json(json_path, artifact)
        html_text = render_html(artifact)
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(html_text, encoding="utf-8")
        return artifact
    finally:
        if os_task is not None and not os_task.done():
            os_task.cancel()
        await conn.close()


async def _collect_db_samples(
    content: ContentPack,
    conn: Any,
    sampled_queries: list[PlannedItem],
    duration_seconds: float,
    interval_seconds: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sample_count = runtime_config.snapshots_sample_count(duration_seconds, interval_seconds)
    loop = asyncio.get_running_loop()
    start = loop.time()
    snapshots: list[dict[str, Any]] = []
    lagged_samples = 0
    max_lag_seconds = 0.0
    for index in range(sample_count):
        target = start + index * interval_seconds
        delay = target - loop.time()
        if delay > 0:
            await asyncio.sleep(delay)
        lag_seconds = max(loop.time() - target, 0.0)
        if lag_seconds > max(0.1, interval_seconds * 0.25):
            lagged_samples += 1
            max_lag_seconds = max(max_lag_seconds, lag_seconds)
        snapshot = {"timestamp": utc_now(), "items": {}}
        for planned in sampled_queries:
            try:
                item = await execute_query_item(content, conn, planned)
            except Exception as exc:
                item = item_error_from_exception(planned, exc)
            snapshot["items"][planned.item_id] = item
        snapshots.append(snapshot)
    diagnostics = []
    if lagged_samples:
        diagnostics.append(
            {
                "level": "warning",
                "code": "db_sampler_lag",
                "message": (
                    f"DB sampler missed target cadence for {lagged_samples} sample(s); "
                    f"max lag {max_lag_seconds:.3f}s"
                ),
            }
        )
    return snapshots, diagnostics


def _extract_snapshots_query_texts(artifact: dict[str, Any], snapshots: list[dict[str, Any]]) -> None:
    query_texts = artifact["query_texts"]
    for snapshot in snapshots:
        for item in (snapshot.get("items") or {}).values():
            extract_item_query_texts(item, query_texts)


def _promote_last_sample_items(artifact: dict[str, Any], snapshots: list[dict[str, Any]]) -> None:
    target_item_ids = {
        item_id
        for snapshot in snapshots
        for item_id in (snapshot.get("items") or {})
    }
    for snapshot in reversed(snapshots):
        for item_id, item in snapshot.get("items", {}).items():
            if item_id not in artifact["items"]:
                artifact["items"][item_id] = item
        if target_item_ids.issubset(artifact["items"]):
            return


async def _execute_once_item(
    content: ContentPack,
    conn: Any,
    planned: PlannedItem,
    collection_mode: str,
) -> dict[str, Any]:
    if planned.source_kind == "query":
        return await execute_query_item(content, conn, planned)
    if planned.source_kind == "script":
        if collection_mode == runtime_config.REMOTE_DB_ONLY_COLLECTION_MODE:
            message = (content.report.get("runtime_policy") or {}).get(
                "remote_db_only_shell_message", "no data because remote call"
            )
            source_text = (
                read_source_text(content.path / "scripts" / planned.script_file)
                if planned.script_file else None
            )
            return skipped_shell_item(planned, message, source_text=source_text)
        return execute_shell_item(content, planned)
    if planned.source_kind == "python":
        if collection_mode == runtime_config.REMOTE_DB_ONLY_COLLECTION_MODE and (
            content.pythons.get(planned.source_id or "", {}).get("local_only", False)
        ):
            message = (content.report.get("runtime_policy") or {}).get(
                "remote_db_only_shell_message", "no data because remote call"
            )
            source_text = (
                read_source_text(content.path / "python" / planned.python_file)
                if planned.python_file else None
            )
            return skipped_python_item(planned, message, source_text)
        return await execute_python_item(content, conn, planned)
    return item_from_plan(planned, collection_status="skipped", result={"kind": "none"})
