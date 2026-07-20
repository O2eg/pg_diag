"""Runtime artifact helpers."""

from __future__ import annotations

import getpass
import json
import os
import platform
import socket
import tempfile
import traceback
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__, runtime_config
from .contracts import SEVERITY_LEVELS
from .content_loader import ContentPack
from .planner import ExecutionPlan, PlannedEntry
from .security import (
    json_safe,
    redact_error,
    redact_text,
    sanitize_public_structure,
    sanitize_result,
)


INTERNAL_TAG_PREFIX = "tag_"
COLLECTION_ERROR_STATUSES = {"error"}
STRIPPED_SOURCE_METADATA_KEYS = ("chart", "display", "internal", "render", "tags")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().removesuffix("+00:00") + "Z"


def create_artifact(
    content: ContentPack,
    plan: ExecutionPlan,
    runtime_context: dict[str, Any],
    started_at: str,
) -> dict[str, Any]:
    return {
        "artifact_schema_version": runtime_config.ARTIFACT_SCHEMA_VERSION,
        "generator": {"name": "pg_diag", "version": __version__},
        "content": {
            "schema_version": runtime_config.SUPPORTED_CONTENT_SCHEMA_VERSION,
            "content_path": str(content.path),
            "checksum": content.checksum,
            "report_id": content.report["report"]["id"],
            "document": json_safe(content.document),
            "provenance": json_safe(content.provenance),
        },
        "report": {
            "id": content.report["report"]["id"],
            "title": content.report["report"]["title"],
            "description": content.report["report"].get("description"),
        },
        "runtime": {
            "mode": plan.mode,
            "collection_mode": plan.collection_mode,
            "collector_host": _collector_host(),
            "collector_user": _collector_user(),
            "collector_platform": platform.platform(),
            "started_at": started_at,
            "finished_at": None,
            "server_version_num": plan.server_version_num,
            **json_safe(runtime_context),
        },
        "display": json_safe(content.report["defaults"]),
        "sections": plan.sections,
        "items": {},
        "query_texts": {},
        "snapshot_schemas": {},
        "snapshots": [],
        "diagnostics": [],
    }


def strip_artifact_metadata(artifact: dict[str, Any]) -> dict[str, Any]:
    """Remove item source/configuration metadata while preserving report presentation."""
    runtime = artifact.setdefault("runtime", {})
    runtime["strip_meta"] = True

    for item in (artifact.get("items") or {}).values():
        if not isinstance(item, dict):
            continue
        metadata = item.get("source_metadata")
        item["source_metadata"] = {
            key: json_safe(metadata[key])
            for key in STRIPPED_SOURCE_METADATA_KEYS
            if isinstance(metadata, dict) and key in metadata
        }

    content = artifact.get("content")
    if not isinstance(content, dict):
        return artifact
    document = content.get("document")
    presentation = (
        ((document.get("catalogs") or {}).get("presentation") or {})
        if isinstance(document, dict)
        else {}
    )
    units = presentation.get("units") if isinstance(presentation, dict) else {}
    unit_registry = {
        str(unit): {}
        for unit in (units if isinstance(units, dict) else {})
    }
    content["document"] = {
        "report": {},
        "runtime_policy": {},
        "defaults": {},
        "sections": {},
        "catalogs": {"presentation": {"units": unit_registry}},
        "queries": {},
        "scripts": {},
        "metrics": {},
        "python_sources": {},
        "sampler_providers": {},
        "instructions": {},
        "field_reference": {"*": "Item metadata omitted by --strip-meta."},
    }
    provenance = content.get("provenance")
    report_sources = (
        provenance.get("report")
        if isinstance(provenance, dict) and isinstance(provenance.get("report"), list)
        else []
    )
    content["provenance"] = {
        "report": [
            source
            for source in report_sources
            if isinstance(source, str) and source
        ]
    }
    return artifact


def _collector_host() -> str:
    return socket.gethostname()


def _collector_user() -> str:
    return getpass.getuser()


def item_from_plan(
    planned: PlannedEntry,
    collection_status: str,
    result: dict[str, Any] | None = None,
    timing_ms: float | None = None,
    reason: str | None = None,
    diagnostics: list[dict[str, Any]] | None = None,
    issues: dict[str, Any] | None = None,
    severity_level: str | None = None,
    source_text: str | None = None,
    source_language: str | None = None,
) -> dict[str, Any]:
    normalized_issues = sanitize_public_structure(issues or {})
    normalized_severity_level = _item_severity_level(collection_status, severity_level)
    source_metadata = json_safe(_publicize_metadata(planned.source_metadata))
    if source_text is not None:
        source_metadata["source_text"] = source_text
        source_metadata["source_language"] = source_language or planned.source_kind
    return {
        "item_id": planned.item_id,
        "section_id": getattr(planned, "section_id", None),
        "item_key": getattr(planned, "item_key", None),
        "title": planned.title,
        "source_kind": planned.source_kind,
        "collection_scope": planned.collection_scope,
        "collection_status": collection_status,
        "severity_level": normalized_severity_level,
        "state": getattr(planned, "state", None),
        "reason": redact_error(reason) if isinstance(reason, str) else json_safe(reason),
        "result": sanitize_result(result),
        "timing_ms": json_safe(timing_ms),
        "source_metadata": source_metadata,
        "diagnostics": sanitize_public_structure(diagnostics or []),
        "issues": normalized_issues,
    }


def item_error_from_exception(
    planned: PlannedEntry,
    exc: BaseException,
    *,
    timing_ms: float | None = None,
    source_text: str | None = None,
    source_language: str | None = None,
) -> dict[str, Any]:
    message = redact_error(exc)
    trace = redact_text("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    return item_from_plan(
        planned,
        collection_status="error",
        reason=message,
        timing_ms=timing_ms,
        result={"kind": "plain_text", "data": trace},
        diagnostics=[
            {
                "level": "error",
                "code": "python_exception",
                "message": message,
                "traceback": trace,
            }
        ],
        source_text=source_text,
        source_language=source_language,
    )


def _item_severity_level(collection_status: str, severity_level: str | None) -> str:
    if collection_status in COLLECTION_ERROR_STATUSES:
        return "unknown"
    if severity_level is None:
        return "unknown"
    level = str(severity_level).strip().lower()
    if level not in SEVERITY_LEVELS:
        raise ValueError(f"unsupported severity_level {severity_level!r}")
    return level


def write_json(
    path: str | Path,
    artifact: dict[str, Any],
    *,
    validate: bool = True,
) -> None:
    if validate:
        from .artifact_schema import validate_artifact

        validate_artifact(artifact)
    payload = json.dumps(
        artifact,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ) + "\n"
    write_text_secure(path, payload)


def write_text_secure(path: str | Path, text: str) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary_name = tempfile.mkstemp(
        dir=output.parent,
        prefix=f".{output.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
        os.chmod(output, 0o600)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


def compact_snapshot_item(item: dict[str, Any]) -> dict[str, Any]:
    """Keep only sample-varying fields; static metadata lives in top-level items."""
    result = item.get("result") or {"kind": "none"}
    if item.get("collection_status") not in {"ok", "empty"}:
        compact_result = {"kind": "none"}
    elif result.get("kind") == "table":
        compact_result = {
            "kind": "table",
            "rows": result.get("rows") or [],
        }
    else:
        compact_result = result
    compact = {
        "collection_status": item.get("collection_status"),
        "result": compact_result,
    }
    if item.get("reason") is not None:
        compact["reason"] = item["reason"]
    return compact


def artifact_has_errors(artifact: dict[str, Any]) -> bool:
    if any(
        isinstance(item, dict) and item.get("collection_status") == "error"
        for item in (artifact.get("items") or {}).values()
    ):
        return True
    return any(
        isinstance(item, dict) and item.get("collection_status") == "error"
        for snapshot in artifact.get("snapshots") or []
        if isinstance(snapshot, dict)
        for item in (snapshot.get("items") or {}).values()
    )


def omit_skipped_report_items(
    artifact: dict[str, Any],
    planned_skipped_item_ids: set[str] | None = None,
) -> None:
    """Remove mode-inapplicable items and any sections left empty by them."""
    items = artifact.get("items") or {}
    skipped_item_ids = set(planned_skipped_item_ids or set())
    skipped_item_ids.update({
        item_id
        for item_id, item in items.items()
        if isinstance(item, dict) and item.get("collection_status") == "skipped"
    })
    if not skipped_item_ids:
        return

    artifact["items"] = {
        item_id: item
        for item_id, item in items.items()
        if item_id not in skipped_item_ids
    }
    filtered_sections = []
    for section in artifact.get("sections") or []:
        item_ids = [
            item_id
            for item_id in section.get("items") or []
            if item_id not in skipped_item_ids
        ]
        if item_ids:
            filtered_sections.append({**section, "items": item_ids})
    artifact["sections"] = filtered_sections


def apply_database_scope_presentation(artifact: dict[str, Any]) -> None:
    """Apply the declarative database-scope presentation contract."""
    config = artifact["display"]["database_scope_presentation"]
    metadata_field = str(config["metadata_field"])
    presentations = config["values"]
    runtime = artifact["runtime"]
    for item in (artifact.get("items") or {}).values():
        if not isinstance(item, dict):
            continue
        metadata = item.get("source_metadata") or {}
        scope = metadata.get(metadata_field) if isinstance(metadata, dict) else None
        presentation = presentations.get(scope)
        if not isinstance(presentation, dict):
            continue
        suffix = str(presentation["title_suffix"]).format_map(runtime)
        for column_name in presentation["hidden_columns"]:
            _remove_table_column(item.get("result"), column_name)
            _remove_redundant_default_sort(metadata, column_name)
        title = str(item.get("title") or "")
        if not title.endswith(suffix):
            item["title"] = title + suffix


def _remove_table_column(result: Any, column_name: str) -> None:
    if not isinstance(result, dict) or result.get("kind") != "table":
        return
    columns = result.get("columns")
    rows = result.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        return
    remove_indexes = [
        index
        for index, column in enumerate(columns)
        if _column_name(column, index) == column_name
    ]
    if not remove_indexes:
        return
    remove = set(remove_indexes)
    result["columns"] = [column for index, column in enumerate(columns) if index not in remove]
    result["rows"] = [
        [value for index, value in enumerate(row) if index not in remove]
        if isinstance(row, list)
        else row
        for row in rows
    ]
    result["row_count"] = len(rows)


def _remove_redundant_default_sort(metadata: dict[str, Any], column_name: str) -> None:
    display = metadata.get("display")
    if not isinstance(display, dict):
        return
    default_sort = display.get("default_sort")
    if isinstance(default_sort, dict) and default_sort.get("column") == column_name:
        display.pop("default_sort", None)


def extract_item_query_texts(
    item: dict[str, Any],
    query_texts: dict[str, str],
    contract: dict[str, Any],
) -> None:
    """Apply the declared query-text catalog extraction contract."""
    result = item.get("result") or {}
    if result.get("kind") != "table":
        return

    columns = result.get("columns")
    rows = result.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        return

    column_names = [_column_name(column, index) for index, column in enumerate(columns)]
    name_to_index = {name: index for index, name in enumerate(column_names) if name}
    id_column_suffix = str(contract["id_column_suffix"])
    value_column_remove_suffix = str(contract["value_column_remove_suffix"])
    query_pairs: list[tuple[int, int]] = []
    remove_indexes: set[int] = set()
    for query_id_index, column_name in enumerate(column_names):
        if not column_name.endswith(id_column_suffix):
            continue
        query_column_name = column_name.removesuffix(value_column_remove_suffix)
        query_index = name_to_index.get(query_column_name)
        if query_index is None:
            continue
        query_pairs.append((query_id_index, query_index))
        remove_indexes.add(query_index)

    if not query_pairs:
        return

    for row in rows:
        if not isinstance(row, list):
            continue
        for query_id_index, query_index in query_pairs:
            query_id = row[query_id_index] if query_id_index < len(row) else None
            query_text = row[query_index] if query_index < len(row) else None
            _remember_query_text(query_texts, query_id, query_text)

    keep_indexes = [index for index in range(len(columns)) if index not in remove_indexes]
    result["columns"] = [columns[index] for index in keep_indexes]
    result["rows"] = [
        [row[index] if index < len(row) else None for index in keep_indexes]
        if isinstance(row, list)
        else row
        for row in rows
    ]


def _column_name(column: Any, index: int) -> str:
    if isinstance(column, str):
        return column
    if isinstance(column, dict):
        return str(column.get("name") or f"column_{index + 1}")
    return f"column_{index + 1}"


def _remember_query_text(query_texts: dict[str, str], query_id: Any, query_text: Any) -> None:
    if query_id is None or query_text is None:
        return
    query_id_text = str(query_id).strip()
    sql_text = str(query_text).strip()
    if not query_id_text or not sql_text:
        return
    existing = query_texts.get(query_id_text)
    if existing is None or len(sql_text) > len(existing):
        query_texts[query_id_text] = sql_text


def report_output_paths(
    out_dir: str | Path,
    json_out: str | Path | None = None,
    html_out: str | Path | None = None,
    output_formats: str | Iterable[str] | None = None,
) -> tuple[Path | None, Path | None]:
    requested = (
        runtime_config.DEFAULT_REPORT_OUTPUT_FORMATS
        if output_formats is None
        else (output_formats,)
        if isinstance(output_formats, str)
        else tuple(output_formats)
    )
    formats = {str(value).strip().lower() for value in requested if str(value).strip()}
    unsupported = formats.difference(runtime_config.REPORT_OUTPUT_FORMATS)
    if unsupported:
        raise ValueError(f"unsupported report output format(s): {', '.join(sorted(unsupported))}")
    if not formats:
        raise ValueError("at least one report output format is required")
    if json_out and "json" not in formats:
        raise ValueError("--json-out requires --output-format to include json")
    if html_out and "html" not in formats:
        raise ValueError("--html-out requires --output-format to include html")

    output_dir = Path(out_dir)
    json_path = None
    if "json" in formats:
        json_path = Path(json_out) if json_out else output_dir / "report.json"
    html_path = None
    if "html" in formats:
        html_path = Path(html_out) if html_out else output_dir / "report.html"
    if (
        json_path is not None
        and html_path is not None
        and json_path.resolve(strict=False) == html_path.resolve(strict=False)
    ):
        raise ValueError("JSON and HTML output paths must be different files")
    return json_path, html_path


def _publicize_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _publicize_metadata(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_publicize_metadata(item) for item in value]
    if isinstance(value, str) and value.startswith(INTERNAL_TAG_PREFIX):
        return value[len(INTERNAL_TAG_PREFIX) :]
    return value
