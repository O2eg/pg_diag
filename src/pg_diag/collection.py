"""Shared collection lifecycle and report-item execution."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
import ipaddress
from pathlib import Path
import socket
from typing import Any

from . import runtime_config
from .artifact import (
    apply_database_scope_presentation,
    create_artifact,
    extract_item_query_texts,
    item_error_from_exception,
    item_from_plan,
    omit_skipped_report_items,
    report_output_paths,
    strip_artifact_metadata,
    utc_now,
    write_json,
    write_text_secure,
)
from .artifact_schema import validate_artifact
from .content_loader import ContentPack
from .object_ddl import collect_object_ddl
from .errors import (
    DatabaseIdentityChangedError,
    DatabaseUnavailableError,
    PgDiagError,
    UnsupportedServerVersion,
)
from .executors.common import read_source_text
from .executors.python import execute_python_item
from .executors.remote_disabled_shell import skipped_python_item, skipped_shell_item
from .executors.shell import execute_remote_shell_item, execute_shell_item
from .executors.sql import DatabaseConnector, connect, detect_runtime_context, execute_query_item, runtime_guard_server_settings
from .host_access import LocalHostAccess
from .planner import (
    ExecutionPlan,
    PlannedItem,
    build_plan,
    collection_requirements,
    normalize_requested_item_ids,
    normalize_requested_tags,
)
from .presentation import apply_presentation_contract
from .progress import ProgressReporter
from .render.html import render_html
from .security import redact_error
from .ssh_transport import (
    SshConfig,
    SshTransport,
    database_connection_host,
    remote_database_endpoint,
    tunneled_connection_kwargs,
)
from .validator import has_errors, validate_content


@dataclass
class CollectionRun:
    content: ContentPack
    conn: Any | None
    plan: ExecutionPlan
    artifact: dict[str, Any]
    fail_fast: bool
    json_path: Path | None
    html_path: Path | None
    database_connector: DatabaseConnector | None
    database_identity: dict[str, Any] | None = None
    ssh: SshTransport | None = None
    progress: ProgressReporter | None = None


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
    output_formats: str | Iterable[str] | None,
    content_validated: bool,
    ssh_config: SshConfig | None = None,
    item_id: str | Iterable[str] | None = None,
    tags: Iterable[str] | None = None,
    progress: ProgressReporter | None = None,
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
    if item_id is not None and tags is not None:
        raise ValueError("--item-id and --tags cannot be used together")
    requested_item_ids = normalize_requested_item_ids(content, item_id)
    requested_tags = normalize_requested_tags(content, tags)
    requirements = collection_requirements(
        content,
        mode=mode,
        collection_mode=collection_mode,
        item_id=requested_item_ids,
        tags=requested_tags,
    )

    json_path, html_path = report_output_paths(out_dir, json_out, html_out, output_formats)
    conn: Any | None = None
    ssh: SshTransport | None = None
    database_connector: DatabaseConnector | None = None
    database_identity: dict[str, Any] | None = None
    remote_endpoint: tuple[str, int] | None = None
    try:
        effective_connection_kwargs = dict(connection_kwargs)
        if collection_mode == runtime_config.REMOTE_COLLECTION_MODE:
            if requirements.requires_ssh(collection_mode) and ssh_config is None:
                raise ValueError("remote collection requires SSH configuration")
            if requirements.requires_ssh(collection_mode):
                assert ssh_config is not None
                ssh = await SshTransport.connect(ssh_config)
            if requirements.requires_database:
                remote_endpoint = remote_database_endpoint(dsn, effective_connection_kwargs)
                assert ssh is not None
                local_host, local_port = await ssh.open_database_tunnel(*remote_endpoint)
                effective_connection_kwargs = tunneled_connection_kwargs(
                    dsn,
                    effective_connection_kwargs,
                    remote_endpoint,
                    (local_host, local_port),
                )
        elif ssh_config is not None:
            raise ValueError("SSH configuration is only valid in remote collection mode")

        runtime_context: dict[str, Any] = {
            "targets": list(requirements.targets),
            "database_connected": requirements.requires_database,
        }
        server_version_num: int | None = None
        if requirements.requires_database:
            guard_settings = runtime_guard_server_settings(content)
            existing_server_settings = effective_connection_kwargs.get("server_settings")
            if isinstance(existing_server_settings, dict):
                guard_settings = {**guard_settings, **existing_server_settings}
            effective_connection_kwargs["server_settings"] = guard_settings

            conn = await connect(dsn=dsn, **effective_connection_kwargs)
            database_connector = DatabaseConnector(dsn, effective_connection_kwargs)
            database_identity = await detect_runtime_context(conn)
            runtime_context.update(database_identity)
            await _populate_database_identity(
                runtime_context,
                collection_mode=collection_mode,
                dsn=dsn,
                connection_kwargs=connection_kwargs,
                ssh=ssh,
            )
            server_version_num = int(runtime_context["server_version_num"])
        if ssh is not None:
            runtime_context.update(
                {
                    "remote_host": ssh.config.host,
                    "remote_ssh_port": ssh.config.port,
                    "remote_ssh_user": ssh.config.username,
                }
            )
            if remote_endpoint is not None:
                runtime_context.update(
                    {
                        "remote_database_host": remote_endpoint[0],
                        "remote_database_port": remote_endpoint[1],
                    }
                )
        plan = build_plan(
            content,
            server_version_num,
            mode=mode,
            collection_mode=collection_mode,
            item_id=requested_item_ids,
            tags=requested_tags,
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
            database_connector=database_connector,
            database_identity=database_identity,
            ssh=ssh,
            progress=progress,
        )
    except BaseException:
        if conn is not None:
            await close_connection(conn)
        if ssh is not None:
            await ssh.close()
        raise


async def _populate_database_identity(
    runtime_context: dict[str, Any],
    *,
    collection_mode: str,
    dsn: str | None,
    connection_kwargs: dict[str, Any],
    ssh: SshTransport | None,
) -> None:
    database_name = runtime_context["current_database"]
    in_recovery = bool(runtime_context["in_recovery"])
    runtime_context["database_name"] = database_name
    runtime_context["database_role"] = "Secondary" if in_recovery else "Primary"

    if collection_mode == runtime_config.REMOTE_COLLECTION_MODE:
        if ssh is None:
            raise PgDiagError("remote collection has no SSH transport for database identity")
        runtime_context["database_host_ip"] = ssh.peer_ip
        runtime_context["database_hostname"] = await ssh.host_access.hostname()
        return

    if collection_mode == runtime_config.LOCAL_COLLECTION_MODE:
        runtime_context["database_hostname"] = await LocalHostAccess().hostname()
    else:
        endpoint = database_connection_host(dsn, connection_kwargs)
        runtime_context["database_hostname"] = await _endpoint_hostname(
            endpoint or runtime_context.get("database_host_ip")
        )

    if not runtime_context.get("database_host_ip"):
        runtime_context["database_host_ip"] = "local socket"


async def _endpoint_hostname(value: Any) -> str:
    endpoint = str(value or "").strip()
    if not endpoint:
        return "unknown"
    try:
        ipaddress.ip_address(endpoint.strip("[]"))
    except ValueError:
        return endpoint
    try:
        hostname = await asyncio.wait_for(
            asyncio.to_thread(socket.getfqdn, endpoint),
            timeout=runtime_config.HOST_COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, asyncio.TimeoutError, TimeoutError):
        return endpoint
    return hostname or endpoint


async def execute_report_item(
    content: ContentPack,
    conn: Any,
    planned: PlannedItem,
    ssh: SshTransport | None = None,
    database_connector: DatabaseConnector | None = None,
    server_log: Any = None,
) -> dict[str, Any]:
    primary_item = await _execute_source_item(
        content,
        conn,
        planned,
        ssh,
        database_connector,
        server_log,
    )
    trigger = _fallback_trigger(primary_item, planned.fallback_on)
    if trigger is None or planned.fallback_item is None:
        return primary_item
    fallback_item = await _execute_source_item(
        content,
        conn,
        planned.fallback_item,
        ssh,
        database_connector,
        server_log,
    )
    return _replace_with_fallback_item(
        planned,
        primary_item,
        planned.fallback_item,
        fallback_item,
        trigger,
    )


async def _execute_source_item(
    content: ContentPack,
    conn: Any,
    planned: PlannedItem,
    ssh: SshTransport | None,
    database_connector: DatabaseConnector | None,
    server_log: Any = None,
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
        return await execute_python_item(
            content,
            conn,
            planned,
            ssh,
            database_connector,
            server_log=server_log,
        )
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


def _fallback_trigger(item: dict[str, Any], allowed: tuple[str, ...]) -> str | None:
    if item.get("collection_status") != "error" or not allowed:
        return None
    allowed_set = set(allowed)
    for diagnostic in item.get("diagnostics") or []:
        if not isinstance(diagnostic, dict):
            continue
        failure_kind = diagnostic.get("failure_kind")
        if isinstance(failure_kind, str) and failure_kind in allowed_set:
            return failure_kind
        code = diagnostic.get("code")
        if isinstance(code, str) and code in allowed_set:
            return code
    return None


def _replace_with_fallback_item(
    parent_plan: PlannedItem,
    primary_item: dict[str, Any],
    fallback_plan: PlannedItem,
    fallback_item: dict[str, Any],
    trigger: str,
) -> dict[str, Any]:
    primary_timing_ms = _numeric_timing(primary_item.get("timing_ms"))
    fallback_timing_ms = _numeric_timing(fallback_item.get("timing_ms"))
    fallback_metadata = dict(fallback_item.get("source_metadata") or {})
    parent_metadata = primary_item.get("source_metadata") or {}
    parent_tags = parent_metadata.get("tags")
    if isinstance(parent_tags, list):
        fallback_metadata["tags"] = list(parent_tags)
    fallback_metadata["fallback"] = {
        "used": True,
        "trigger": trigger,
        "on": list(parent_plan.fallback_on),
        "parent_item_id": parent_plan.item_id,
        "parent_title": parent_plan.title,
        "fallback_item_id": fallback_plan.item_id,
        "effective_item_id": fallback_plan.item_id,
        "primary_source_kind": parent_plan.source_kind,
        "primary_source_id": parent_plan.source_id,
        "primary_reason": primary_item.get("reason"),
        "primary_timing_ms": primary_timing_ms,
        "fallback_timing_ms": fallback_timing_ms,
        "primary_diagnostics": primary_item.get("diagnostics") or [],
    }
    fallback_diagnostics = list(fallback_item.get("diagnostics") or [])
    fallback_diagnostics.insert(
        0,
        {
            "level": "warning",
            "code": "fallback_item_activated",
            "message": (
                f"Primary item {parent_plan.item_id} failed with {trigger}; "
                f"executed fallback item {fallback_plan.item_id}."
            ),
            "trigger": trigger,
            "parent_item_id": parent_plan.item_id,
            "fallback_item_id": fallback_plan.item_id,
        },
    )
    fallback_status = str(fallback_item.get("collection_status") or "error")
    if fallback_status in {"ok", "empty"}:
        reason = (
            f"Primary item timed out ({trigger}); fallback item "
            f"{fallback_plan.item_id} was collected."
        )
    else:
        fallback_reason = fallback_item.get("reason") or fallback_status
        reason = (
            f"Primary item timed out ({trigger}); fallback item "
            f"{fallback_plan.item_id} failed: {fallback_reason}"
        )
    return {
        **fallback_item,
        "item_id": parent_plan.item_id,
        "section_id": parent_plan.section_id,
        "item_key": parent_plan.item_key,
        "title": f"[Fallback] {fallback_item.get('title') or fallback_plan.title}",
        "state": parent_plan.state,
        "collection_scope": parent_plan.collection_scope,
        "reason": reason,
        "timing_ms": round(primary_timing_ms + fallback_timing_ms, 3),
        "source_metadata": fallback_metadata,
        "diagnostics": fallback_diagnostics,
    }


def _numeric_timing(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


async def execute_and_record_report_item(
    run: CollectionRun,
    planned: PlannedItem,
) -> dict[str, Any]:
    collected_at = utc_now()
    try:
        async def execute(conn: Any) -> dict[str, Any]:
            return await execute_report_item(
                run.content,
                conn,
                planned,
                run.ssh,
                run.database_connector,
                server_log=getattr(run, "server_log", None),
            )

        if (
            run.database_connector is not None
            and planned.source_kind in {"query", "python"}
        ):
            item = await execute_with_database_reconnect(
                run,
                execute,
                operation=f"item:{planned.item_id}",
            )
        else:
            item = await execute(run.conn)
        item["collected_at"] = collected_at
        extract_item_query_texts(
            item,
            run.artifact["query_texts"],
            run.content.report["runtime_policy"]["query_text_catalog"],
        )
        run.artifact["items"][planned.item_id] = item
        record_item_progress(run, planned, item)
        raise_if_fail_fast(run.fail_fast, item)
        return item
    except Exception as exc:
        if isinstance(exc, PgDiagError):
            raise
        item = item_error_from_exception(planned, exc)
        item["collected_at"] = collected_at
        run.artifact["items"][planned.item_id] = item
        record_item_progress(run, planned, item)
        raise_if_fail_fast(run.fail_fast, item, cause=exc)
        return item


async def execute_with_database_reconnect(
    run: CollectionRun,
    operation_callback: Callable[[Any], Awaitable[Any]],
    *,
    operation: str,
) -> Any:
    """Run DB work and retry it on a verified replacement connection."""
    try:
        result = await operation_callback(run.conn)
    except Exception as exc:
        if not _is_database_disconnect(exc, run.conn):
            raise
        last_error: BaseException = exc
    else:
        if not _connection_is_closed(run.conn):
            return result
        last_error = ConnectionError("the PostgreSQL connection was closed")

    connector = run.database_connector
    attempts = runtime_config.DATABASE_RECONNECT_ATTEMPTS
    delay_seconds = runtime_config.DATABASE_RECONNECT_DELAY_SECONDS
    if connector is None:
        raise DatabaseUnavailableError(
            "database host is unavailable and no reconnect configuration is available"
        ) from last_error

    await close_connection(run.conn)
    for attempt in range(1, attempts + 1):
        if run.progress is not None:
            run.progress.error(
                f"DB_RECONNECT operation={operation} attempt={attempt}/{attempts} "
                f"delay_seconds={_format_retry_delay(delay_seconds)}"
            )
        await asyncio.sleep(delay_seconds)
        replacement = None
        try:
            replacement = await connector.open(
                timeout_seconds=runtime_config.DATABASE_RECONNECT_CONNECT_TIMEOUT_SECONDS,
            )
            replacement_identity = await detect_runtime_context(replacement)
            _verify_reconnected_database_identity(run.database_identity, replacement_identity)
            run.conn = replacement
            run.database_identity = replacement_identity
            if run.progress is not None:
                run.progress.info(
                    f"DB_RECONNECT operation={operation} attempt={attempt}/{attempts} "
                    "status=connected"
                )
            result = await operation_callback(replacement)
            if not _connection_is_closed(replacement):
                return result
            last_error = ConnectionError(
                "the PostgreSQL connection closed again during the retried operation"
            )
        except DatabaseIdentityChangedError:
            await close_connection(replacement)
            raise
        except Exception as exc:
            if replacement is not None and not _is_database_disconnect(exc, replacement):
                await close_connection(replacement)
                raise
            last_error = exc
        await close_connection(replacement)
        if run.progress is not None:
            run.progress.error(
                f"DB_RECONNECT operation={operation} attempt={attempt}/{attempts} "
                f"status=failed reason={redact_error(last_error)}"
            )

    raise DatabaseUnavailableError(
        "database host is unavailable: PostgreSQL connection could not be restored "
        f"after {attempts} attempts with "
        f"{_format_retry_delay(delay_seconds)}-second delay; "
        f"last error: {redact_error(last_error)}"
    ) from last_error


def _connection_is_closed(conn: Any) -> bool:
    if conn is None:
        return True
    is_closed = getattr(conn, "is_closed", None)
    if not callable(is_closed):
        return False
    try:
        return bool(is_closed())
    except Exception:
        return True


def _is_database_disconnect(exc: BaseException, conn: Any) -> bool:
    if _connection_is_closed(conn):
        return True
    connection_error_names = {
        "CannotConnectNowError",
        "ClientCannotConnectError",
        "ConnectionDoesNotExistError",
        "ConnectionFailureError",
        "ConnectionRefusedError",
        "ConnectionResetError",
    }
    disconnect_fragments = (
        "connection is closed",
        "connection was closed",
        "connection has been closed",
        "connection lost",
        "underlying connection is closed",
    )
    current: BaseException | None = exc
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(current, ConnectionError):
            return True
        if type(current).__name__ in connection_error_names:
            return True
        message = str(current).lower()
        if any(fragment in message for fragment in disconnect_fragments):
            return True
        current = current.__cause__ or current.__context__
    return False


def _verify_reconnected_database_identity(
    expected: dict[str, Any] | None,
    actual: dict[str, Any],
) -> None:
    if expected is None:
        return
    identity_fields = (
        ("current_database", "database"),
        ("server_version_num", "server version"),
        ("in_recovery", "database role"),
        ("database_host_ip", "server address"),
    )
    changes = []
    for field, label in identity_fields:
        expected_value = expected.get(field)
        actual_value = actual.get(field)
        if expected_value is None or actual_value is None or expected_value == actual_value:
            continue
        changes.append(f"{label}: {expected_value!r} -> {actual_value!r}")
    if changes:
        raise DatabaseIdentityChangedError(
            "database identity changed after reconnect; refusing to merge samples "
            "from different PostgreSQL endpoints (" + ", ".join(changes) + ")"
        )


def _format_retry_delay(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def record_item_progress(
    run: CollectionRun,
    planned: PlannedItem,
    item: dict[str, Any] | None = None,
) -> None:
    if run.progress is None:
        return
    status = str((item or {}).get("collection_status") or planned.status)
    reason = (item or {}).get("reason") or planned.reason
    run.progress.item(planned.item_id, status, str(reason) if reason else None)


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


async def collect_report_object_ddl(run: CollectionRun, *, enabled: bool) -> None:
    """Fill artifact['object_ddl'] from oids referenced by collected items."""
    runtime = run.artifact["runtime"]
    run.artifact.setdefault("object_ddl", {})
    if not enabled:
        runtime["ddl_extraction"] = "disabled"
        return
    if run.conn is None or not runtime.get("database_connected"):
        runtime["ddl_extraction"] = "unavailable"
        return
    try:
        server_version_num = int(runtime.get("server_version_num") or 0)
        if not server_version_num:
            server_version_num = int(await run.conn.fetchval("show server_version_num"))
        async with run.conn.transaction(readonly=True):
            await run.conn.execute(
                "select pg_catalog.set_config('statement_timeout', $1, true)",
                str(runtime_config.OBJECT_DDL_STATEMENT_TIMEOUT_MS),
            )
            await run.conn.execute(
                "select pg_catalog.set_config('lock_timeout', $1, true)",
                str(runtime_config.OBJECT_DDL_LOCK_TIMEOUT_MS),
            )
            run.artifact["object_ddl"] = await asyncio.wait_for(
                collect_object_ddl(run.conn, server_version_num, run.artifact),
                timeout=runtime_config.OBJECT_DDL_TIMEOUT_SECONDS,
            )
        runtime["ddl_extraction"] = "collected"
    except Exception as exc:  # noqa: BLE001 - DDL extras must never fail the report
        run.artifact["object_ddl"] = {}
        runtime["ddl_extraction"] = f"failed: {type(exc).__name__}: {exc}"


def finish_collection(
    run: CollectionRun,
    *,
    runtime_updates: dict[str, Any] | None = None,
    strip_meta: bool = False,
) -> dict[str, Any]:
    if runtime_updates:
        run.artifact["runtime"].update(runtime_updates)
    run.artifact["runtime"]["finished_at"] = utc_now()
    omit_skipped_report_items(
        run.artifact,
        {
            planned.item_id
            for planned in run.plan.items
            if planned.status == "skipped"
        },
    )
    apply_database_scope_presentation(run.artifact)
    apply_presentation_contract(run.content, run.artifact)
    if strip_meta:
        strip_artifact_metadata(run.artifact)
    validate_artifact(run.artifact)
    if run.html_path is not None:
        html_text = render_html(run.artifact, validate=False)
        write_text_secure(run.html_path, html_text)
    if run.json_path is not None:
        write_json(run.json_path, run.artifact, validate=False)
    return run.artifact


async def close_connection(conn: Any) -> None:
    if conn is None:
        return
    close = getattr(conn, "close", None)
    if not callable(close):
        return
    try:
        await asyncio.wait_for(
            close(),
            timeout=runtime_config.DATABASE_CONNECTION_CLOSE_TIMEOUT_SECONDS,
        )
    except asyncio.CancelledError:
        _terminate_connection(conn)
        raise
    except (asyncio.TimeoutError, TimeoutError):
        _terminate_connection(conn)
    except Exception:
        _terminate_connection(conn)


def _terminate_connection(conn: Any) -> None:
    terminate = getattr(conn, "terminate", None)
    if not callable(terminate):
        return
    try:
        terminate()
    except Exception:
        pass


async def close_collection(run: CollectionRun) -> None:
    await close_connection(run.conn)
    if run.ssh is not None:
        await run.ssh.close()
