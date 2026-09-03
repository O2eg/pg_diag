"""Parse privacy-safe metadata from auto_explain csvlog messages."""

from __future__ import annotations

import json
import math
import re
from typing import Any
from xml.etree import ElementTree

from .model import AutoExplainPlan
from .sanitize import sanitize_text

QUERY_SAMPLE_CHARS = 300

_HEADER_RE = re.compile(
    r"^duration:\s+(?P<duration>\d+(?:\.\d+)?)\s+ms\s+plan:\s*\n(?P<plan>.*)\Z",
    re.DOTALL,
)
_TEXT_NODE_RE = re.compile(r"^(?:->\s+)?(?P<node>.+?)\s{2,}\(cost=")
_YAML_NODE_RE = re.compile(r"^\s*(?:-\s+)?Node Type:\s*(?P<node>.+?)\s*$", re.MULTILINE)
_YAML_QUERY_RE = re.compile(r"^Query Text:\s*(?P<query>.+?)\s*$", re.MULTILINE)
_XML_LIST_CHILDREN = frozenset({"Item", "Plan", "Setting", "Trigger", "Worker"})
_XML_INTEGER_RE = re.compile(r"^-?\d+$")
_XML_DECIMAL_RE = re.compile(r"^-?(?:\d+\.\d*|\d*\.\d+)(?:[eE][+-]?\d+)?$")


def parse_auto_explain(message: str, *, complete: bool) -> AutoExplainPlan | None:
    """Return extracted plan metadata, or ``None`` for a non-auto_explain record."""
    match = _HEADER_RE.match(message)
    if match is None:
        return None
    duration_ms = float(match.group("duration"))
    if not math.isfinite(duration_ms) or duration_ms < 0:
        return None
    plan_text = match.group("plan")
    plan_format, root_node_type, node_count, parsed, query_text = _parse_plan(plan_text)
    return AutoExplainPlan(
        duration_ms=duration_ms,
        plan_format=plan_format,
        root_node_type=root_node_type,
        node_count=node_count,
        parsed=parsed,
        complete=complete,
        query_sample=_query_sample(query_text),
        viewer_plan=_viewer_plan(message, plan_text, plan_format, duration_ms),
    )


def _parse_plan(plan_text: str) -> tuple[str, str | None, int, bool, str | None]:
    stripped = plan_text.lstrip()
    if stripped.startswith(("{", "[")):
        return _parse_json(stripped)
    if stripped.startswith("<"):
        return _parse_xml(stripped)
    if re.search(r"(?m)^Plan:\s*$", plan_text) is not None:
        return _parse_yaml(plan_text)
    return _parse_text(plan_text)


def _parse_json(plan_text: str) -> tuple[str, str | None, int, bool, str | None]:
    try:
        payload: Any = json.loads(plan_text)
    except (TypeError, ValueError, RecursionError):
        return "json", None, 0, False, None
    if isinstance(payload, list) and payload:
        payload = payload[0]
    plan = payload.get("Plan") if isinstance(payload, dict) else None
    if not isinstance(plan, dict):
        return "json", None, 0, False, None
    root = plan.get("Node Type")
    node_count = _count_json_nodes(plan)
    query_text = payload.get("Query Text")
    return (
        "json",
        str(root) if root else None,
        node_count,
        bool(root and node_count),
        str(query_text) if isinstance(query_text, str) else None,
    )


def _count_json_nodes(plan: dict[str, Any]) -> int:
    count = 0
    pending = [plan]
    while pending:
        node = pending.pop()
        count += 1
        children = node.get("Plans")
        if isinstance(children, list):
            pending.extend(child for child in children if isinstance(child, dict))
    return count


def _parse_xml(plan_text: str) -> tuple[str, str | None, int, bool, str | None]:
    if "<!DOCTYPE" in plan_text.upper() or "<!ENTITY" in plan_text.upper():
        return "xml", None, 0, False, None
    try:
        root = ElementTree.fromstring(plan_text)
    except (ElementTree.ParseError, ValueError):
        return "xml", None, 0, False, None
    plans = [element for element in root.iter() if _local_name(element.tag) == "Plan"]
    root_node = None
    if plans:
        for child in plans[0]:
            if _local_name(child.tag) == "Node-Type":
                root_node = (child.text or "").strip() or None
                break
    query_element = next(
        (element for element in root.iter() if _local_name(element.tag) == "Query-Text"),
        None,
    )
    query_text = "".join(query_element.itertext()) if query_element is not None else None
    return "xml", root_node, len(plans), bool(root_node and plans), query_text


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _viewer_plan(
    message: str,
    plan_text: str,
    plan_format: str,
    duration_ms: float,
) -> str | None:
    try:
        if plan_format == "json":
            converted = _json_viewer_payload(plan_text)
            if converted is None:
                return None
            safe_payload = _sanitize_nested_text(converted)
            serialized = json.dumps(safe_payload, ensure_ascii=False, separators=(",", ":"))
            return f"duration: {duration_ms:g} ms  plan:\n{serialized}"
        if plan_format != "xml":
            return sanitize_text(message)
        converted = _xml_viewer_payload(plan_text)
        if converted is None:
            return None
        safe_payload = _sanitize_nested_text(converted)
        serialized = json.dumps([safe_payload], ensure_ascii=False, separators=(",", ":"))
        return f"duration: {duration_ms:g} ms  plan:\n{serialized}"
    except (RecursionError, TypeError, ValueError, OverflowError):
        # A pathological but valid deeply nested plan must not abort the
        # complete server-log phase. Metadata remains available in the chart;
        # only the optional embedded viewer is disabled for this record.
        return None


def _json_viewer_payload(plan_text: str) -> Any | None:
    try:
        return json.loads(plan_text)
    except (TypeError, ValueError, RecursionError):
        return None


def _xml_viewer_payload(plan_text: str) -> dict[str, Any] | None:
    if "<!DOCTYPE" in plan_text.upper() or "<!ENTITY" in plan_text.upper():
        return None
    try:
        root = ElementTree.fromstring(plan_text)
    except (ElementTree.ParseError, ValueError):
        return None
    query = next(
        (element for element in root.iter() if _local_name(element.tag) == "Query"),
        None,
    )
    payload = _xml_element_value(query if query is not None else root)
    return payload if isinstance(payload, dict) and isinstance(payload.get("Plan"), dict) else None


def _xml_element_value(element: ElementTree.Element) -> Any:
    children = list(element)
    if not children:
        return _xml_scalar(_local_name(element.tag), element.text or "")
    child_names = [_local_name(child.tag) for child in children]
    if len(set(child_names)) == 1 and child_names[0] in _XML_LIST_CHILDREN:
        return [_xml_element_value(child) for child in children]
    result: dict[str, Any] = {}
    for child, child_name in zip(children, child_names):
        key = child_name.replace("-", " ")
        value = _xml_element_value(child)
        if key not in result:
            result[key] = value
            continue
        existing = result[key]
        if not isinstance(existing, list):
            result[key] = [existing]
        result[key].append(value)
    return result


def _xml_scalar(tag: str, text: str) -> Any:
    value = text.strip()
    if tag in {"Item", "Query-Identifier", "Query-Text"}:
        return value
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if _XML_INTEGER_RE.fullmatch(value):
        return int(value)
    if _XML_DECIMAL_RE.fullmatch(value):
        return float(value)
    return value


def _sanitize_nested_text(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, list):
        return [_sanitize_nested_text(item) for item in value]
    if isinstance(value, dict):
        return {key: _sanitize_nested_text(item) for key, item in value.items()}
    return value


def _parse_yaml(plan_text: str) -> tuple[str, str | None, int, bool, str | None]:
    nodes = [_unquote(match.group("node")) for match in _YAML_NODE_RE.finditer(plan_text)]
    query_match = _YAML_QUERY_RE.search(plan_text)
    query_text = _unquote(query_match.group("query")) if query_match else None
    return "yaml", nodes[0] if nodes else None, len(nodes), bool(nodes), query_text


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            decoded = json.loads(value)
        except ValueError:
            return value[1:-1]
        return str(decoded)
    return value


def _parse_text(plan_text: str) -> tuple[str, str | None, int, bool, str | None]:
    nodes: list[str] = []
    query_lines: list[str] = []
    reading_query = False
    for raw_line in plan_text.splitlines():
        line = raw_line.strip()
        if line.startswith("Query Text:"):
            reading_query = True
            query_lines.append(line.removeprefix("Query Text:").strip())
            continue
        match = _TEXT_NODE_RE.match(line)
        if match is not None:
            reading_query = False
            nodes.append(match.group("node").strip())
        elif reading_query and line:
            query_lines.append(line)
    query_text = " ".join(query_lines) if query_lines else None
    return "text", nodes[0] if nodes else None, len(nodes), bool(nodes), query_text


def _query_sample(query_text: str | None) -> str | None:
    if not query_text:
        return None
    normalized = re.sub(r"\s+", " ", sanitize_text(query_text)).strip()
    if not normalized:
        return None
    if len(normalized) > QUERY_SAMPLE_CHARS:
        return normalized[:QUERY_SAMPLE_CHARS].rstrip() + "..."
    return normalized
