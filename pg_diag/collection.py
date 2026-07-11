"""Shared collection lifecycle and report-item execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import runtime_config
from .artifact import (
    apply_database_scope_presentation,
    create_artifact,
    extract_item_query_texts,
    item_error_from_exception,
    item_from_plan,
    report_output_paths,
    utc_now,
    write_json,
    write_text_secure,
)
from .artifact_schema import validate_artifact
from .content_loader import ContentPack
from .errors import PgDiagError, UnsupportedServerVersion
from .executors.common import read_source_text
from .executors.python import execute_python_item
from .executors.remote_disabled_shell import skipped_python_item, skipped_shell_item
from .executors.shell import execute_remote_shell_item, execute_shell_item
from .executors.sql import connect, detect_runtime_context, execute_query_item
from .planner import ExecutionPlan, PlannedItem, build_plan
from .render.html import render_html
from .ssh_transport import (
    SshConfig,
    SshTransport,
    remote_database_endpoint,
    tunneled_connection_kwargs,
)
from .validator import has_errors, validate_content


@dataclass(frozen=True)
class CollectionRun:
    content: ContentPack
    conn: Any
    plan: ExecutionPlan
    artifact: dict[str, Any]
    fail_fast: bool
    json_path: Path
    html_path: Path
    ssh: SshTransport | None = None


async def start_collection(
    *,
    content: ContentPack,
    out_dir: str | Path,
    dsn: str | None,
    connection_kwargs: dict[str, Any],
    mode: str,
    collection_mode: str,
    json_out: str | Path | None,
    html_out: str | Path | None,
    content_validated: bool,
    ssh_config: SshConfig | None = None,
) -> CollectionRun:
    if collection_mode not in runtime_config.COLLECTION_MODES:
        raise ValueError(f"unsupported collection mode {collection_mode!r}")
    if not content_validated:
        issues = validate_content(content)
        if has_errors(issues):
            details = "; ".join(
                f"{issue.location}: {issue.message}"
                for issue in issues
                if issue.level == "error"
            )
            raise ValueError(f"Content validation failed: {details}")

    json_path, html_path = report_output_paths(out_dir, json_out, html_out)
    conn: Any | None = None
    ssh: SshTransport | None = None
    remote_endpoint: tuple[str, int] | None = None
    try:
        effective_connection_kwargs = dict(connection_kwargs)
        if collection_mode == runtime_config.REMOTE_COLLECTION_MODE:
            if ssh_config is None:
                raise ValueError("remote collection requires SSH configuration")
            remote_endpoint = remote_database_endpoint(dsn, effective_connection_kwargs)
            ssh = await SshTransport.connect(ssh_config)
            local_host, local_port = await ssh.open_database_tunnel(*remote_endpoint)
            effective_connection_kwargs = tunneled_connection_kwargs(
                dsn,
                effective_connection_kwargs,
                remote_endpoint,
                (local_host, local_port),
            )
        elif ssh_config is not None:
            raise ValueError("SSH configuration is only valid in remote collection mode")

        conn = await connect(dsn=dsn, **effective_connection_kwargs)
        runtime_context = await detect_runtime_context(conn)
        if ssh is not None and remote_endpoint is not None:
            runtime_context.update(
                {
                    "remote_host": ssh.config.host,
                    "remote_ssh_port": ssh.config.port,
                    "remote_ssh_user": ssh.config.username,
                    "remote_database_host": remote_endpoint[0],
                    "remote_database_port": remote_endpoint[1],
                }
            )
        server_version_num = int(runtime_context["server_version_num"])
        plan = build_plan(
            content,
            server_version_num,
            mode=mode,
            collection_mode=collection_mode,
        )
        if not plan.supported_server_version:
            raise UnsupportedServerVersion(plan.reason or "Unsupported PostgreSQL server version")
        fail_fast = bool((content.report.get("runtime_policy") or {}).get("fail_fast", False))
        artifact = create_artifact(content, plan, runtime_context, utc_now())
        return CollectionRun(
            content=content,
            conn=conn,
            plan=plan,
            artifact=artifact,
            fail_fast=fail_fast,
            json_path=json_path,
            html_path=html_path,
            ssh=ssh,
        )
    except BaseException:
        if conn is not None:
            await close_connection(conn)
        if ssh is not None:
            await ssh.close()
        raise


async def execute_report_item(
    content: ContentPack,
    conn: Any,
    planned: PlannedItem,
    ssh: SshTransport | None = None,
) -> dict[str, Any]:
    if planned.status == "unsupported":
        return item_from_plan(
            planned,
            collection_status="unsupported",
            reason=planned.reason,
            result={"kind": "none"},
        )
    if planned.status == "skipped":
        message = (
            planned.source_metadata.get("remote_message")
            or planned.reason
            or "Collection skipped"
        )
        if planned.source_kind == "script":
            source_text = (
                read_source_text(content.path / "scripts" / planned.script_file)
                if planned.script_file
                else None
            )
            return skipped_shell_item(planned, message, source_text=source_text)
        if planned.source_kind == "python":
            source_text = (
                read_source_text(content.path / "python" / planned.python_file)
                if planned.python_file
                else None
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
        if ssh is not None:
            return await execute_remote_shell_item(content, planned, ssh)
        return execute_shell_item(content, planned)
    if planned.source_kind == "python":
        return await execute_python_item(content, conn, planned, ssh)
    if planned.source_kind == "metric":
        return item_from_plan(
            planned,
            collection_status="skipped",
            reason=planned.reason or "requires snapshots mode",
            result={"kind": "none"},
        )
    return item_from_plan(
        planned,
        collection_status="error",
        reason="Unknown source kind",
        result={"kind": "none"},
    )


async def execute_and_record_report_item(
    run: CollectionRun,
    planned: PlannedItem,
) -> dict[str, Any]:
    try:
        if run.ssh is None:
            item = await execute_report_item(run.content, run.conn, planned)
        else:
            item = await execute_report_item(run.content, run.conn, planned, run.ssh)
        extract_item_query_texts(
            item,
            run.artifact["query_texts"],
            run.content.report["runtime_policy"]["query_text_catalog"],
        )
        run.artifact["items"][planned.item_id] = item
        raise_if_fail_fast(run.fail_fast, item)
        return item
    except Exception as exc:
        if isinstance(exc, PgDiagError):
            raise
        item = item_error_from_exception(planned, exc)
        run.artifact["items"][planned.item_id] = item
        raise_if_fail_fast(run.fail_fast, item, cause=exc)
        return item


def raise_if_fail_fast(
    enabled: bool,
    item: dict[str, Any],
    *,
    cause: BaseException | None = None,
) -> None:
    if not enabled or item.get("collection_status") != "error":
        return
    error = PgDiagError(
        f"fail_fast stopped collection at {item.get('item_id') or '<sample item>'}: "
        f"{item.get('reason') or 'collection error'}"
    )
    if cause is None:
        raise error
    raise error from cause


def finish_collection(
    run: CollectionRun,
    *,
    runtime_updates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if runtime_updates:
        run.artifact["runtime"].update(runtime_updates)
    run.artifact["runtime"]["finished_at"] = utc_now()
    apply_database_scope_presentation(run.artifact)
    validate_artifact(run.artifact)
    html_text = render_html(run.artifact, validate=False)
    write_text_secure(run.html_path, html_text)
    write_json(run.json_path, run.artifact, validate=False)
    return run.artifact


async def close_connection(conn: Any) -> None:
    try:
        await conn.close()
    except Exception:
        pass


async def close_collection(run: CollectionRun) -> None:
    await close_connection(run.conn)
    if run.ssh is not None:
        await run.ssh.close()
