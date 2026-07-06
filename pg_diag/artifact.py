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
