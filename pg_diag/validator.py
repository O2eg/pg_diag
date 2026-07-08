"""Content validation for pg_diag."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import runtime_config
from .content_loader import ContentPack, instruction_ref_for_report_item, iter_report_items
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
ALLOWED_ITEM_TAGS = {
    "CPU",
    "Checkpoints",
    "Configuration",
    "Databases",
    "Disk",
    "Filesystem",
    "Functions",
    "Hardware",
    "I/O",
    "Indexes",
    "Kernel",
    "Locks",
    "Maintenance",
    "Memory",
    "Network",
    "Other",
    "Processes",
    "Replication",
    "SQL",
    "Security",
    "Sequences",
    "Sessions",
    "Storage",
    "Tables",
    "Tablespaces",
    "Transactions",
    "Vacuum",
    "WAL",
    "Waits",
}


def validate_content(content: ContentPack) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    _validate_schema_versions(content, issues)
    _validate_report_items(content, issues)
    _validate_query_manifests(content, issues)
    _validate_scripts(content, issues)
    _validate_python_sources(content, issues)
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

    for key in content.report:
        if key not in {"report", "runtime_policy", "defaults", "sections"}:
            _issue(issues, "unknown_key", f"Unknown report top-level key {key!r}", "report.yaml")


def _validate_report_items(content: ContentPack, issues: list[ValidationIssue]) -> None:
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
        forbidden = FORBIDDEN_LAYOUT_KEYS.intersection(item)
        if forbidden:
            _issue(
                issues,
                "layout_columns",
                f"Report item must not define table columns: {sorted(forbidden)}",
                location,
            )
        _validate_report_item_tags(item, issues, location)
        _validate_report_item_render(item, issues, location)

        if "query" in source_keys and item["query"] not in content.queries:
            _issue(issues, "missing_query", f"Unknown query id {item['query']!r}", location)
        if "script" in source_keys and item["script"] not in content.scripts:
            _issue(issues, "missing_script", f"Unknown script id {item['script']!r}", location)
        if "metric" in source_keys and item["metric"] not in content.metrics:
            _issue(issues, "missing_metric", f"Unknown metric id {item['metric']!r}", location)
        if "python" in source_keys and item["python"] not in content.pythons:
            _issue(issues, "missing_python", f"Unknown python source id {item['python']!r}", location)


def _validate_report_item_tags(
    item: dict[str, Any],
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
        if tag not in ALLOWED_ITEM_TAGS:
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
    sql_root = (content.query_catalog.get("query_catalog") or {}).get("sql_root", "queries")
    for query_id, manifest in content.queries.items():
        location = f"query:{query_id}"
        variants = manifest.get("variants") or []
        if not variants:
            _issue(issues, "variants", "Query manifest must define at least one variant", location)
            continue

        collection = manifest.get("collection") or {}
        default_collection = collection.get("default")
        supports = collection.get("supports") or []
        if default_collection not in supports:
            _issue(
                issues,
                "collection",
                "collection.default must be included in collection.supports",
                location,
            )

        requirements = manifest.get("requirements") or {}
        unsupported_reason = requirements.get("unsupported_versions_reason")
        if unsupported_reason is not None and not isinstance(unsupported_reason, str):
            _issue(
                issues,
                "requirements",
                "requirements.unsupported_versions_reason must be a string",
                location,
            )
        _validate_display_options(manifest, issues, location)

        ranges: list[tuple[int, int, str]] = []
        for index, variant in enumerate(variants):
            variant_id = variant.get("id", f"variant[{index}]")
            variant_location = f"{location}.variants.{variant_id}"
            min_version = variant.get("min_pg_version")
            if min_version is None:
                _issue(issues, "version_range", "min_pg_version is required", variant_location)
                continue
            max_version = variant.get("max_pg_version")
            min_int = int(min_version)
            max_int = int(max_version) if max_version is not None else 999999
            if min_int > max_int:
                _issue(issues, "version_range", "min_pg_version exceeds max_pg_version", variant_location)
            ranges.append((min_int, max_int, str(variant_id)))

            sql_file = variant.get("sql_file")
            if not sql_file:
                _issue(issues, "sql_file", "Variant must define sql_file", variant_location)
            else:
                sql_path = content.path / sql_root / sql_file
                if not sql_path.exists():
                    _issue(issues, "sql_file", f"SQL file does not exist: {sql_file}", variant_location)

        for idx, current in enumerate(sorted(ranges)):
            for other in sorted(ranges)[idx + 1 :]:
                if current[1] >= other[0]:
                    _issue(
                        issues,
                        "version_overlap",
                        f"Variant ranges overlap: {current[2]} and {other[2]}",
                        location,
                    )


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
    if direction not in {"asc", "desc"}:
        _issue(issues, "display", "display.default_sort.direction must be asc or desc", location)


def _validate_scripts(content: ContentPack, issues: list[ValidationIssue]) -> None:
    script_defaults = (content.script_catalog.get("script_catalog") or {}).get("defaults") or {}
    default_remote_behavior = script_defaults.get("remote_db_only_behavior")
    for script_id, script in content.scripts.items():
        location = f"script:{script_id}"
        script_file = script.get("script_file")
        if not script_file:
            _issue(issues, "script_file", "Script manifest must define script_file", location)
        elif not (content.path / "scripts" / script_file).exists():
            _issue(issues, "script_file", f"Script file does not exist: {script_file}", location)

        if script.get("local_only", True) and not (
            script.get("remote_db_only_behavior") or default_remote_behavior
        ):
            _issue(
                issues,
                "remote_shell",
                "Local-only script must define remote_db_only_behavior",
                location,
            )


def _validate_python_sources(content: ContentPack, issues: list[ValidationIssue]) -> None:
    for python_id, python_source in content.pythons.items():
        location = f"python:{python_id}"
        python_file = python_source.get("python_file")
        if not python_file:
            _issue(issues, "python_file", "Python source manifest must define python_file", location)
        else:
            path = content.path / "python" / python_file
            if not path.exists():
                _issue(issues, "python_file", f"Python source file does not exist: {python_file}", location)
            elif path.suffix != ".py":
                _issue(issues, "python_file", "Python source file must use .py extension", location)

        function = python_source.get("function")
        if not isinstance(function, str) or not function:
            _issue(issues, "python_function", "Python source manifest must define function", location)


def _validate_metrics(content: ContentPack, issues: list[ValidationIssue]) -> None:
    for metric_id, metric in content.metrics.items():
        location = f"metric:{metric_id}"
        source_query = metric.get("source_query")
        source_sampler = metric.get("source_sampler")
        if source_sampler and not source_query:
            for series in metric.get("series") or []:
                color = series.get("color")
                if color and not _is_hex_color(str(color)):
                    _issue(issues, "metric_color", f"Invalid series color {color!r}", location)
                if not series.get("value_ref"):
                    _issue(issues, "metric_ref", "Sampler metric series must define value_ref", location)
            continue
        if not source_query:
            _issue(issues, "metric_source", "Metric must define source_query or source_sampler", location)
            continue
        if source_query not in content.queries:
            _issue(issues, "metric_source", f"Unknown source_query {source_query!r}", location)
            continue
        query = content.queries[source_query]
        collection = query.get("collection") or {}
        if metric.get("requires_collection") == "every_snapshot":
            if "every_snapshot" not in (collection.get("supports") or []):
                _issue(
                    issues,
                    "metric_collection",
                    "Metric source query must support every_snapshot collection",
                    location,
                )

        supported_variants = [
            variant
            for variant in query.get("variants", []) or []
            if variant_intersects_supported_window(variant)
        ]
        for ref in metric.get("partition_by") or []:
            if not _semantic_ref_exists(supported_variants, ref):
                _issue(issues, "metric_ref", f"Unresolvable partition_by ref {ref!r}", location)
        for series in metric.get("series") or []:
            color = series.get("color")
            if color and not _is_hex_color(str(color)):
                _issue(issues, "metric_color", f"Invalid series color {color!r}", location)
            value_ref = series.get("value_ref")
            if value_ref and not _semantic_ref_exists(supported_variants, value_ref):
                _issue(issues, "metric_ref", f"Unresolvable value_ref {value_ref!r}", location)
            name_ref = series.get("name_from_ref")
            if name_ref and not _semantic_ref_exists(supported_variants, name_ref):
                _issue(issues, "metric_ref", f"Unresolvable name_from_ref {name_ref!r}", location)


def _validate_instructions(content: ContentPack, issues: list[ValidationIssue]) -> None:
    catalogs = (content.report.get("report") or {}).get("catalogs") or {}
    instructions_root = catalogs.get("instructions", "instructions")
    instructions_dir = content.path / instructions_root
    for section_id, item_key, item_id, item in iter_report_items(content):
        location = f"report.yaml:sections.{section_id}.items.{item_key}"
        try:
            instruction_ref = instruction_ref_for_report_item(section_id, item_key, item)
        except Exception as exc:
            _issue(issues, "instruction_file", str(exc), location)
            continue
        if instruction_ref is None:
            _issue(issues, "instruction_file", "Report item must define an instruction markdown file", location)
            continue
        path_ref = Path(instruction_ref)
        if path_ref.is_absolute() or ".." in path_ref.parts:
            _issue(issues, "instruction_file", "Instruction path must stay under the instructions directory", location)
            continue
        if path_ref.suffix.lower() != ".md":
            _issue(issues, "instruction_file", "Instruction file must use .md extension", location)
            continue
        instruction_path = instructions_dir / path_ref
        if not instruction_path.exists():
            _issue(
                issues,
                "instruction_file",
                f"Instruction file does not exist: {instructions_root}/{instruction_ref}",
                location,
            )
            continue
        if not instruction_path.read_text(encoding="utf-8").strip():
            _issue(issues, "instruction_file", "Instruction file must not be empty", location)
            continue
        if item_id not in content.instructions:
            _issue(issues, "instruction_file", "Instruction file was not loaded", location)


def _is_hex_color(value: str) -> bool:
    if len(value) not in {4, 7} or not value.startswith("#"):
        return False
    return all(char in "0123456789abcdefABCDEF" for char in value[1:])


def _semantic_ref_exists(variants: list[dict[str, Any]], semantic_ref: str) -> bool:
    parts = semantic_ref.split(".")
    if len(parts) != 2:
        return False
    group, key = parts
    for variant in variants:
        semantic_columns = variant.get("semantic_columns") or {}
        if key in (semantic_columns.get(group) or {}):
            return True
    return False


def _validate_sql_files(content: ContentPack, issues: list[ValidationIssue]) -> None:
    sql_root = content.path / ((content.query_catalog.get("query_catalog") or {}).get("sql_root", "queries"))
    for query_id, manifest in content.queries.items():
        for variant in manifest.get("variants", []) or []:
            sql_file = variant.get("sql_file")
            if not sql_file:
                continue
            sql_path = sql_root / sql_file
            if not sql_path.exists():
                continue
            sql_text = sql_path.read_text(encoding="utf-8")
            for lint_issue in lint_sql(sql_text):
                _issue(
                    issues,
                    lint_issue.code,
                    lint_issue.message,
                    f"{sql_path.relative_to(content.path)} query_id={query_id} variant_id={variant.get('id')}",
                )
