"""Snapshot collection orchestration."""

from __future__ import annotations

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
from .executors.remote_disabled_shell import skipped_shell_item
from .executors.shell import execute_shell_item
from .executors.sql import connect, detect_runtime_context, execute_query_item
from .planner import build_plan
from .render.html import render_html
from .validator import has_errors, validate_content


async def collect_snapshot(
    content: ContentPack,
    out_dir: str | Path,
    dsn: str | None,
    connection_kwargs: dict[str, Any],
    collection_mode: str = runtime_config.DEFAULT_COLLECTION_MODE,
    json_out: str | Path | None = None,
    html_out: str | Path | None = None,
) -> dict[str, Any]:
    issues = validate_content(content)
    if has_errors(issues):
        details = "; ".join(f"{issue.location}: {issue.message}" for issue in issues if issue.level == "error")
        raise ValueError(f"Content validation failed: {details}")

    conn = await connect(dsn=dsn, **connection_kwargs)
    try:
        runtime_context = await detect_runtime_context(conn)
        server_version_num = int(runtime_context["server_version_num"])
        plan = build_plan(
            content,
            server_version_num,
            mode=runtime_config.SNAPSHOT_MODE,
            collection_mode=collection_mode,
        )
        started_at = utc_now()
        artifact = create_artifact(content, plan, runtime_context, started_at)

        for planned in plan.items:
            try:
                if planned.status == "unsupported":
                    artifact["items"][planned.item_id] = item_from_plan(
                        planned,
                        status="unsupported",
                        reason=planned.reason,
                        result={"kind": "none"},
                    )
                elif planned.source_kind == "query":
                    artifact["items"][planned.item_id] = await execute_query_item(content, conn, planned)
                elif planned.source_kind == "script":
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
                        artifact["items"][planned.item_id] = skipped_shell_item(planned, message, source_text=source_text)
                    else:
                        artifact["items"][planned.item_id] = execute_shell_item(content, planned)
                elif planned.source_kind == "metric":
                    artifact["items"][planned.item_id] = item_from_plan(
                        planned,
                        status="skipped",
                        reason="requires snapshots mode",
                        result={"kind": "none"},
                    )
                else:
                    artifact["items"][planned.item_id] = item_from_plan(
                        planned,
                        status="error",
                        reason="Unknown source kind",
                        result={"kind": "none"},
                    )
                extract_item_query_texts(artifact["items"][planned.item_id], artifact["query_texts"])
            except Exception as exc:
                artifact["items"][planned.item_id] = item_error_from_exception(planned, exc)

        artifact["runtime"]["finished_at"] = utc_now()
        json_path, html_path = report_output_paths(out_dir, json_out, html_out)
        write_json(json_path, artifact)
        html_text = render_html(artifact)
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(html_text, encoding="utf-8")
        return artifact
    finally:
        await conn.close()
