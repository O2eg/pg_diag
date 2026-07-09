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
    write_text_secure,
)
from .content_loader import ContentPack
from .executors.common import read_source_text
from .executors.remote_disabled_shell import skipped_python_item, skipped_shell_item
from .executors.python import execute_python_item
from .executors.shell import execute_shell_item
from .executors.sql import connect, detect_runtime_context, execute_query_item
from .errors import PgDiagError, UnsupportedServerVersion
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

    json_path, html_path = report_output_paths(out_dir, json_out, html_out)
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
        if not plan.supported_server_version:
            raise UnsupportedServerVersion(plan.reason or "Unsupported PostgreSQL server version")
        fail_fast = bool((content.report.get("runtime_policy") or {}).get("fail_fast", False))
        started_at = utc_now()
        artifact = create_artifact(content, plan, runtime_context, started_at)

        for planned in plan.items:
            try:
                if planned.status == "unsupported":
                    artifact["items"][planned.item_id] = item_from_plan(
                        planned,
                        collection_status="unsupported",
                        reason=planned.reason,
                        result={"kind": "none"},
                    )
                elif planned.status == "skipped" and planned.source_kind == "script":
                    source_text = (
                        read_source_text(content.path / "scripts" / planned.script_file)
                        if planned.script_file else None
                    )
                    artifact["items"][planned.item_id] = skipped_shell_item(
                        planned,
                        planned.source_metadata.get("remote_message")
                        or planned.reason
                        or "Collection skipped",
                        source_text=source_text,
                    )
                elif planned.status == "skipped" and planned.source_kind == "python":
                    source_text = (
                        read_source_text(content.path / "python" / planned.python_file)
                        if planned.python_file else None
                    )
                    artifact["items"][planned.item_id] = skipped_python_item(
                        planned,
                        planned.source_metadata.get("remote_message")
                        or planned.reason
                        or "Collection skipped",
                        source_text,
                    )
                elif planned.status == "skipped":
                    artifact["items"][planned.item_id] = item_from_plan(
                        planned,
                        collection_status="skipped",
                        reason=planned.reason,
                        result={"kind": "none"},
                    )
                elif planned.source_kind == "query":
                    artifact["items"][planned.item_id] = await execute_query_item(content, conn, planned)
                elif planned.source_kind == "script":
                    artifact["items"][planned.item_id] = execute_shell_item(content, planned)
                elif planned.source_kind == "python":
                    artifact["items"][planned.item_id] = await execute_python_item(content, conn, planned)
                elif planned.source_kind == "metric":
                    artifact["items"][planned.item_id] = item_from_plan(
                        planned,
                        collection_status="skipped",
                        reason=planned.reason or "requires snapshots mode",
                        result={"kind": "none"},
                    )
                else:
                    artifact["items"][planned.item_id] = item_from_plan(
                        planned,
                        collection_status="error",
                        reason="Unknown source kind",
                        result={"kind": "none"},
                    )
                if fail_fast and artifact["items"][planned.item_id].get("collection_status") == "error":
                    raise PgDiagError(
                        f"fail_fast stopped collection at {planned.item_id}: "
                        f"{artifact['items'][planned.item_id].get('reason') or 'collection error'}"
                    )
                extract_item_query_texts(artifact["items"][planned.item_id], artifact["query_texts"])
            except Exception as exc:
                if isinstance(exc, PgDiagError):
                    raise
                artifact["items"][planned.item_id] = item_error_from_exception(planned, exc)
                if fail_fast:
                    raise PgDiagError(
                        f"fail_fast stopped collection at {planned.item_id}: "
                        f"{artifact['items'][planned.item_id].get('reason') or 'collection error'}"
                    ) from exc

        artifact["runtime"]["finished_at"] = utc_now()
        html_text = render_html(artifact)
        write_text_secure(html_path, html_text)
        write_json(json_path, artifact)
        return artifact
    finally:
        try:
            await conn.close()
        except Exception:
            pass
