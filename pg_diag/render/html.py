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

from pg_diag.artifact_schema import validate_artifact
from pg_diag.executors.sql import publicize_table_result

_SCRIPT_END_RE = re.compile(r"</script", re.IGNORECASE)
_STYLE_END_RE = re.compile(r"</style", re.IGNORECASE)


def render_html(artifact: dict[str, Any]) -> str:
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
    html_text = _html_template()
    for placeholder, value in replacements.items():
        html_text = html_text.replace(placeholder, value)
    return html_text


def render_from_json(json_path: str | Path, html_path: str | Path) -> None:
    artifact = json.loads(Path(json_path).read_text(encoding="utf-8"))
    html_text = render_html(artifact)
    output = Path(html_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_text, encoding="utf-8")


def _safe_json_payload(artifact: dict[str, Any]) -> str:
    payload = json.dumps(artifact, ensure_ascii=False, separators=(",", ":"))
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
    public_artifact = deepcopy(artifact)
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
    return public_artifact
