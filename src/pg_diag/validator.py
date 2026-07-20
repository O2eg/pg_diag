"""Content validation for pg_diag."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import math
import os
from pathlib import Path
import re
from typing import Any

from . import runtime_config
from .contracts import DATABASE_SCOPES
from .content_loader import (
    ContentLoadError,
    ContentPack,
    instruction_ref_for_report_item,
    iter_report_items,
    resolve_under,
)
from .sql_lint import lint_sql
from .versioning import variant_intersects_supported_window


@dataclass(frozen=True)
class ValidationIssue:
    level: str
    code: str
    message: str
    location: str


SOURCE_KEYS = {"query", "script", "metric", "python"}
FORBIDDEN_LAYOUT_KEYS = {"columns", "theader", "fields"}
VALID_STATES = {"expanded", "collapsed", "hidden"}
VALID_COLLECTION_SCOPES = {
    runtime_config.ONCE_COLLECTION_SCOPE,
    runtime_config.EVERY_SNAPSHOT_COLLECTION_SCOPE,
    runtime_config.WINDOW_ENDPOINTS_COLLECTION_SCOPE,
}
VALID_SCRIPT_OUTPUTS = {"plain_text", "table_json"}
IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")
REPORT_ITEM_LINK_RE = re.compile(
    r"\[([a-z][a-z0-9_.-]*)\]\(#item-([a-z][a-z0-9_.-]*)\)"
)
REPORT_ITEM_FRAGMENT_LINK_RE = re.compile(r"\[([^\]\n]+)\]\(#item-([^\s)]*)\)")
REPORT_ITEM_LINK_LINE_RE = re.compile(
    r"- \[([a-z][a-z0-9_.-]*)\]\(#item-\1\) — \S.*"
)
REQUIRED_INSTRUCTION_HEADINGS = (
    "## What this item shows",
    "## What to watch",
    "## Common fault causes",
    "## Automatic evaluation",
    "## Checklist",
)
REQUIRED_RESOLVED_FIELD_REFERENCE_PATHS = {
    "resolved",
    "resolved/item_id",
    "resolved/title",
    "resolved/source_kind",
    "resolved/source_id",
    "resolved/state",
    "resolved/database_scope",
    "resolved/tags",
    "resolved/tags[]",
    "resolved/render",
    "resolved/render/empty_message",
    "resolved/display",
    "resolved/display/default_sort",
    "resolved/display/default_sort/column",
    "resolved/display/default_sort/direction",
    "resolved/variant_id",
    "resolved/sql_file",
    "resolved/collection_scope",
}


def validate_content(content: ContentPack) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not _validate_content_shapes(content, issues):
        return issues
    _validate_schema_versions(content, issues)
    _validate_unified_document(content, issues)
    _validate_field_reference(content, issues)
    _validate_presentation_catalog(content, issues)
    _validate_report_contract(content, issues)
    _validate_report_items(content, issues)
    _validate_query_manifests(content, issues)
    _validate_scripts(content, issues)
    _validate_python_sources(content, issues)
    _validate_sampler_providers(content, issues)
    _validate_metrics(content, issues)
    _validate_instructions(content, issues)
    _validate_sql_files(content, issues)
    return issues


def has_errors(issues: list[ValidationIssue]) -> bool:
    return any(issue.level == "error" for issue in issues)


def _issue(
    issues: list[ValidationIssue], code: str, message: str, location: str, level: str = "error"
) -> None:
    issues.append(ValidationIssue(level=level, code=code, message=message, location=location))


def _validate_content_shapes(content: ContentPack, issues: list[ValidationIssue]) -> bool:
    valid = True
    mapping_fields = {
        "report": content.report,
        "query_catalog": content.query_catalog,
        "script_catalog": content.script_catalog,
        "metric_catalog": content.metric_catalog,
        "python_catalog": content.python_catalog,
        "field_reference_catalog": content.field_reference_catalog,
        "presentation_catalog": content.presentation_catalog,
        "queries": content.queries,
        "scripts": content.scripts,
        "metrics": content.metrics,
        "pythons": content.pythons,
        "sampler_providers": content.sampler_providers,
        "instructions": content.instructions,
        "document": content.document,
        "provenance": content.provenance,
    }
    for name, value in mapping_fields.items():
        if not isinstance(value, dict):
            _issue(issues, "structure", f"Content field {name!r} must be a mapping", name)
            valid = False

    if not valid:
        return False

    nested_mappings = [
        (content.report.get("report"), "report.yaml:report"),
        (content.report.get("runtime_policy"), "report.yaml:runtime_policy"),
        (content.report.get("defaults"), "report.yaml:defaults"),
        (content.report.get("sections"), "report.yaml:sections"),
        (content.query_catalog.get("query_catalog"), "queries.yaml:query_catalog"),
        (content.script_catalog.get("script_catalog"), "scripts.yaml:script_catalog"),
        (content.metric_catalog.get("metric_catalog"), "metrics.yaml:metric_catalog"),
        (content.python_catalog.get("python_catalog"), "python.yaml:python_catalog"),
        (
            content.field_reference_catalog.get("field_reference"),
            "field_reference.yaml:field_reference",
        ),
    ]
    for value, location in nested_mappings:
        if not isinstance(value, dict):
            _issue(issues, "structure", "Value must be a mapping", location)
            valid = False

    report_meta = content.report.get("report")
    if isinstance(report_meta, dict):
        catalogs = report_meta.get("catalogs")
        if not isinstance(catalogs, dict):
            _issue(issues, "structure", "Value must be a mapping", "report.yaml:report.catalogs")
            valid = False
    for catalog, root_key, location in (
        (content.query_catalog, "query_catalog", "queries.yaml:query_catalog.defaults"),
        (content.script_catalog, "script_catalog", "scripts.yaml:script_catalog.defaults"),
        (content.metric_catalog, "metric_catalog", "metrics.yaml:metric_catalog.defaults"),
        (content.python_catalog, "python_catalog", "python.yaml:python_catalog.defaults"),
    ):
        metadata = catalog.get(root_key)
        if isinstance(metadata, dict):
            defaults = metadata.get("defaults")
            if not isinstance(defaults, dict):
                _issue(issues, "structure", "Value must be a mapping", location)
                valid = False

    sections = content.report.get("sections")
    if isinstance(sections, dict):
        for section_id, section in sections.items():
            location = f"report.yaml:sections.{section_id}"
            if not isinstance(section, dict):
                _issue(issues, "structure", "Report section must be a mapping", location)
                valid = False
                continue
            items = section.get("items")
            if not isinstance(items, dict):
                _issue(issues, "structure", "Report section items must be a mapping", location)
                valid = False
                continue
            for item_key, item in (items or {}).items():
                if not isinstance(item, dict):
                    _issue(
                        issues,
                        "structure",
                        "Report item must be a mapping",
                        f"{location}.items.{item_key}",
                    )
                    valid = False

    for label, manifests in (
        ("query", content.queries),
        ("script", content.scripts),
        ("metric", content.metrics),
        ("python", content.pythons),
    ):
        for source_id, manifest in manifests.items():
            if not isinstance(source_id, str) or not source_id:
                _issue(issues, "structure", f"{label} id must be a non-empty string", label)
                valid = False
            if not isinstance(manifest, dict):
                _issue(issues, "structure", f"{label} manifest must be a mapping", f"{label}:{source_id}")
                valid = False
                continue
            title = manifest.get("title")
            if not isinstance(title, str) or not title.strip():
                _issue(
                    issues,
                    "structure",
                    f"{label} manifest must define a non-empty title",
                    f"{label}:{source_id}",
                )
                valid = False
    return valid


def _validate_unified_document(content: ContentPack, issues: list[ValidationIssue]) -> None:
    expected_roots = {
        "report": content.report.get("report") or {},
        "runtime_policy": content.report.get("runtime_policy") or {},
        "defaults": content.report.get("defaults") or {},
        "sections": content.report.get("sections") or {},
        "queries": content.queries,
        "scripts": content.scripts,
        "metrics": content.metrics,
        "python_sources": content.pythons,
    }
    for root, expected in expected_roots.items():
        if content.document.get(root) != expected:
            _issue(
                issues,
                "content_document",
                f"Unified content root {root!r} is inconsistent with the loaded catalog",
                f"content.document:{root}",
            )
    for path, sources in content.provenance.items():
        if (
            not isinstance(path, str)
            or not path
            or path.startswith("/")
            or "//" in path
            or not isinstance(sources, list)
            or not sources
            or any(not isinstance(source, str) or not source for source in sources)
        ):
            _issue(
                issues,
                "content_provenance",
                "Provenance must map canonical relative paths to non-empty source-file lists",
                f"content.provenance:{path}",
            )


def _validate_field_reference(content: ContentPack, issues: list[ValidationIssue]) -> None:
    reference = content.field_reference_catalog.get("field_reference") or {}
    if reference.get("schema_version") != 1:
        _issue(
            issues,
            "field_reference",
            "field_reference.schema_version must be 1",
            "field_reference.yaml:field_reference",
        )
    fields = reference.get("fields")
    if not isinstance(fields, dict) or not fields:
        _issue(
            issues,
            "field_reference",
            "field_reference.fields must be a non-empty mapping",
            "field_reference.yaml:field_reference.fields",
        )
        return
    if "*" in fields:
        _issue(
            issues,
            "field_reference",
            "field_reference.fields must not contain a catch-all '*' entry",
            "field_reference.yaml:field_reference.fields",
        )
    for path, description in fields.items():
        if not isinstance(path, str) or not path or not isinstance(description, str) or not description.strip():
            _issue(
                issues,
                "field_reference",
                "Field-reference paths and descriptions must be non-empty strings",
                "field_reference.yaml:field_reference.fields",
            )
            break

    patterns = [path.split("/") for path in fields if path != "*"]
    paths_requiring_help = _unified_document_paths(content.document).union(
        REQUIRED_RESOLVED_FIELD_REFERENCE_PATHS
    )
    missing = sorted(
        path
        for path in paths_requiring_help
        if not any(_field_reference_pattern_matches(pattern, path.split("/")) for pattern in patterns)
    )
    if missing:
        preview = ", ".join(missing[:8])
        suffix = f" and {len(missing) - 8} more" if len(missing) > 8 else ""
        _issue(
            issues,
            "field_reference",
            f"Missing field-reference entries for: {preview}{suffix}",
            "field_reference.yaml:field_reference.fields",
        )


def _field_reference_pattern_matches(pattern: list[str], path: list[str]) -> bool:
    return len(pattern) == len(path) and all(
        expected == "*" or expected == actual
        for expected, actual in zip(pattern, path)
    )


def _validate_presentation_catalog(
    content: ContentPack,
    issues: list[ValidationIssue],
) -> None:
    catalog = content.presentation_catalog.get("presentation_catalog") or {}
    location = "presentation.yaml:presentation_catalog"
    required_lists = (
        "descriptor_fields",
        "value_kinds",
        "semantic_roles",
        "qualities",
        "encodings",
        "cell_statuses",
        "rules",
    )
    required_mappings = (
        "units",
        "unit_aliases",
        "quantity_aliases",
        "unit_values",
        "label_terms",
        "type_defaults",
        "source_overrides",
    )
    for key in required_lists:
        value = catalog.get(key)
        if not isinstance(value, list) or (key != "rules" and not value):
            _issue(
                issues,
                "presentation",
                f"presentation_catalog.{key} must be a non-empty list",
                location,
            )
    for key in required_mappings:
        value = catalog.get(key)
        if not isinstance(value, dict) or (key not in {"source_overrides"} and not value):
            _issue(
                issues,
                "presentation",
                f"presentation_catalog.{key} must be a mapping",
                location,
            )

    units = catalog.get("units") or {}
    for alias, canonical in (catalog.get("unit_aliases") or {}).items():
        if canonical not in units:
            _issue(
                issues,
                "presentation_unit",
                f"Unit alias {alias!r} references unknown unit {canonical!r}",
                location,
            )
    for index, rule in enumerate(catalog.get("rules") or []):
        if not isinstance(rule, dict) or not isinstance(rule.get("match"), dict) or not isinstance(rule.get("descriptor"), dict):
            _issue(
                issues,
                "presentation_rule",
                "Each presentation rule must define match and descriptor mappings",
                f"{location}.rules[{index}]",
            )
            continue
        for key, pattern in rule["match"].items():
            if not str(key).endswith("_regex"):
                continue
            try:
                re.compile(str(pattern))
            except re.error as exc:
                _issue(
                    issues,
                    "presentation_rule",
                    f"Invalid regular expression: {exc}",
                    f"{location}.rules[{index}].match.{key}",
                )

    required_descriptor_fields = set(catalog.get("descriptor_fields") or []) - {"label"}
    for pg_type, descriptor in (catalog.get("type_defaults") or {}).items():
        if not isinstance(descriptor, dict):
            _issue(
                issues,
                "presentation_descriptor",
                f"Type default {pg_type!r} must be a mapping",
                location,
            )
            continue
        missing = required_descriptor_fields.difference(descriptor)
        if missing:
            _issue(
                issues,
                "presentation_descriptor",
                f"Type default {pg_type!r} misses {sorted(missing)!r}",
                location,
            )


def _unified_document_paths(document: dict[str, Any]) -> set[str]:
    paths: set[str] = set()

    def visit(value: Any, path: list[str]) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = [*path, str(key)]
                paths.add("/".join(child_path))
                visit(child, child_path)
        elif isinstance(value, list):
            item_path = [*path[:-1], path[-1] + "[]"]
            paths.add("/".join(item_path))
            for child in value:
                visit(child, item_path)

    for root, value in document.items():
        if root == "field_reference":
            continue
        paths.add(root)
        visit(value, [root])
    return paths


def _validate_report_contract(content: ContentPack, issues: list[ValidationIssue]) -> None:
    report = content.report.get("report") or {}
    allowed_report_keys = {
        "id",
        "title",
        "description",
        "schema_version",
        "catalogs",
        "allowed_item_tags",
    }
    for key in report:
        if key not in allowed_report_keys:
            _issue(
                issues,
                "unknown_key",
                f"Unknown report metadata key {key!r}",
                "report.yaml:report",
            )
    for key in ("id", "title"):
        value = report.get(key)
        if not isinstance(value, str) or not value.strip():
            _issue(issues, "report", f"report.{key} must be a non-empty string", "report.yaml:report")
    allowed_item_tags = report.get("allowed_item_tags")
    if (
        not isinstance(allowed_item_tags, list)
        or not allowed_item_tags
        or any(not isinstance(tag, str) or not tag for tag in allowed_item_tags)
        or len(set(allowed_item_tags)) != len(allowed_item_tags)
    ):
        _issue(
            issues,
            "report",
            "report.allowed_item_tags must be a non-empty list of unique strings",
            "report.yaml:report",
        )

    catalogs = report.get("catalogs")
    if isinstance(catalogs, dict):
        for key in (
            "queries",
            "scripts",
            "metrics",
            "python",
            "instructions",
            "field_reference",
            "presentation",
        ):
            value = catalogs.get(key)
            if not isinstance(value, str) or not value.strip():
                _issue(
                    issues,
                    "report",
                    f"report.catalogs.{key} must be a non-empty relative path",
                    "report.yaml:report.catalogs",
                )

    policy = content.report.get("runtime_policy") or {}
    if not isinstance(policy, dict):
        return
    fail_fast = policy.get("fail_fast")
    if not isinstance(fail_fast, bool):
        _issue(issues, "runtime_policy", "runtime_policy.fail_fast must be boolean", "report.yaml")
    for key in ("default_sql_timeout_ms", "default_shell_timeout_ms"):
        if not _is_positive_number(policy.get(key)):
            _issue(issues, "runtime_policy", f"runtime_policy.{key} must be positive", "report.yaml")
    shell_timeout_ms = policy.get("default_shell_timeout_ms")
    max_host_timeout_ms = runtime_config.HOST_COMMAND_TIMEOUT_SECONDS * 1000
    if _is_positive_number(shell_timeout_ms) and float(shell_timeout_ms) > max_host_timeout_ms:
        _issue(
            issues,
            "runtime_policy",
            f"runtime_policy.default_shell_timeout_ms must not exceed {max_host_timeout_ms:g}",
            "report.yaml",
        )
    remote_message = policy.get("remote_db_only_shell_message")
    if not isinstance(remote_message, str) or not remote_message.strip():
        _issue(
            issues,
            "runtime_policy",
            "runtime_policy.remote_db_only_shell_message must be a non-empty string",
            "report.yaml",
        )
    if policy.get("table_columns") != "dynamic_from_result":
        _issue(
            issues,
            "runtime_policy",
            "runtime_policy.table_columns must be 'dynamic_from_result'",
            "report.yaml",
        )
    query_text_catalog = policy.get("query_text_catalog")
    if not isinstance(query_text_catalog, dict):
        _issue(
            issues,
            "runtime_policy",
            "runtime_policy.query_text_catalog must be a mapping",
            "report.yaml",
        )
    else:
        id_suffix = query_text_catalog.get("id_column_suffix")
        remove_suffix = query_text_catalog.get("value_column_remove_suffix")
        if not isinstance(id_suffix, str) or not id_suffix:
            _issue(
                issues,
                "runtime_policy",
                "query_text_catalog.id_column_suffix must be a non-empty string",
                "report.yaml",
            )
        if not isinstance(remove_suffix, str) or not remove_suffix:
            _issue(
                issues,
                "runtime_policy",
                "query_text_catalog.value_column_remove_suffix must be a non-empty string",
                "report.yaml",
            )
        elif isinstance(id_suffix, str) and not id_suffix.endswith(remove_suffix):
            _issue(
                issues,
                "runtime_policy",
                "query_text_catalog.id_column_suffix must end with value_column_remove_suffix",
                "report.yaml",
            )

    defaults = content.report.get("defaults") or {}
    for group in ("table", "item", "section", "database_scope_presentation"):
        value = defaults.get(group)
        if not isinstance(value, dict):
            _issue(issues, "defaults", f"defaults.{group} must be a mapping", "report.yaml")
    table_defaults = defaults.get("table") if isinstance(defaults.get("table"), dict) else {}
    page_size = table_defaults.get("page_size")
    if (
        not isinstance(page_size, int) or isinstance(page_size, bool) or page_size <= 0
    ):
        _issue(issues, "defaults", "defaults.table.page_size must be a positive integer", "report.yaml")
    for group in ("item", "section"):
        group_defaults = defaults.get(group) if isinstance(defaults.get(group), dict) else {}
        state = group_defaults.get("state")
        if not _is_valid_state(state):
            _issue(issues, "state", f"defaults.{group}.state has an unsupported value", "report.yaml")
    item_defaults = defaults.get("item") if isinstance(defaults.get("item"), dict) else {}
    if item_defaults.get("database_scope") is None:
        _issue(
            issues,
            "database_scope",
            "defaults.item.database_scope is required",
            "report.yaml:defaults.item",
        )
    _validate_database_scope(
        item_defaults.get("database_scope"),
        issues,
        "report.yaml:defaults.item",
    )
    _validate_database_scope_presentation(defaults, issues)

    sections = content.report.get("sections") or {}
    if not sections:
        _issue(issues, "sections", "Report must define at least one section", "report.yaml:sections")
    item_ids: set[str] = set()
    for section_id, section in sections.items():
        location = f"report.yaml:sections.{section_id}"
        if not isinstance(section_id, str) or not IDENTIFIER_RE.fullmatch(section_id):
            _issue(issues, "identifier", f"Invalid section id {section_id!r}", location)
        state = section.get("state")
        if state is not None and not _is_valid_state(state):
            _issue(issues, "state", "Section state has an unsupported value", location)
        title = section.get("title")
        if title is not None and (not isinstance(title, str) or not title.strip()):
            _issue(issues, "section", "Section title must be a non-empty string", location)
        show_database_scope = section.get("show_database_scope")
        if show_database_scope is not None and not isinstance(show_database_scope, bool):
            _issue(
                issues,
                "database_scope",
                "Section show_database_scope must be boolean",
                location,
            )
        for item_key in (section.get("items") or {}):
            item_location = f"{location}.items.{item_key}"
            if not isinstance(item_key, str) or not IDENTIFIER_RE.fullmatch(item_key):
                _issue(issues, "identifier", f"Invalid report item key {item_key!r}", item_location)
            item_id = f"{section_id}.{item_key}"
            if item_id in item_ids:
                _issue(issues, "identifier", f"Duplicate report item id {item_id!r}", item_location)
            item_ids.add(item_id)


def _is_positive_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and value > 0
    )


def _validate_database_scope_presentation(
    defaults: dict[str, Any],
    issues: list[ValidationIssue],
) -> None:
    config = defaults.get("database_scope_presentation")
    location = "report.yaml:defaults.database_scope_presentation"
    if not isinstance(config, dict):
        return
    metadata_field = config.get("metadata_field")
    if not isinstance(metadata_field, str) or not metadata_field:
        _issue(issues, "defaults", "metadata_field must be a non-empty string", location)
    values = config.get("values")
    if not isinstance(values, dict):
        _issue(issues, "defaults", "values must be a mapping", location)
        return
    missing = DATABASE_SCOPES.difference(values)
    if missing:
        _issue(
            issues,
            "defaults",
            f"values must define database scopes: {', '.join(sorted(missing))}",
            location,
        )
    for scope, presentation in values.items():
        value_location = f"{location}.values.{scope}"
        if not isinstance(presentation, dict):
            _issue(issues, "defaults", "scope presentation must be a mapping", value_location)
            continue
        suffix = presentation.get("title_suffix")
        if not isinstance(suffix, str) or not suffix:
            _issue(issues, "defaults", "title_suffix must be a non-empty string", value_location)
        hidden_columns = presentation.get("hidden_columns")
        if not isinstance(hidden_columns, list) or any(
            not isinstance(column, str) or not column for column in hidden_columns
        ):
            _issue(issues, "defaults", "hidden_columns must be a string list", value_location)


def _is_valid_state(value: Any) -> bool:
    return isinstance(value, str) and value in VALID_STATES


def _validate_schema_versions(content: ContentPack, issues: list[ValidationIssue]) -> None:
    report_schema = (content.report.get("report") or {}).get("schema_version")
    if report_schema != runtime_config.SUPPORTED_CONTENT_SCHEMA_VERSION:
        _issue(issues, "schema_version", "Unsupported report schema version", "report.yaml:report")

    query_schema = (content.query_catalog.get("query_catalog") or {}).get("schema_version")
    if query_schema != runtime_config.SUPPORTED_CONTENT_SCHEMA_VERSION:
        _issue(issues, "schema_version", "Unsupported query catalog schema version", "queries.yaml")

    script_schema = (content.script_catalog.get("script_catalog") or {}).get("schema_version")
    if script_schema != runtime_config.SUPPORTED_CONTENT_SCHEMA_VERSION:
        _issue(issues, "schema_version", "Unsupported script catalog schema version", "scripts.yaml")

    metric_schema = (content.metric_catalog.get("metric_catalog") or {}).get("schema_version")
    if metric_schema != runtime_config.SUPPORTED_CONTENT_SCHEMA_VERSION:
        _issue(issues, "schema_version", "Unsupported metric catalog schema version", "metrics.yaml")

    python_schema = (content.python_catalog.get("python_catalog") or {}).get("schema_version")
    if python_schema != runtime_config.SUPPORTED_CONTENT_SCHEMA_VERSION:
        _issue(issues, "schema_version", "Unsupported python catalog schema version", "python.yaml")

    presentation_schema = (
        content.presentation_catalog.get("presentation_catalog") or {}
    ).get("schema_version")
    if presentation_schema != 1:
        _issue(
            issues,
            "schema_version",
            "Unsupported presentation catalog schema version",
            "presentation.yaml",
        )

    for key in content.report:
        if key not in {"report", "runtime_policy", "defaults", "sections"}:
            _issue(issues, "unknown_key", f"Unknown report top-level key {key!r}", "report.yaml")


def _validate_report_items(content: ContentPack, issues: list[ValidationIssue]) -> None:
    allowed_tags = set((content.report.get("report") or {}).get("allowed_item_tags") or [])
    for section_id, item_key, item_id, item in iter_report_items(content):
        source_keys = SOURCE_KEYS.intersection(item)
        location = f"report.yaml:sections.{section_id}.items.{item_key}"
        if len(source_keys) != 1:
            _issue(
                issues,
                "item_source",
                "Report item must contain exactly one source key: query, script, metric, or python",
                location,
            )
            continue
        source_key = next(iter(source_keys))
        source_id = item.get(source_key)
        if not isinstance(source_id, str) or not source_id.strip():
            _issue(
                issues,
                "item_source",
                f"Report item {source_key} reference must be a non-empty string",
                location,
            )
            continue
        forbidden = FORBIDDEN_LAYOUT_KEYS.intersection(item)
        if forbidden:
            _issue(
                issues,
                "layout_columns",
                f"Report item must not define table columns: {sorted(forbidden)}",
                location,
            )
        _validate_report_item_tags(item, allowed_tags, issues, location)
        _validate_report_item_render(item, issues, location)
        state = item.get("state")
        if state is not None and not _is_valid_state(state):
            _issue(issues, "state", "Report item state has an unsupported value", location)
        title = item.get("title")
        if title is not None and (not isinstance(title, str) or not title.strip()):
            _issue(issues, "item_title", "Report item title must be a non-empty string", location)
        _validate_database_scope(item.get("database_scope"), issues, location)

        if source_key == "query" and source_id not in content.queries:
            _issue(issues, "missing_query", f"Unknown query id {source_id!r}", location)
        if source_key == "script" and source_id not in content.scripts:
            _issue(issues, "missing_script", f"Unknown script id {source_id!r}", location)
        if source_key == "metric" and source_id not in content.metrics:
            _issue(issues, "missing_metric", f"Unknown metric id {source_id!r}", location)
        if source_key == "python" and source_id not in content.pythons:
            _issue(issues, "missing_python", f"Unknown python source id {source_id!r}", location)


def _validate_report_item_tags(
    item: dict[str, Any],
    allowed_tags: set[str],
    issues: list[ValidationIssue],
    location: str,
) -> None:
    tags = item.get("tags")
    if not isinstance(tags, list) or not tags:
        _issue(issues, "item_tags", "Report item must define at least one tag", location)
        return

    seen: set[str] = set()
    for tag in tags:
        if not isinstance(tag, str) or not tag:
            _issue(issues, "item_tags", "Report item tags must be non-empty strings", location)
            continue
        if tag in seen:
            _issue(issues, "item_tags", f"Duplicate report item tag {tag!r}", location)
        seen.add(tag)
        if tag not in allowed_tags:
            _issue(issues, "item_tags", f"Unknown report item tag {tag!r}", location)


def _validate_report_item_render(
    item: dict[str, Any],
    issues: list[ValidationIssue],
    location: str,
) -> None:
    render = item.get("render")
    if render is None:
        return
    if not isinstance(render, dict):
        _issue(issues, "render", "Report item render must be a mapping", location)
        return
    allowed_keys = {"empty_message"}
    for key in render:
        if key not in allowed_keys:
            _issue(issues, "render", f"Unknown report item render key {key!r}", location)
    empty_message = render.get("empty_message")
    if empty_message is not None and (not isinstance(empty_message, str) or not empty_message.strip()):
        _issue(issues, "render", "render.empty_message must be a non-empty string", location)


def _validate_query_manifests(content: ContentPack, issues: list[ValidationIssue]) -> None:
    sql_root = (content.query_catalog.get("query_catalog") or {}).get("sql_root")
    try:
        sql_root_path = resolve_under(content.path, sql_root, "SQL root")
    except ContentLoadError as exc:
        _issue(issues, "sql_root", str(exc), "queries.yaml:query_catalog.sql_root")
        return
    for query_id, manifest in content.queries.items():
        location = f"query:{query_id}"
        variants_value = manifest.get("variants")
        if not isinstance(variants_value, list) or not variants_value:
            _issue(issues, "variants", "Query manifest must define at least one variant", location)
            continue
        variants = variants_value

        collection = manifest.get("collection") or {}
        if not isinstance(collection, dict):
            _issue(issues, "collection", "collection must be a mapping", location)
            collection = {}
        default_collection = collection.get("default")
        supports = collection.get("supports") or []
        if not isinstance(supports, list) or any(
            not isinstance(scope, str) or scope not in VALID_COLLECTION_SCOPES
            for scope in supports
        ):
            _issue(
                issues,
                "collection",
                "collection.supports must contain only once, every_snapshot, and window_endpoints",
                location,
            )
            supports = []
        if not isinstance(default_collection, str) or default_collection not in VALID_COLLECTION_SCOPES:
            _issue(issues, "collection", "collection.default has an unsupported value", location)
        elif default_collection not in supports:
            _issue(
                issues,
                "collection",
                "collection.default must be included in collection.supports",
                location,
            )

        requirements = manifest.get("requirements") or {}
        if not isinstance(requirements, dict):
            _issue(issues, "requirements", "requirements must be a mapping", location)
            requirements = {}
        unsupported_reason = requirements.get("unsupported_versions_reason")
        if unsupported_reason is not None and not isinstance(unsupported_reason, str):
            _issue(
                issues,
                "requirements",
                "requirements.unsupported_versions_reason must be a string",
                location,
            )
        _validate_display_options(manifest, issues, location)
        _validate_evaluation_options(manifest, issues, location)
        optional = manifest.get("optional")
        if optional is not None and not isinstance(optional, bool):
            _issue(issues, "query", "optional must be boolean", location)
        _validate_database_scope(manifest.get("database_scope"), issues, location)

        ranges: list[tuple[int, int, str]] = []
        variant_ids: set[str] = set()
        for index, variant in enumerate(variants):
            if not isinstance(variant, dict):
                _issue(issues, "variant", "Query variant must be a mapping", f"{location}.variants[{index}]")
                continue
            variant_id = variant.get("id", f"variant[{index}]")
            variant_location = f"{location}.variants.{variant_id}"
            if not isinstance(variant.get("id"), str) or not str(variant.get("id") or "").strip():
                _issue(issues, "variant", "Variant id must be a non-empty string", variant_location)
            elif variant["id"] in variant_ids:
                _issue(issues, "variant", f"Duplicate variant id {variant['id']!r}", variant_location)
            else:
                variant_ids.add(variant["id"])
            min_version = variant.get("min_pg_version")
            max_version = variant.get("max_pg_version")
            if not _is_version_number(min_version):
                _issue(issues, "version_range", "min_pg_version must be an integer", variant_location)
                continue
            if max_version is not None and not _is_version_number(max_version):
                _issue(issues, "version_range", "max_pg_version must be an integer", variant_location)
                continue
            min_int = min_version
            max_int = max_version if max_version is not None else 999999
            if min_int > max_int:
                _issue(issues, "version_range", "min_pg_version exceeds max_pg_version", variant_location)
            ranges.append((min_int, max_int, str(variant_id)))

            sql_file = variant.get("sql_file")
            try:
                sql_path = resolve_under(sql_root_path, sql_file, "SQL file")
            except ContentLoadError as exc:
                _issue(issues, "sql_file", str(exc), variant_location)
            else:
                if not sql_path.is_file():
                    _issue(issues, "sql_file", f"SQL file does not exist: {sql_file}", variant_location)

            semantic_columns = variant.get("semantic_columns") or {}
            if not isinstance(semantic_columns, dict):
                _issue(issues, "semantic_columns", "semantic_columns must be a mapping", variant_location)
            else:
                for group, refs in semantic_columns.items():
                    if not isinstance(group, str) or not isinstance(refs, dict):
                        _issue(
                            issues,
                            "semantic_columns",
                            "semantic_columns groups must be named mappings",
                            variant_location,
                        )

            column_statuses = variant.get("column_statuses") or {}
            if not isinstance(column_statuses, dict):
                _issue(
                    issues,
                    "column_statuses",
                    "column_statuses must be a mapping",
                    variant_location,
                )
            else:
                for column_name, status in column_statuses.items():
                    if (
                        not isinstance(column_name, str)
                        or not column_name
                        or not isinstance(status, dict)
                        or status.get("status")
                        not in {"timeout", "error", "permission_denied", "unavailable", "unsupported"}
                        or not isinstance(status.get("reason"), str)
                        or not status["reason"].strip()
                    ):
                        _issue(
                            issues,
                            "column_statuses",
                            "Each column status must define a column, supported status, and reason",
                            variant_location,
                        )
                        continue
                    if any(
                        not isinstance(key, str)
                        or not key
                        or not isinstance(value, str)
                        or not value
                        for key, value in refs.items()
                    ):
                        _issue(
                            issues,
                            "semantic_columns",
                            "semantic_columns references must map non-empty strings to column names",
                            variant_location,
                        )

        for idx, current in enumerate(sorted(ranges)):
            for other in sorted(ranges)[idx + 1 :]:
                if current[1] >= other[0]:
                    _issue(
                        issues,
                        "version_overlap",
                        f"Variant ranges overlap: {current[2]} and {other[2]}",
                        location,
                    )


def _is_version_number(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _validate_display_options(
    manifest: dict[str, Any],
    issues: list[ValidationIssue],
    location: str,
) -> None:
    display = manifest.get("display")
    if display is None:
        return
    if not isinstance(display, dict):
        _issue(issues, "display", "display must be a mapping", location)
        return
    default_sort = display.get("default_sort")
    if default_sort is None:
        return
    if not isinstance(default_sort, dict):
        _issue(issues, "display", "display.default_sort must be a mapping", location)
        return
    column = default_sort.get("column")
    direction = default_sort.get("direction")
    if not isinstance(column, str) or not column:
        _issue(issues, "display", "display.default_sort.column must be a non-empty string", location)
    if not isinstance(direction, str) or direction not in {"asc", "desc"}:
        _issue(issues, "display", "display.default_sort.direction must be asc or desc", location)


def _validate_evaluation_options(
    manifest: dict[str, Any],
    issues: list[ValidationIssue],
    location: str,
) -> None:
    evaluation = manifest.get("evaluation")
    if evaluation is None:
        return
    if not isinstance(evaluation, dict):
        _issue(issues, "evaluation", "evaluation must be a mapping", location)
        return
    allowed_keys = {"summary_title", "recommendation"}
    for key in evaluation:
        if key not in allowed_keys:
            _issue(issues, "evaluation", f"Unknown evaluation key {key!r}", location)
    for key in allowed_keys:
        value = evaluation.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            _issue(issues, "evaluation", f"evaluation.{key} must be a non-empty string", location)


def _validate_scripts(content: ContentPack, issues: list[ValidationIssue]) -> None:
    try:
        scripts_root = resolve_under(content.path, "scripts", "Scripts root")
    except ContentLoadError as exc:  # pragma: no cover - fixed literal root
        _issue(issues, "script_file", str(exc), "scripts.yaml")
        return
    max_host_timeout_ms = runtime_config.HOST_COMMAND_TIMEOUT_SECONDS * 1000
    for script_id, script in content.scripts.items():
        location = f"script:{script_id}"
        script_file = script.get("script_file")
        try:
            script_path = resolve_under(scripts_root, script_file, "Script file")
        except ContentLoadError as exc:
            _issue(issues, "script_file", str(exc), location)
        else:
            if not script_path.is_file():
                _issue(issues, "script_file", f"Script file does not exist: {script_file}", location)
            elif not os.access(script_path, os.X_OK):
                _issue(issues, "script_file", f"Script file is not executable: {script_file}", location)

        output = script.get("output")
        if not isinstance(output, str) or output not in VALID_SCRIPT_OUTPUTS:
            _issue(issues, "script_output", f"Unsupported script output mode {output!r}", location)
        local_only = script.get("local_only")
        if not isinstance(local_only, bool):
            _issue(issues, "script", "local_only must be boolean", location)
        timeout_ms = script.get("timeout_ms")
        if timeout_ms is not None and not _is_positive_number(timeout_ms):
            _issue(issues, "script", "timeout_ms must be positive", location)
        elif timeout_ms is not None and float(timeout_ms) > max_host_timeout_ms:
            _issue(
                issues,
                "script",
                f"timeout_ms must not exceed {max_host_timeout_ms:g} for host shell scripts",
                location,
            )
        remote_behavior = script.get("remote_db_only_behavior")
        if local_only and not isinstance(remote_behavior, dict):
            _issue(
                issues,
                "remote_shell",
                "Local-only script must define remote_db_only_behavior as a mapping",
                location,
            )
        elif local_only:
            _validate_remote_behavior(remote_behavior, issues, location)


def _validate_remote_behavior(
    behavior: Any,
    issues: list[ValidationIssue],
    location: str,
) -> None:
    if not isinstance(behavior, dict):
        _issue(issues, "remote_shell", "remote_db_only_behavior must be a mapping", location)
        return
    status = behavior.get("status")
    if status != "skipped":
        _issue(issues, "remote_shell", "remote_db_only_behavior.status must be skipped", location)
    message_ref = behavior.get("message_ref")
    if not isinstance(message_ref, str) or not message_ref.startswith("runtime_policy."):
        _issue(
            issues,
            "remote_shell",
            "remote_db_only_behavior.message_ref must reference runtime_policy",
            location,
        )
    elif message_ref != "runtime_policy.remote_db_only_shell_message":
        _issue(
            issues,
            "remote_shell",
            "remote_db_only_behavior.message_ref must reference "
            "runtime_policy.remote_db_only_shell_message",
            location,
        )


def _validate_python_sources(content: ContentPack, issues: list[ValidationIssue]) -> None:
    try:
        python_root = resolve_under(content.path, "python", "Python root")
    except ContentLoadError as exc:  # pragma: no cover - fixed literal root
        _issue(issues, "python_file", str(exc), "python.yaml")
        return
    max_host_timeout_ms = runtime_config.HOST_COMMAND_TIMEOUT_SECONDS * 1000
    for python_id, python_source in content.pythons.items():
        location = f"python:{python_id}"
        python_file = python_source.get("python_file")
        path: Path | None = None
        try:
            path = resolve_under(python_root, python_file, "Python source file")
        except ContentLoadError as exc:
            _issue(issues, "python_file", str(exc), location)
        else:
            if not path.is_file():
                _issue(issues, "python_file", f"Python source file does not exist: {python_file}", location)
            elif path.suffix != ".py":
                _issue(issues, "python_file", "Python source file must use .py extension", location)

        function = python_source.get("function")
        if not isinstance(function, str) or not function or not function.isidentifier():
            _issue(issues, "python_function", "Python source manifest must define function", location)
        local_only = python_source.get("local_only")
        if not isinstance(local_only, bool):
            _issue(issues, "python_source", "local_only must be boolean", location)
        if (
            path is not None
            and path.is_file()
            and path.suffix == ".py"
            and isinstance(function, str)
            and function.isidentifier()
        ):
            try:
                module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, UnicodeError, SyntaxError) as exc:
                _issue(
                    issues,
                    "python_function",
                    f"Cannot parse Python source: {exc}",
                    location,
                )
            else:
                definition = next(
                    (
                        node
                        for node in module.body
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and node.name == function
                    ),
                    None,
                )
                if definition is None:
                    _issue(
                        issues,
                        "python_function",
                        f"Python source does not define function {function!r}",
                        location,
                    )
                elif local_only is True and not isinstance(definition, ast.AsyncFunctionDef):
                    _issue(
                        issues,
                        "python_function",
                        "local_only Python source function must be async to use ctx.host",
                        location,
                    )
        timeout_ms = python_source.get("timeout_ms")
        if not _is_positive_number(timeout_ms):
            _issue(issues, "python_source", "timeout_ms must be positive", location)
        elif (
            local_only is True
            and float(timeout_ms) > max_host_timeout_ms
        ):
            _issue(
                issues,
                "python_source",
                f"local_only timeout_ms must not exceed {max_host_timeout_ms:g}",
                location,
            )
        _validate_display_options(python_source, issues, location)


def _validate_sampler_providers(
    content: ContentPack,
    issues: list[ValidationIssue],
) -> None:
    scripts_root = content.path / "scripts"
    seen_outputs: dict[str, str] = {}
    max_grace_ms = runtime_config.HOST_COMMAND_TIMEOUT_SECONDS * 1000
    for provider_id, provider in content.sampler_providers.items():
        location = f"sampler_provider:{provider_id}"
        module = provider.get("module")
        if not isinstance(module, str) or not module or any(
            not part.isidentifier() for part in module.split(".")
        ):
            _issue(issues, "sampler_provider", "module must be a dotted Python name", location)
        function = provider.get("function")
        if not isinstance(function, str) or not function.isidentifier():
            _issue(issues, "sampler_provider", "function must be a Python identifier", location)
        grace_timeout_ms = provider.get("grace_timeout_ms")
        if not _is_positive_number(grace_timeout_ms):
            _issue(issues, "sampler_provider", "grace_timeout_ms must be positive", location)
        elif float(grace_timeout_ms) > max_grace_ms:
            _issue(
                issues,
                "sampler_provider",
                f"grace_timeout_ms must not exceed {max_grace_ms:g}",
                location,
            )
        if not isinstance(provider.get("config"), dict):
            _issue(issues, "sampler_provider", "config must be a mapping", location)

        outputs = provider.get("outputs")
        if not isinstance(outputs, dict) or not outputs:
            _issue(issues, "sampler_provider", "outputs must be a non-empty mapping", location)
            continue
        for output_id, output in outputs.items():
            output_location = f"{location}.outputs.{output_id}"
            if not isinstance(output_id, str) or not output_id:
                _issue(issues, "sampler_provider", "output id must be non-empty", output_location)
                continue
            previous = seen_outputs.get(output_id)
            if previous is not None:
                _issue(
                    issues,
                    "sampler_provider",
                    f"output {output_id!r} is already declared by provider {previous!r}",
                    output_location,
                )
            else:
                seen_outputs[output_id] = provider_id
            if not isinstance(output, dict):
                _issue(issues, "sampler_provider", "output must be a mapping", output_location)
                continue
            scope = output.get("collection_scope")
            if scope not in {
                runtime_config.EVERY_SNAPSHOT_COLLECTION_SCOPE,
                runtime_config.WINDOW_ENDPOINTS_COLLECTION_SCOPE,
            }:
                _issue(
                    issues,
                    "sampler_provider",
                    "collection_scope must be every_snapshot or window_endpoints",
                    output_location,
                )
            source_file = output.get("source_file")
            try:
                source_path = resolve_under(
                    scripts_root,
                    source_file,
                    "Sampler source file",
                )
            except ContentLoadError as exc:
                _issue(issues, "sampler_provider", str(exc), output_location)
            else:
                if not source_path.is_file():
                    _issue(
                        issues,
                        "sampler_provider",
                        f"Sampler source file does not exist: {source_file}",
                        output_location,
                    )
            source_language = output.get("source_language")
            if not isinstance(source_language, str) or not source_language:
                _issue(
                    issues,
                    "sampler_provider",
                    "source_language must be a non-empty string",
                    output_location,
                )


def _sampler_output_registry(content: ContentPack) -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}
    for provider in content.sampler_providers.values():
        for output_id, output in (provider.get("outputs") or {}).items():
            if isinstance(output_id, str) and isinstance(output, dict):
                registry[output_id] = output
    return registry


def _validate_metrics(content: ContentPack, issues: list[ValidationIssue]) -> None:
    sampler_registry = _sampler_output_registry(content)
    for metric_id, metric in content.metrics.items():
        location = f"metric:{metric_id}"
        _validate_database_scope(metric.get("database_scope"), issues, location)
        source_query = metric.get("source_query")
        source_sampler = metric.get("source_sampler")
        if bool(source_query) == bool(source_sampler):
            _issue(
                issues,
                "metric_source",
                "Metric must define exactly one of source_query or source_sampler",
                location,
            )
            continue
        if source_query is not None and (not isinstance(source_query, str) or not source_query):
            _issue(issues, "metric_source", "source_query must be a non-empty string", location)
            continue
        if source_sampler is not None and (not isinstance(source_sampler, str) or not source_sampler):
            _issue(issues, "metric_source", "source_sampler must be a non-empty string", location)
            continue

        series_list = metric.get("series") or []
        if not isinstance(series_list, list):
            _issue(issues, "metric_series", "Metric series must be a list", location)
            series_list = []
        valid_series: list[dict[str, Any]] = []
        for index, series in enumerate(series_list):
            if not isinstance(series, dict):
                _issue(issues, "metric_series", "Metric series entry must be a mapping", f"{location}.series[{index}]")
                continue
            valid_series.append(series)
            color = series.get("color")
            if color and not _is_hex_color(str(color)):
                _issue(issues, "metric_color", f"Invalid series color {color!r}", location)
            optional = series.get("optional")
            if optional is not None and not isinstance(optional, bool):
                _issue(
                    issues,
                    "metric_series",
                    "Metric series optional must be boolean",
                    f"{location}.series[{index}]",
                )
        partition_by = metric.get("partition_by") or []
        if not isinstance(partition_by, list) or any(
            not isinstance(ref, str) or not ref for ref in partition_by
        ):
            _issue(issues, "metric_ref", "partition_by must be a list of non-empty strings", location)
            partition_by = []

        requires_collection = metric.get("requires_collection")
        if requires_collection is not None and requires_collection not in {
            runtime_config.EVERY_SNAPSHOT_COLLECTION_SCOPE,
            runtime_config.WINDOW_ENDPOINTS_COLLECTION_SCOPE,
        }:
            _issue(
                issues,
                "metric_collection",
                "requires_collection must be every_snapshot or window_endpoints when defined",
                location,
            )

        if source_sampler:
            if source_sampler not in sampler_registry:
                _issue(issues, "metric_source", f"Unknown source_sampler {source_sampler!r}", location)
            else:
                expected_scope = sampler_registry[source_sampler].get("collection_scope")
                if requires_collection is not None and requires_collection != expected_scope:
                    _issue(
                        issues,
                        "metric_collection",
                        (
                            f"Sampler {source_sampler!r} uses {expected_scope!r}, "
                            f"not {requires_collection!r}"
                        ),
                        location,
                    )
                is_table = metric.get("result") == "table" or bool(metric.get("table"))
                if is_table and expected_scope != runtime_config.WINDOW_ENDPOINTS_COLLECTION_SCOPE:
                    _issue(
                        issues,
                        "metric_collection",
                        "Sampler-backed tables require a window_endpoints sampler",
                        location,
                    )
                if is_table and requires_collection != runtime_config.WINDOW_ENDPOINTS_COLLECTION_SCOPE:
                    _issue(
                        issues,
                        "metric_collection",
                        "Sampler-backed tables must declare requires_collection: window_endpoints",
                        location,
                    )
                if not is_table and expected_scope == runtime_config.WINDOW_ENDPOINTS_COLLECTION_SCOPE:
                    _issue(
                        issues,
                        "metric_collection",
                        "A window_endpoints sampler cannot produce a repeated chart",
                        location,
                    )
            for series in valid_series:
                if not isinstance(series.get("value_ref"), str) or not series.get("value_ref"):
                    _issue(issues, "metric_ref", "Sampler metric series must define value_ref", location)
            _validate_metric_result_shape(metric, issues, location)
            continue
        if source_query not in content.queries:
            _issue(issues, "metric_source", f"Unknown source_query {source_query!r}", location)
            continue
        query = content.queries[source_query]
        query_scope = query.get("database_scope")
        metric_scope = metric.get("database_scope")
        if metric_scope != query_scope:
            _issue(
                issues,
                "database_scope",
                (
                    f"Metric database_scope {metric_scope!r} must match source query "
                    f"database_scope {query_scope!r}"
                ),
                location,
            )
        collection = query.get("collection") or {}
        if metric.get("requires_collection") in {
            runtime_config.EVERY_SNAPSHOT_COLLECTION_SCOPE,
            runtime_config.WINDOW_ENDPOINTS_COLLECTION_SCOPE,
        }:
            required_scope = metric["requires_collection"]
            if required_scope not in (collection.get("supports") or []):
                _issue(
                    issues,
                    "metric_collection",
                    f"Metric source query must support {required_scope} collection",
                    location,
                )

        supported_variants = []
        for variant in query.get("variants", []) or []:
            if not isinstance(variant, dict) or not _is_version_number(variant.get("min_pg_version")):
                continue
            max_version = variant.get("max_pg_version")
            if max_version is not None and not _is_version_number(max_version):
                continue
            if variant_intersects_supported_window(variant):
                supported_variants.append(variant)
        for ref in partition_by:
            if not _semantic_ref_exists(supported_variants, ref):
                _issue(issues, "metric_ref", f"Unresolvable partition_by ref {ref!r}", location)
        epoch_refs = metric.get("epoch_refs") or []
        if not isinstance(epoch_refs, list) or any(
            not isinstance(ref, str) or not ref for ref in epoch_refs
        ):
            _issue(
                issues,
                "metric_ref",
                "metric epoch_refs must be a list of non-empty strings",
                location,
            )
        else:
            for ref in epoch_refs:
                if not _semantic_ref_exists(supported_variants, ref):
                    _issue(issues, "metric_ref", f"Unresolvable metric epoch_refs ref {ref!r}", location)
        for series in valid_series:
            value_ref = series.get("value_ref")
            if value_ref is not None and (not isinstance(value_ref, str) or not value_ref):
                _issue(issues, "metric_ref", "value_ref must be a non-empty string", location)
            elif value_ref and not _semantic_ref_exists(supported_variants, value_ref):
                _issue(issues, "metric_ref", f"Unresolvable value_ref {value_ref!r}", location)
            name_ref = series.get("name_from_ref")
            if name_ref is not None and (not isinstance(name_ref, str) or not name_ref):
                _issue(issues, "metric_ref", "name_from_ref must be a non-empty string", location)
            elif name_ref and not _semantic_ref_exists(supported_variants, name_ref):
                _issue(issues, "metric_ref", f"Unresolvable name_from_ref {name_ref!r}", location)
        table = metric.get("table") or {}
        if isinstance(table, dict):
            for ref_key in ("key_refs", "epoch_refs"):
                refs = table.get(ref_key) or []
                if not isinstance(refs, list) or any(
                    not isinstance(ref, str) or not ref for ref in refs
                ):
                    _issue(
                        issues,
                        "metric_ref",
                        f"table.{ref_key} must be a list of non-empty strings",
                        location,
                    )
                    continue
                for ref in refs:
                    if not _semantic_ref_exists(supported_variants, ref):
                        _issue(issues, "metric_ref", f"Unresolvable table.{ref_key} ref {ref!r}", location)
            for column in table.get("columns") or []:
                if not isinstance(column, dict):
                    continue
                refs = [column.get("value_ref") or column.get("ref")]
                for key in ("numerator_ref", "denominator_ref"):
                    refs.append(column.get(key))
                for key in ("numerator_refs", "denominator_refs"):
                    value = column.get(key)
                    if isinstance(value, list):
                        refs.extend(value)
                for ref in refs:
                    if isinstance(ref, str) and "." in ref and not _semantic_ref_exists(
                        supported_variants,
                        ref,
                    ):
                        _issue(issues, "metric_ref", f"Unresolvable table column ref {ref!r}", location)
        _validate_metric_result_shape(metric, issues, location)


def _validate_database_scope(
    scope: Any,
    issues: list[ValidationIssue],
    location: str,
) -> None:
    if scope is not None and scope not in DATABASE_SCOPES:
        _issue(
            issues,
            "database_scope",
            "database_scope must be all_databases or current_database",
            location,
        )


def _validate_metric_result_shape(
    metric: dict[str, Any],
    issues: list[ValidationIssue],
    location: str,
) -> None:
    result_kind = metric.get("result")
    if result_kind is not None and result_kind != "table":
        _issue(issues, "metric_result", "Metric result must be table when defined", location)
    for key in ("chart", "table", "top_n", "display"):
        value = metric.get(key)
        if value is not None and not isinstance(value, dict):
            _issue(issues, "metric_result", f"Metric {key} must be a mapping", location)
    table = metric.get("table")
    if isinstance(table, dict):
        columns = table.get("columns") or []
        if not isinstance(columns, list):
            _issue(issues, "metric_result", "Metric table.columns must be a list", location)
        else:
            for index, column in enumerate(columns):
                column_location = f"{location}.table.columns[{index}]"
                if not isinstance(column, dict):
                    _issue(issues, "metric_result", "Metric table column must be a mapping", column_location)
                    continue
                if not isinstance(column.get("name"), str) or not column["name"]:
                    _issue(issues, "metric_result", "Metric table column must define name", column_location)
                if not isinstance(column.get("pg_type"), str) or not column["pg_type"]:
                    _issue(
                        issues,
                        "metric_result",
                        "Metric table column must define its output pg_type",
                        column_location,
                    )
                if "optional" in column and not isinstance(column["optional"], bool):
                    _issue(
                        issues,
                        "metric_result",
                        "Metric table column optional must be boolean",
                        column_location,
                    )
                transform = column.get("transform") or "last"
                if transform not in {
                    "last", "first", "delta", "rate", "pct_delta", "delta_ratio",
                    "sample_count", "sum", "avg", "max",
                }:
                    _issue(
                        issues,
                        "metric_result",
                        f"Unsupported metric table transform {transform!r}",
                        column_location,
                    )
                if transform == "delta_ratio":
                    for prefix in ("numerator", "denominator"):
                        singular = column.get(f"{prefix}_ref")
                        plural = column.get(f"{prefix}_refs")
                        valid_singular = isinstance(singular, str) and bool(singular)
                        valid_plural = (
                            isinstance(plural, list)
                            and bool(plural)
                            and all(isinstance(ref, str) and ref for ref in plural)
                        )
                        if valid_singular == valid_plural:
                            _issue(
                                issues,
                                "metric_result",
                                f"delta_ratio must define exactly one of {prefix}_ref or {prefix}_refs",
                                column_location,
                            )
                    if "scale" in column and not isinstance(column["scale"], (int, float)):
                        _issue(
                            issues,
                            "metric_result",
                            "delta_ratio scale must be numeric",
                            column_location,
                        )
    evaluation = metric.get("evaluation")
    if evaluation is None:
        return
    if not isinstance(evaluation, dict):
        _issue(issues, "metric_evaluation", "Metric evaluation must be a mapping", location)
        return
    rules = evaluation.get("rules") or []
    if not isinstance(rules, list):
        _issue(issues, "metric_evaluation", "Metric evaluation.rules must be a list", location)
        return
    table_columns = {
        str(column.get("name") or "")
        for column in ((metric.get("table") or {}).get("columns") or [])
        if isinstance(column, dict)
    }
    for index, rule in enumerate(rules):
        rule_location = f"{location}.evaluation.rules[{index}]"
        if not isinstance(rule, dict):
            _issue(issues, "metric_evaluation", "Evaluation rule must be a mapping", rule_location)
            continue
        if rule.get("severity") not in {"medium", "high"}:
            _issue(issues, "metric_evaluation", "Rule severity must be medium or high", rule_location)
        conditions = rule.get("all") or []
        if not isinstance(conditions, list) or not conditions:
            _issue(issues, "metric_evaluation", "Rule all must be a non-empty list", rule_location)
            continue
        for condition in conditions:
            if not isinstance(condition, dict):
                _issue(issues, "metric_evaluation", "Rule condition must be a mapping", rule_location)
                continue
            if condition.get("column") not in table_columns:
                _issue(issues, "metric_evaluation", "Rule references an unknown table column", rule_location)
            if condition.get("operator") not in {"gt", "gte", "lt", "lte", "eq"}:
                _issue(issues, "metric_evaluation", "Rule operator is unsupported", rule_location)
            if not isinstance(condition.get("value"), (int, float)):
                _issue(issues, "metric_evaluation", "Rule value must be numeric", rule_location)


def _validate_instructions(content: ContentPack, issues: list[ValidationIssue]) -> None:
    catalogs = (content.report.get("report") or {}).get("catalogs") or {}
    instructions_root = catalogs.get("instructions")
    try:
        instructions_dir = resolve_under(content.path, instructions_root, "Instructions root")
    except ContentLoadError as exc:
        _issue(issues, "instruction_file", str(exc), "report.yaml:report.catalogs.instructions")
        return
    report_item_ids = {
        item_id for _section_id, _item_key, item_id, _item in iter_report_items(content)
    }
    for section_id, item_key, item_id, item in iter_report_items(content):
        location = f"report.yaml:sections.{section_id}.items.{item_key}"
        try:
            instruction_ref = instruction_ref_for_report_item(section_id, item_key, item)
        except Exception as exc:
            _issue(issues, "instruction_file", str(exc), location)
            continue
        if instruction_ref is None:
            if item.get("state") != "hidden":
                _issue(issues, "instruction_file", "Visible report item must define an instruction markdown file", location)
            continue
        try:
            instruction_path = resolve_under(instructions_dir, instruction_ref, "Instruction path")
        except ContentLoadError as exc:
            _issue(issues, "instruction_file", str(exc), location)
            continue
        if instruction_path.suffix.lower() != ".md":
            _issue(issues, "instruction_file", "Instruction file must use .md extension", location)
            continue
        if not instruction_path.is_file():
            _issue(
                issues,
                "instruction_file",
                f"Instruction file does not exist: {instructions_root}/{instruction_ref}",
                location,
            )
            continue
        try:
            instruction_text = instruction_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            _issue(issues, "instruction_file", f"Cannot read instruction file: {exc}", location)
            continue
        if not instruction_text.strip():
            _issue(issues, "instruction_file", "Instruction file must not be empty", location)
            continue
        if item_id not in content.instructions:
            _issue(issues, "instruction_file", "Instruction file was not loaded", location)
        first_line = instruction_text.lstrip().splitlines()[0]
        if not re.fullmatch(r"# [^#\s].*", first_line):
            _issue(
                issues,
                "instruction_contract",
                "Instruction must begin with one level-one Markdown title",
                location,
            )
        ownership_line = f"This instruction belongs to report item `{item_id}`."
        if ownership_line not in instruction_text:
            _issue(
                issues,
                "instruction_contract",
                f"Instruction must contain the exact ownership sentence: {ownership_line}",
                location,
            )
        for heading in REQUIRED_INSTRUCTION_HEADINGS:
            if instruction_text.splitlines().count(heading) != 1:
                _issue(
                    issues,
                    "instruction_contract",
                    f"Instruction must contain exactly one {heading!r} section",
                    location,
                )
        related_targets: list[str] = []
        for match in REPORT_ITEM_FRAGMENT_LINK_RE.finditer(instruction_text):
            exact_match = REPORT_ITEM_LINK_RE.fullmatch(match.group(0))
            if exact_match is None:
                _issue(
                    issues,
                    "instruction_link",
                    "Report item links must use exact [section.item](#item-section.item) syntax",
                    location,
                )
                continue
            label, target = exact_match.groups()
            related_targets.append(target)
            if label != target:
                _issue(
                    issues,
                    "instruction_link",
                    "Related report item link label must equal its report item id",
                    location,
                )
            if target not in report_item_ids:
                _issue(
                    issues,
                    "instruction_link",
                    f"Related report item link references unknown item {target!r}",
                    location,
                )
            if target == item_id:
                _issue(
                    issues,
                    "instruction_link",
                    "Instruction must not link to its own report item",
                    location,
                )
        if len(related_targets) != len(set(related_targets)):
            _issue(
                issues,
                "instruction_link",
                "Related report item links must not contain duplicate targets",
                location,
            )
        related_heading_count = instruction_text.splitlines().count("## Related report items")
        if related_heading_count > 1:
            _issue(
                issues,
                "instruction_contract",
                "Instruction must contain at most one '## Related report items' section",
                location,
            )
        if related_heading_count == 1:
            instruction_lines = instruction_text.splitlines()
            related_start = instruction_lines.index("## Related report items") + 1
            related_end = next(
                (
                    index
                    for index in range(related_start, len(instruction_lines))
                    if instruction_lines[index].startswith("## ")
                ),
                len(instruction_lines),
            )
            related_lines = [
                line for line in instruction_lines[related_start:related_end] if line.strip()
            ]
            if not related_targets:
                _issue(
                    issues,
                    "instruction_link",
                    "Related report items section must contain at least one item link",
                    location,
                )
            if not related_lines or any(
                REPORT_ITEM_LINK_LINE_RE.fullmatch(line) is None for line in related_lines
            ):
                _issue(
                    issues,
                    "instruction_link",
                    "Each related item must be a bullet link followed by an em dash "
                    "and investigation reason",
                    location,
                )


def _is_hex_color(value: str) -> bool:
    if len(value) not in {4, 7} or not value.startswith("#"):
        return False
    return all(char in "0123456789abcdefABCDEF" for char in value[1:])


def _semantic_ref_exists(variants: list[dict[str, Any]], semantic_ref: str) -> bool:
    if not isinstance(semantic_ref, str):
        return False
    parts = semantic_ref.split(".")
    if len(parts) != 2:
        return False
    group, key = parts
    for variant in variants:
        semantic_columns = variant.get("semantic_columns") or {}
        if not isinstance(semantic_columns, dict):
            continue
        refs = semantic_columns.get(group) or {}
        if isinstance(refs, dict) and key in refs:
            return True
    return False


def _validate_sql_files(content: ContentPack, issues: list[ValidationIssue]) -> None:
    try:
        sql_root = resolve_under(
            content.path,
            (content.query_catalog.get("query_catalog") or {}).get("sql_root"),
            "SQL root",
        )
    except ContentLoadError:
        return
    for query_id, manifest in content.queries.items():
        for variant in manifest.get("variants", []) or []:
            if not isinstance(variant, dict):
                continue
            sql_file = variant.get("sql_file")
            if not sql_file:
                continue
            try:
                sql_path = resolve_under(sql_root, sql_file, "SQL file")
            except ContentLoadError:
                continue
            if not sql_path.is_file():
                continue
            try:
                sql_text = sql_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                _issue(
                    issues,
                    "sql_file",
                    f"Cannot read SQL file: {exc}",
                    f"{sql_path.relative_to(content.path)} query_id={query_id}",
                )
                continue
            for lint_issue in lint_sql(sql_text):
                _issue(
                    issues,
                    lint_issue.code,
                    lint_issue.message,
                    f"{sql_path.relative_to(content.path)} query_id={query_id} variant_id={variant.get('id')}",
                )
