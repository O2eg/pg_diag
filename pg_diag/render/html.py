"""Self-contained HTML renderer for pg_diag artifacts."""

from __future__ import annotations

import html
import json
import re
from copy import deepcopy
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any

from pg_diag.artifact import apply_database_scope_presentation, write_text_secure
from pg_diag.artifact_schema import validate_artifact
from pg_diag.executors.sql import publicize_table_result

_SCRIPT_END_RE = re.compile(r"</script", re.IGNORECASE)
_STYLE_END_RE = re.compile(r"</style", re.IGNORECASE)


def render_html(artifact: dict[str, Any], *, validate: bool = True) -> str:
    if validate:
        validate_artifact(artifact)
    artifact = _publicize_artifact_for_render(artifact)
    payload = _safe_json_payload(artifact)
    title = html.escape(str((artifact.get("report") or {}).get("title") or "pg_diag report"))
    replacements = {
        "__TITLE__": title,
        "__PAYLOAD__": payload,
        "__APEXCHARTS_JS__": _inline_script(_read_render_resource("vendor", "apexcharts-5.16.0.min.js")),
        "__HIGHLIGHT_JS__": _inline_script(_read_render_resource("vendor", "highlight-11.11.1.min.js")),
        "__HIGHLIGHT_CSS__": _inline_style(
            _read_render_resource("vendor", "highlight-github-dark-11.11.1.min.css")
        ),
        "__THIRD_PARTY_LICENSES__": _inline_script(
            _read_render_resource("vendor", "THIRD_PARTY_LICENSES.txt")
        ),
    }
    placeholder_pattern = re.compile("|".join(re.escape(key) for key in replacements))
    return placeholder_pattern.sub(lambda match: replacements[match.group(0)], _html_template())


def render_from_json(json_path: str | Path, html_path: str | Path) -> None:
    artifact = json.loads(Path(json_path).read_text(encoding="utf-8"))
    html_text = render_html(artifact)
    write_text_secure(html_path, html_text)


def _safe_json_payload(artifact: dict[str, Any]) -> str:
    payload = json.dumps(artifact, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return (
        payload.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


@lru_cache(maxsize=1)
def _html_template() -> str:
    return _read_render_resource("templates", "report.html")


@lru_cache(maxsize=None)
def _read_render_resource(*path_parts: str) -> str:
    return files("pg_diag.render").joinpath(*path_parts).read_text(encoding="utf-8")


def _inline_script(value: str) -> str:
    return _SCRIPT_END_RE.sub("<\\/script", value)


def _inline_style(value: str) -> str:
    return _STYLE_END_RE.sub("<\\/style", value)


def _publicize_artifact_for_render(artifact: dict[str, Any]) -> dict[str, Any]:
    snapshots = artifact.get("snapshots") or []
    public_artifact = deepcopy(
        {
            key: value
            for key, value in artifact.items()
            if key not in {"sections", "items", "snapshots", "snapshot_schemas"}
        }
    )
    runtime = public_artifact.setdefault("runtime", {})
    if isinstance(runtime, dict):
        runtime.setdefault("snapshot_count", len(snapshots))
    public_artifact["snapshots"] = []
    public_artifact["snapshot_schemas"] = {}

    public_sections = deepcopy(
        [
            section
            for section in artifact.get("sections") or []
            if isinstance(section, dict) and section.get("state") != "hidden"
        ]
    )
    all_items = artifact.get("items") or {}
    for section in public_sections:
        section["items"] = [
            item_id
            for item_id in section.get("items") or []
            if isinstance(all_items.get(item_id), dict)
            and all_items[item_id].get("state") != "hidden"
        ]
    public_artifact["sections"] = public_sections
    visible_item_ids = {
        item_id
        for section in public_sections
        for item_id in section.get("items") or []
    }
    public_artifact["items"] = deepcopy(
        {
            item_id: item
            for item_id, item in all_items.items()
            if item_id in visible_item_ids
        }
    )

    for item in (public_artifact.get("items") or {}).values():
        result = item.get("result") or {}
        if result.get("kind") != "table":
            continue
        columns = result.get("columns") or []
        rows = result.get("rows") or []
        public_columns, public_rows = publicize_table_result(columns, rows)
        result["columns"] = public_columns
        result["rows"] = public_rows
        result["row_count"] = len(public_rows)
    apply_database_scope_presentation(public_artifact)
    return public_artifact
