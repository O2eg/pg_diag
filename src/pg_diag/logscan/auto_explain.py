"""Parse privacy-safe metadata from auto_explain csvlog messages."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from json.decoder import scanstring
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
_JSON_NUMBER_RE = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")
_JSON_PLAN_ROLES = frozenset({"root_plan", "plan_node"})


@dataclass
class _JsonFrame:
    kind: str
    role: str
    state: str
    key: str | None = None
    index: int = 0


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
    except RecursionError:
        metadata = _parse_deep_json_metadata(plan_text)
        if metadata is None:
            return "json", None, 0, False, None
        root, node_count, query_text = metadata
        return "json", root, node_count, bool(root and node_count), query_text
    except (TypeError, ValueError):
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


def _parse_deep_json_metadata(plan_text: str) -> tuple[str | None, int, str | None] | None:
    """Extract bounded plan metadata without recursive JSON object construction."""
    frames: list[_JsonFrame] = []
    root_started = False
    root_complete = False
    root_node_type: str | None = None
    node_count = 0
    query_text: str | None = None

    def start_value(kind: str, value: str | None, role: str) -> None:
        nonlocal node_count, query_text, root_node_type
        if kind == "{":
            if role in _JSON_PLAN_ROLES:
                node_count += 1
            frames.append(_JsonFrame("object", role, "key_or_end"))
            return
        if kind == "[":
            frames.append(_JsonFrame("array", role, "value_or_end"))
            return
        if kind not in {"string", "scalar"}:
            raise ValueError("expected JSON value")
        if kind == "string" and role == "query_text":
            query_text = value
        elif kind == "string" and role == "root_node_type":
            root_node_type = value

    def object_value_role(frame: _JsonFrame) -> str:
        if frame.role == "payload":
            if frame.key == "Plan":
                return "root_plan"
            if frame.key == "Query Text":
                return "query_text"
        if frame.role in _JSON_PLAN_ROLES:
            if frame.key == "Plans":
                return "plans_array"
            if frame.role == "root_plan" and frame.key == "Node Type":
                return "root_node_type"
        return "other"

    def array_value_role(frame: _JsonFrame) -> str:
        if frame.role == "root_array" and frame.index == 0:
            return "payload"
        if frame.role == "plans_array":
            return "plan_node"
        return "other"

    try:
        for kind, value in _iter_json_tokens(plan_text):
            if not frames:
                if root_started:
                    raise ValueError("trailing JSON content")
                root_started = True
                role = "payload" if kind == "{" else "root_array" if kind == "[" else "other"
                start_value(kind, value, role)
                if not frames:
                    root_complete = True
                continue

            frame = frames[-1]
            if frame.kind == "object":
                if frame.state in {"key_or_end", "key"}:
                    if kind == "}" and frame.state == "key_or_end":
                        frames.pop()
                        root_complete = not frames
                    elif kind == "string":
                        frame.key = value
                        frame.state = "colon"
                    else:
                        raise ValueError("expected JSON object key")
                elif frame.state == "colon":
                    if kind != ":":
                        raise ValueError("expected colon after JSON object key")
                    frame.state = "value"
                elif frame.state == "value":
                    role = object_value_role(frame)
                    frame.key = None
                    frame.state = "comma_or_end"
                    start_value(kind, value, role)
                elif frame.state == "comma_or_end":
                    if kind == "}":
                        frames.pop()
                        root_complete = not frames
                    elif kind == ",":
                        frame.state = "key"
                    else:
                        raise ValueError("expected comma or JSON object end")
                continue

            if frame.state in {"value_or_end", "value"}:
                if kind == "]" and frame.state == "value_or_end":
                    frames.pop()
                    root_complete = not frames
                    continue
                role = array_value_role(frame)
                frame.index += 1
                frame.state = "comma_or_end"
                start_value(kind, value, role)
            elif frame.state == "comma_or_end":
                if kind == "]":
                    frames.pop()
                    root_complete = not frames
                elif kind == ",":
                    frame.state = "value"
                else:
                    raise ValueError("expected comma or JSON array end")
        if frames or not root_started or not root_complete:
            raise ValueError("incomplete JSON value")
    except (TypeError, ValueError):
        return None
    return root_node_type, node_count, query_text


def _iter_json_tokens(plan_text: str):
    index = 0
    while index < len(plan_text):
        character = plan_text[index]
        if character.isspace():
            index += 1
            continue
        if character in "{}[]:,":
            yield character, None
            index += 1
            continue
        if character == '"':
            value, index = scanstring(plan_text, index + 1, True)
            yield "string", value
            continue
        number_match = _JSON_NUMBER_RE.match(plan_text, index)
        if number_match is not None:
            yield "scalar", None
            index = number_match.end()
            continue
        literal = next(
            (candidate for candidate in ("true", "false", "null") if plan_text.startswith(candidate, index)),
            None,
        )
        if literal is None:
            raise ValueError("invalid JSON token")
        yield "scalar", None
        index += len(literal)


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
