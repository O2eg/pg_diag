"""Repeated snapshot collection for chart-oriented reports."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from . import runtime_config
from .artifact import create_artifact, item_error_from_exception, item_from_plan, utc_now, write_json
from .content_loader import ContentPack
from .executors.remote_disabled_shell import skipped_shell_item
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
    duration_seconds: float = 30.0,
    interval_seconds: float = 5.0,
) -> dict[str, Any]:
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
            if item.status == "planned"
            and item.source_kind in {"query", "script"}
            and item not in sampled_queries
        ]
        metric_items = [
            item
            for item in plan.items
            if item.source_kind == "metric" and item.status == "planned"
        ]

        snapshots = await _collect_db_samples(content, conn, sampled_queries, duration_seconds, interval_seconds)
        artifact["snapshots"] = snapshots
        _promote_last_sample_items(artifact, snapshots)

        for planned in once_items:
            try:
                artifact["items"][planned.item_id] = await _execute_once_item(
                    content,
                    conn,
                    planned,
                    collection_mode,
                )
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
                    status=planned.status if planned.status != "planned" else "skipped",
                    reason=planned.reason,
                    result={"kind": "none"},
                )

        artifact["runtime"]["finished_at"] = utc_now()
        output_dir = Path(out_dir)
        write_json(output_dir / "report.json", artifact)
        html_text = render_html(artifact)
        (output_dir / "report.html").write_text(html_text, encoding="utf-8")
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
) -> list[dict[str, Any]]:
    sample_count = max(1, int(round(duration_seconds / interval_seconds)) + 1)
    loop = asyncio.get_running_loop()
    start = loop.time()
    snapshots: list[dict[str, Any]] = []
    for index in range(sample_count):
        target = start + index * interval_seconds
        delay = target - loop.time()
        if delay > 0:
            await asyncio.sleep(delay)
        snapshot = {"timestamp": utc_now(), "items": {}}
        for planned in sampled_queries:
            try:
                item = await execute_query_item(content, conn, planned)
            except Exception as exc:
                item = item_error_from_exception(planned, exc)
            snapshot["items"][planned.item_id] = item
        snapshots.append(snapshot)
    return snapshots


def _promote_last_sample_items(artifact: dict[str, Any], snapshots: list[dict[str, Any]]) -> None:
    for snapshot in reversed(snapshots):
        for item_id, item in snapshot.get("items", {}).items():
            if item_id not in artifact["items"]:
                artifact["items"][item_id] = item
        if artifact["items"]:
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
                "remote_db_only_shell_message", "no data bacause remote call"
            )
            source_text = None
            if planned.script_file:
                try:
                    source_text = (content.path / "scripts" / planned.script_file).read_text(encoding="utf-8")
                except OSError:
                    source_text = None
            return skipped_shell_item(planned, message, source_text=source_text)
        return execute_shell_item(content, planned)
    return item_from_plan(planned, status="skipped", result={"kind": "none"})
