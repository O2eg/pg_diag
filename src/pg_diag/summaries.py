"""Merge Markdown audits into the artifact embedded in an existing HTML report."""

from __future__ import annotations

import csv
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Any

from .errors import ValidationError


REPORT_LINK = re.compile(r"#item-([a-z][a-z0-9_.-]*)(?:\?(queryid|oid)=(-?\d+))?\Z")
MARKDOWN_TOKEN = re.compile(r"(`+).*?\1|\[[^\]\n]+\]\((?P<target>[^\s)]+)\)")


class _ArtifactParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.payloads: list[list[str]] = []
        self.capturing = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "script" and attributes.get("id") == "pg-diag-artifact":
            if attributes.get("type") != "application/json":
                raise ValidationError("The embedded artifact must be application/json")
            self.payloads.append([])
            self.capturing = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.capturing = False

    def handle_data(self, data: str) -> None:
        if self.capturing:
            self.payloads[-1].append(data)


def artifact_from_html(text: str) -> dict[str, Any]:
    parser = _ArtifactParser()
    parser.feed(text)
    parser.close()
    if len(parser.payloads) != 1 or parser.capturing:
        raise ValidationError("Expected exactly one complete pg-diag-artifact JSON block")
    try:
        artifact = json.loads("".join(parser.payloads[0]))
    except (ValueError, RecursionError) as exc:
        raise ValidationError(f"Invalid embedded report JSON: {exc}") from exc
    if not isinstance(artifact, dict):
        raise ValidationError("Embedded report JSON must be an object")
    return artifact


def markdown_file_arguments(values: list[str]) -> list[str]:
    """Accept two shell arguments, or one quoted JSON/CSV-style bracketed list."""
    if len(values) == 1 and values[0].startswith("[") and values[0].endswith("]"):
        try:
            parsed = json.loads(values[0])
        except json.JSONDecodeError:
            parsed = next(csv.reader([values[0][1:-1]], skipinitialspace=True))
        if not isinstance(parsed, list) or not all(isinstance(value, str) for value in parsed):
            raise ValidationError("--md-files must contain two file paths")
        values = [value.strip() for value in parsed]
    if len(values) != 2 or not all(values):
        raise ValidationError("--md-files requires exactly two Markdown files")
    return values


def _markdown_links(markdown: str):
    fence: str | None = None
    for line in markdown.splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence is None:
            # Inline code is literal, including examples of link syntax.
            yield from (
                match['target'] for match in MARKDOWN_TOKEN.finditer(line) if match['target']
            )


def validate_summaries(artifact: dict[str, Any]) -> None:
    if "summaries" not in artifact:
        return
    summaries = artifact["summaries"]
    if not isinstance(summaries, dict) or set(summaries) != {"brief", "detailed"}:
        raise ValidationError("summaries must contain brief and detailed documents")
    items = artifact.get("items") or {}
    visible = {
        item_id
        for section in artifact.get("sections") or []
        if section.get("state") != "hidden"
        for item_id in section.get("items") or []
        if item_id in items and items[item_id].get("state") != "hidden"
        and not (items[item_id].get("source_metadata") or {}).get("internal")
    }
    errors = []
    for kind, document in summaries.items():
        if (
            not isinstance(document, dict)
            or not isinstance(document.get("markdown"), str)
            or not document["markdown"].strip()
        ):
            raise ValidationError(f"summaries.{kind}.markdown must be non-empty text")
        for target in _markdown_links(document["markdown"]):
            if target.startswith(("https://", "http://")):
                continue
            match = REPORT_LINK.fullmatch(target)
            if not match or match[1] not in visible:
                errors.append(f"{kind}: unknown or invalid report link {target}")
                continue
            if match[2] == "queryid" and not (artifact.get("query_texts") or {}).get(match[3]):
                errors.append(f"{kind}: SQL text is absent for {target}")
            if match[2] == "oid":
                entry = (artifact.get("object_ddl") or {}).get(match[3])
                if not isinstance(entry, dict) or not entry.get("ddl"):
                    errors.append(f"{kind}: DDL is absent for {target}")
    if errors:
        raise ValidationError("Invalid summary links:\n" + "\n".join(dict.fromkeys(errors)))


def merge_markdown_to_html(html_file: str | Path, md_files: list[str]) -> None:
    from .artifact import write_text_secure
    from .artifact_schema import validate_artifact
    from .render.html import render_html

    target = Path(html_file).expanduser().resolve()
    paths = [Path(name).expanduser().resolve() for name in markdown_file_arguments(md_files)]
    if paths[0] == paths[1] or target in paths:
        raise ValidationError("HTML and both Markdown documents must be distinct files")
    try:
        documents = [(path.read_bytes(), path) for path in paths]
        if len(documents[0][0]) == len(documents[1][0]):
            raise ValidationError("Markdown files have equal byte sizes; cannot identify detailed audit")
        documents.sort(key=lambda entry: len(entry[0]))
        summaries = {
            kind: {"markdown": data.decode("utf-8-sig")}
            for kind, (data, _) in zip(("brief", "detailed"), documents)
        }
        artifact = artifact_from_html(target.read_text(encoding="utf-8"))
        validate_artifact(artifact)
        artifact["summaries"] = summaries
        validate_summaries(artifact)
        rendered = render_html(artifact)
        write_text_secure(target, rendered)
    except (OSError, UnicodeError) as exc:
        raise ValidationError(f"Cannot merge Markdown into HTML: {exc}") from exc
