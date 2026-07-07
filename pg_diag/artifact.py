"""Runtime artifact helpers."""

from __future__ import annotations

import json
import getpass
import platform
import socket
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__, runtime_config
from .content_loader import ContentPack
from .planner import ExecutionPlan, PlannedItem
from .security import redact_error, redact_text


INTERNAL_TAG_PREFIX = "tag_"


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


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
            "report_id": (content.report.get("report") or {}).get("id"),
        },
        "report": {
            "id": (content.report.get("report") or {}).get("id"),
            "title": (content.report.get("report") or {}).get("title"),
            "description": (content.report.get("report") or {}).get("description"),
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
            **runtime_context,
        },
        "sections": plan.sections,
        "items": {},
        "query_texts": {},
        "snapshots": [],
        "diagnostics": [],
    }


def _collector_host() -> str:
    return socket.gethostname()


def _collector_user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return ""


def item_from_plan(
    planned: PlannedItem,
    status: str,
    result: dict[str, Any] | None = None,
    timing_ms: float | None = None,
    reason: str | None = None,
    diagnostics: list[dict[str, Any]] | None = None,
    source_text: str | None = None,
    source_language: str | None = None,
) -> dict[str, Any]:
    source_metadata = _publicize_metadata(planned.source_metadata)
    if source_text is not None:
        source_metadata["source_text"] = source_text
        source_metadata["source_language"] = source_language or planned.source_kind
    return {
        "item_id": planned.item_id,
        "section_id": planned.section_id,
        "title": planned.title,
        "source_kind": planned.source_kind,
        "status": status,
        "state": planned.state,
        "reason": reason,
        "result": result or {"kind": "none"},
        "timing_ms": timing_ms,
        "source_metadata": source_metadata,
        "diagnostics": diagnostics or [],
    }


def item_error_from_exception(
    planned: PlannedItem,
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
        status="error",
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


def write_json(path: str | Path, artifact: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        json.dump(artifact, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def extract_item_query_texts(item: dict[str, Any], query_texts: dict[str, str]) -> None:
    """Move SQL text columns paired with query_id columns into the artifact catalog."""
    result = item.get("result") or {}
    if result.get("kind") != "table":
        return

    columns = result.get("columns")
    rows = result.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        return

    column_names = [_column_name(column, index) for index, column in enumerate(columns)]
    name_to_index = {name: index for index, name in enumerate(column_names) if name}
    query_pairs: list[tuple[int, int]] = []
    remove_indexes: set[int] = set()
    for query_id_index, column_name in enumerate(column_names):
        if not column_name.endswith("query_id"):
            continue
        query_column_name = column_name.removesuffix("_id")
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
) -> tuple[Path, Path]:
    output_dir = Path(out_dir)
    json_path = Path(json_out) if json_out else output_dir / "report.json"
    html_path = Path(html_out) if html_out else output_dir / "report.html"
    return json_path, html_path


def _publicize_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _publicize_metadata(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_publicize_metadata(item) for item in value]
    if isinstance(value, str) and value.startswith(INTERNAL_TAG_PREFIX):
        return value[len(INTERNAL_TAG_PREFIX) :]
    return value
