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

from pg_diag.artifact import write_text_secure
from pg_diag.artifact_schema import validate_artifact

_SCRIPT_END_RE = re.compile(r"</script", re.IGNORECASE)
_STYLE_END_RE = re.compile(r"</style", re.IGNORECASE)


def render_html(artifact: dict[str, Any], *, validate: bool = True) -> str:
    if validate:
        validate_artifact(artifact)
    artifact = _publicize_artifact_for_render(artifact)
    payload = _safe_json_payload(artifact)
    title = html.escape(artifact["report"]["title"])
    replacements = {
        "__TITLE__": title,
        "__PAYLOAD__": payload,
        "__ECHARTS_JS__": _inline_script(
            _read_render_resource("vendor", "echarts-6.1.0.min.js")
        ),
        "__HIGHLIGHT_JS__": _inline_script(
            _read_render_resource("vendor", "highlight-11.11.1.min.js")
        ),
        "__HIGHLIGHT_CSS__": _inline_style(
            _read_render_resource("vendor", "highlight-github-dark-11.11.1.min.css")
        ),
        "__THIRD_PARTY_LICENSES__": _inline_script(_third_party_licenses()),
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


@lru_cache(maxsize=1)
def _third_party_licenses() -> str:
    sections = [
        _read_render_resource("vendor", "THIRD_PARTY_LICENSES.txt"),
        "Apache ECharts 6.1.0 - Apache-2.0 license\n\n"
        + _read_render_resource("vendor", "echarts-6.1.0.LICENSE.txt"),
        "Apache ECharts 6.1.0 - NOTICE\n\n"
        + _read_render_resource("vendor", "echarts-6.1.0.NOTICE.txt"),
        "Apache ECharts 6.1.0 embedded d3 components - BSD-3-Clause license\n\n"
        + _read_render_resource("vendor", "echarts-6.1.0.LICENSE-d3.txt"),
        "highlight.js 11.11.1 - BSD-3-Clause license\n\n"
        + _read_render_resource("vendor", "highlight-11.11.1.LICENSE.txt"),
    ]
    return "\n\n".join(section.rstrip() for section in sections) + "\n"


def _publicize_artifact_for_render(artifact: dict[str, Any]) -> dict[str, Any]:
    snapshots = artifact["snapshots"]
    public_artifact = deepcopy(
        {
            key: value
            for key, value in artifact.items()
            if key not in {"sections", "items", "snapshots", "snapshot_schemas"}
        }
    )
    public_artifact["runtime"]["snapshot_count"] = len(snapshots)
    public_artifact["snapshots"] = []
    public_artifact["snapshot_schemas"] = {}

    public_sections = deepcopy(
        [
            section
            for section in artifact["sections"]
            if isinstance(section, dict) and section.get("state") != "hidden"
        ]
    )
    all_items = artifact["items"]
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

    return public_artifact
