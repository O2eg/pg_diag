"""Lightweight artifact validation."""

from __future__ import annotations

import math
import re
from typing import Any

from . import runtime_config
from .contracts import (
    COLLECTION_STATUSES,
    INTERVAL_COVERAGE_STATUSES,
    RESULT_KINDS,
    SEVERITY_LEVELS,
    interval_coverage_totals,
)
from .errors import ValidationError

INTERNAL_TIME_COLUMN = "epoch_ns"
INTERNAL_TAG_PREFIX = "tag_"
INTERNAL_EVALUATION_PREFIX = "pg_diag_internal_"
COLUMN_DESCRIPTOR_FIELDS = {
    "label",
    "value_kind",
    "semantic_role",
    "quality",
    "nullable",
    "encoding",
}
VALUE_KINDS = {"integer", "decimal", "text", "boolean", "timestamp", "date", "time", "lsn", "json"}
SEMANTIC_ROLES = {"identifier", "counter", "counter_delta", "gauge", "rate", "duration", "estimate", "state", "label"}
QUALITIES = {"exact", "estimated", "sampled", "derived"}
ENCODINGS = {"json_number", "decimal_string", "json_string", "json_boolean", "json_value"}
VALUE_ENCODINGS = {
    "integer": {"json_number", "decimal_string"},
    "decimal": {"json_number", "decimal_string"},
    "text": {"json_string"},
    "boolean": {"json_boolean"},
    "timestamp": {"json_string"},
    "date": {"json_string"},
    "time": {"json_string"},
    "lsn": {"json_string"},
    "json": {"json_value"},
}
CELL_STATUSES = {"timeout", "error", "permission_denied", "unavailable", "unsupported"}


def validate_artifact(artifact: dict[str, Any]) -> None:
    required = [
        "artifact_schema_version",
        "generator",
        "content",
        "report",
        "runtime",
        "display",
        "sections",
        "items",
        "query_texts",
        "snapshot_schemas",
        "snapshots",
        "diagnostics",
    ]
    for key in required:
        if key not in artifact:
            raise ValidationError(f"Artifact missing required field {key!r}")
    schema_version = artifact["artifact_schema_version"]
    if schema_version != runtime_config.ARTIFACT_SCHEMA_VERSION:
        raise ValidationError(
            "Unsupported artifact schema version: "
            f"{schema_version}"
        )
    for key in ("generator", "content", "report", "runtime"):
        if not isinstance(artifact[key], dict):
            raise ValidationError(f"Artifact field {key!r} must be a mapping")
    content = artifact["content"]
    if content.get("schema_version") != runtime_config.SUPPORTED_CONTENT_SCHEMA_VERSION:
        raise ValidationError("Artifact content schema version does not match the runtime contract")
    for key in ("content_path", "checksum", "report_id"):
        if not isinstance(content.get(key), str) or not content[key]:
            raise ValidationError(f"Artifact field 'content.{key}' must be a non-empty string")
    content_document = content.get("document")
    if not isinstance(content_document, dict) or not content_document:
        raise ValidationError("Artifact field 'content.document' must be a non-empty mapping")
    field_reference = content_document.get("field_reference")
    if not isinstance(field_reference, dict) or not field_reference:
        raise ValidationError("Artifact field 'content.document.field_reference' must be a non-empty mapping")
    required_document_roots = {
        "report",
        "runtime_policy",
        "defaults",
        "sections",
        "catalogs",
        "queries",
        "scripts",
        "metrics",
        "python_sources",
        "sampler_providers",
        "instructions",
        "field_reference",
    }
    if set(content_document) != required_document_roots:
        raise ValidationError("Artifact field 'content.document' has an invalid root set")
    presentation = ((content_document.get("catalogs") or {}).get("presentation") or {})
    units = presentation.get("units") if isinstance(presentation, dict) else None
    if not isinstance(units, dict) or not units:
        raise ValidationError("Artifact presentation catalog must define a non-empty unit registry")
    content_provenance = content.get("provenance")
    if (
        not isinstance(content_provenance, dict)
        or not content_provenance
        or any(
            not isinstance(path, str)
            or not isinstance(sources, list)
            or any(not isinstance(source, str) or not source for source in sources)
            for path, sources in content_provenance.items()
        )
    ):
        raise ValidationError(
            "Artifact field 'content.provenance' must map paths to source-file lists"
        )
    display = artifact["display"]
    if not isinstance(display, dict):
        raise ValidationError("Artifact field 'display' must be a mapping")
    table_display = display.get("table")
    if not isinstance(table_display, dict):
        raise ValidationError("Artifact field 'display.table' must be a mapping")
    page_size = table_display.get("page_size")
    if page_size is not None and (
        not isinstance(page_size, int) or isinstance(page_size, bool) or page_size <= 0
    ):
        raise ValidationError("Artifact display table page_size must be a positive integer")
    if not isinstance(artifact["sections"], list):
        raise ValidationError("Artifact field 'sections' must be a list")
    if not isinstance(artifact["items"], dict):
        raise ValidationError("Artifact field 'items' must be a mapping")
    referenced_item_ids = _validate_sections(artifact["sections"])
    for item_id, item in artifact["items"].items():
        if not isinstance(item_id, str) or not item_id:
            raise ValidationError("Artifact item ids must be non-empty strings")
        if not isinstance(item, dict):
            raise ValidationError(f"Artifact item {item_id!r} must be a mapping")
        _validate_item_payload(item_id, item, set(units))
        if item.get("item_id") not in (None, item_id):
            raise ValidationError(f"Artifact item key {item_id!r} does not match item_id")
        if not _valid_item_state(item.get("state")):
            raise ValidationError(f"Artifact item {item_id!r} has unsupported state {item.get('state')!r}")

    missing_items = referenced_item_ids.difference(artifact["items"])
    if missing_items:
        raise ValidationError(f"Artifact sections reference missing items: {sorted(missing_items)!r}")

    snapshot_schemas = artifact["snapshot_schemas"]
    _validate_snapshot_schemas(snapshot_schemas, set(units))
    _validate_snapshots(artifact["snapshots"], artifact["items"], snapshot_schemas, set(units))
    _validate_diagnostics(artifact["diagnostics"], "Artifact diagnostics")
    query_texts = artifact["query_texts"]
    if not isinstance(query_texts, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in query_texts.items()
    ):
        raise ValidationError("Artifact field 'query_texts' must map strings to strings")

    _validate_json_data(artifact, "$", set())


def _validate_sections(sections: list[Any]) -> set[str]:
    section_ids: set[str] = set()
    referenced_item_ids: set[str] = set()
    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            raise ValidationError(f"Artifact section at index {index} must be a mapping")
        section_id = section.get("section_id")
        if not isinstance(section_id, str) or not section_id:
            raise ValidationError(f"Artifact section at index {index} has an invalid section_id")
        if section_id in section_ids:
            raise ValidationError(f"Artifact has duplicate section_id {section_id!r}")
        section_ids.add(section_id)
        if not _valid_item_state(section.get("state")):
            raise ValidationError(
                f"Artifact section {section_id!r} has unsupported state {section.get('state')!r}"
            )
        item_ids = section.get("items")
        if not isinstance(item_ids, list) or any(
            not isinstance(item_id, str) or not item_id for item_id in item_ids
        ):
            raise ValidationError(f"Artifact section {section_id!r} items must be a string list")
        if len(item_ids) != len(set(item_ids)):
            raise ValidationError(f"Artifact section {section_id!r} contains duplicate item ids")
        duplicate_refs = referenced_item_ids.intersection(item_ids)
        if duplicate_refs:
            raise ValidationError(f"Artifact items belong to multiple sections: {sorted(duplicate_refs)!r}")
        referenced_item_ids.update(item_ids)
    return referenced_item_ids


def _validate_item_payload(item_id: str, item: dict[str, Any], units: set[str]) -> None:
    for key in ("section_id", "item_key", "title", "source_kind"):
        if not isinstance(item.get(key), str) or not item[key]:
            raise ValidationError(f"Artifact item {item_id!r} field {key!r} must be a non-empty string")
    if not _value_in(item.get("collection_status"), COLLECTION_STATUSES):
        raise ValidationError(
            f"Artifact item {item_id!r} has unsupported collection_status "
            f"{item.get('collection_status')!r}"
        )
    if not _value_in(item.get("severity_level"), SEVERITY_LEVELS):
        raise ValidationError(
            f"Artifact item {item_id!r} has unsupported severity_level {item.get('severity_level')!r}"
        )
    result = item.get("result")
    if not isinstance(result, dict):
        raise ValidationError(f"Artifact item {item_id!r} result must be a mapping")
    _validate_result(item_id, result, units)
    if not isinstance(item.get("source_metadata"), dict):
        raise ValidationError(f"Artifact item {item_id!r} source_metadata must be a mapping")
    if not isinstance(item.get("issues"), dict):
        raise ValidationError(f"Artifact item {item_id!r} issues must be a mapping")
    _validate_diagnostics(item.get("diagnostics"), f"Artifact item {item_id!r} diagnostics")
    reason = item.get("reason")
    if reason is not None and not isinstance(reason, str):
        raise ValidationError(f"Artifact item {item_id!r} reason must be a string or null")
    collected_at = item.get("collected_at")
    if collected_at is not None and (
        not isinstance(collected_at, str) or not collected_at.strip()
    ):
        raise ValidationError(
            f"Artifact item {item_id!r} collected_at must be a non-empty string or null"
        )
    timing_ms = item.get("timing_ms")
    if timing_ms is not None and (
        not isinstance(timing_ms, (int, float)) or isinstance(timing_ms, bool)
    ):
        raise ValidationError(f"Artifact item {item_id!r} timing_ms must be numeric or null")


def _validate_result(item_id: str, result: dict[str, Any], units: set[str]) -> None:
    kind = result.get("kind")
    if not _value_in(kind, RESULT_KINDS):
        raise ValidationError(f"Artifact item {item_id!r} has unsupported result kind {kind!r}")
    if kind == "plain_text" and not isinstance(result.get("data"), str):
        raise ValidationError(f"Artifact plain-text item {item_id!r} data must be a string")
    if kind == "table":
        columns = result.get("columns")
        rows = result.get("rows")
        if not isinstance(columns, list) or not isinstance(rows, list):
            raise ValidationError(f"Artifact table item {item_id!r} must define list columns and rows")
        column_names = []
        for column in columns:
            if not isinstance(column, dict) or not isinstance(column.get("name"), str) or not column["name"]:
                raise ValidationError(f"Artifact table item {item_id!r} has an invalid column")
            _validate_column_descriptor(item_id, column, units)
            column_names.append(column["name"])
        if len(column_names) != len(set(column_names)):
            raise ValidationError(f"Artifact table item {item_id!r} has duplicate column names")
        internal_columns = {
            name
            for name in column_names
            if name == INTERNAL_TIME_COLUMN
            or name.startswith(INTERNAL_TAG_PREFIX)
            or name.startswith(INTERNAL_EVALUATION_PREFIX)
        }
        if internal_columns:
            raise ValidationError(
                f"Artifact table item {item_id!r} exposes internal columns: {sorted(internal_columns)!r}"
            )
        for column in columns:
            for ref in ("unit_ref", "quantity_ref"):
                if ref in column and column[ref] not in column_names:
                    raise ValidationError(
                        f"Artifact table item {item_id!r} {ref} references a missing column"
                    )
        for row in rows:
            if not isinstance(row, list) or len(row) != len(columns):
                raise ValidationError(
                    f"Artifact table item {item_id!r} rows must match the column count"
                )
        status_cells = _validate_table_statuses(item_id, result, columns, rows)
        for row_index, row in enumerate(rows):
            for column_index, column in enumerate(columns):
                _validate_encoded_value(
                    row[column_index],
                    column,
                    f"Artifact table item {item_id!r} row {row_index} column {column['name']!r}",
                    allow_status_null=(row_index, column["name"]) in status_cells,
                )
                unit_ref = column.get("unit_ref")
                if unit_ref and row[column_names.index(unit_ref)] is not None and row[column_names.index(unit_ref)] not in units:
                    raise ValidationError(
                        f"Artifact table item {item_id!r} row {row_index} has an unknown dynamic unit"
                    )
        row_count = result.get("row_count")
        if not isinstance(row_count, int) or isinstance(row_count, bool) or row_count != len(rows):
            raise ValidationError(f"Artifact table item {item_id!r} has an invalid row_count")
        _validate_delta_window(item_id, result.get("delta_window"))
    if kind == "chart":
        series = result.get("series")
        if not isinstance(series, list) or any(not isinstance(entry, dict) for entry in series):
            raise ValidationError(f"Artifact chart item {item_id!r} must define a mapping series list")
        for index, entry in enumerate(series):
            _validate_column_descriptor(f"{item_id}.series[{index}]", entry, units, require_name=False)
            points = entry.get("points")
            if not isinstance(points, list):
                raise ValidationError(f"Artifact chart item {item_id!r} series must define points")
            for point_index, point in enumerate(points):
                if not isinstance(point, dict) or not isinstance(point.get("t"), str):
                    raise ValidationError(f"Artifact chart item {item_id!r} has an invalid point")
                _validate_encoded_value(
                    point.get("value"),
                    entry,
                    f"Artifact chart item {item_id!r} point {point_index}",
                )
        chart = result.get("chart") or {}
        if isinstance(chart, dict) and str(chart.get("kind") or "").startswith("stacked") and series:
            stacked_contracts = {(entry.get("quantity"), entry.get("unit")) for entry in series}
            if len(stacked_contracts) != 1:
                raise ValidationError(
                    f"Artifact chart item {item_id!r} stacks incompatible quantities or units"
                )
    _validate_interval_coverage(item_id, result.get("interval_coverage"))


def _validate_column_descriptor(
    item_id: str,
    column: dict[str, Any],
    units: set[str],
    *,
    require_name: bool = True,
) -> None:
    if require_name and (not isinstance(column.get("name"), str) or not column["name"]):
        raise ValidationError(f"Artifact column in {item_id!r} has no name")
    missing = sorted(field for field in COLUMN_DESCRIPTOR_FIELDS if field not in column)
    if "unit_ref" not in column and "unit" not in column:
        missing.append("unit")
    if "quantity_ref" not in column and "quantity" not in column:
        missing.append("quantity")
    if missing:
        raise ValidationError(
            f"Artifact column in {item_id!r} is missing descriptor fields {sorted(set(missing))!r}"
        )
    if not isinstance(column.get("label"), str) or not column["label"].strip():
        raise ValidationError(f"Artifact column in {item_id!r} has an invalid label")
    if column.get("value_kind") not in VALUE_KINDS:
        raise ValidationError(f"Artifact column in {item_id!r} has an invalid value_kind")
    if column.get("semantic_role") not in SEMANTIC_ROLES:
        raise ValidationError(f"Artifact column in {item_id!r} has an invalid semantic_role")
    if column.get("quality") not in QUALITIES:
        raise ValidationError(f"Artifact column in {item_id!r} has an invalid quality")
    if column.get("encoding") not in ENCODINGS:
        raise ValidationError(f"Artifact column in {item_id!r} has an invalid encoding")
    if column.get("encoding") not in VALUE_ENCODINGS[column["value_kind"]]:
        raise ValidationError(
            f"Artifact column in {item_id!r} has incompatible value_kind and encoding"
        )
    if not isinstance(column.get("nullable"), bool):
        raise ValidationError(f"Artifact column in {item_id!r} nullable must be boolean")
    if "unit" in column and column["unit"] not in units:
        raise ValidationError(
            f"Artifact column in {item_id!r} references unknown unit {column['unit']!r}"
        )
    if "unit" in column and "unit_ref" in column:
        raise ValidationError(f"Artifact column in {item_id!r} defines both unit and unit_ref")
    if "quantity" in column and "quantity_ref" in column:
        raise ValidationError(f"Artifact column in {item_id!r} defines both quantity and quantity_ref")
    for ref in ("unit_ref", "quantity_ref"):
        if ref in column and (not isinstance(column[ref], str) or not column[ref]):
            raise ValidationError(f"Artifact column in {item_id!r} has invalid {ref}")


def _validate_encoded_value(
    value: Any,
    column: dict[str, Any],
    location: str,
    *,
    allow_status_null: bool = False,
) -> None:
    if value is None:
        if not column.get("nullable") and not allow_status_null:
            raise ValidationError(f"Non-nullable value is null at {location}")
        return
    encoding = column["encoding"]
    if encoding == "decimal_string":
        if not isinstance(value, str) or re.fullmatch(r"-?(?:0|[1-9][0-9]*)", value) is None:
            raise ValidationError(f"Invalid decimal_string at {location}")
        return
    if encoding == "json_number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValidationError(f"Invalid json_number at {location}")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValidationError(f"Non-finite json_number at {location}")
        return
    if encoding == "json_string" and not isinstance(value, str):
        raise ValidationError(f"Invalid json_string at {location}")
    if encoding == "json_boolean" and not isinstance(value, bool):
        raise ValidationError(f"Invalid json_boolean at {location}")


def _validate_table_statuses(
    item_id: str,
    result: dict[str, Any],
    columns: list[dict[str, Any]],
    rows: list[list[Any]],
) -> set[tuple[int, str]]:
    column_names = {column["name"] for column in columns}
    cell_statuses = result.get("cell_statuses", [])
    if not isinstance(cell_statuses, list):
        raise ValidationError(f"Artifact table item {item_id!r} cell_statuses must be a list")
    seen_cells: set[tuple[int, str]] = set()
    for entry in cell_statuses:
        if not isinstance(entry, dict):
            raise ValidationError(f"Artifact table item {item_id!r} has an invalid cell status")
        row_index = entry.get("row_index")
        column = entry.get("column")
        if not isinstance(row_index, int) or isinstance(row_index, bool) or not 0 <= row_index < len(rows):
            raise ValidationError(f"Artifact table item {item_id!r} has an invalid cell row_index")
        if column not in column_names:
            raise ValidationError(f"Artifact table item {item_id!r} cell status references a missing column")
        if entry.get("status") not in CELL_STATUSES or not isinstance(entry.get("reason"), str) or not entry["reason"]:
            raise ValidationError(f"Artifact table item {item_id!r} has an invalid cell status payload")
        key = (row_index, str(column))
        if key in seen_cells:
            raise ValidationError(f"Artifact table item {item_id!r} has duplicate cell statuses")
        seen_cells.add(key)
        column_index = next(index for index, value in enumerate(columns) if value["name"] == column)
        if rows[row_index][column_index] is not None:
            raise ValidationError(f"Artifact table item {item_id!r} status cell must contain null")

    column_statuses = result.get("column_statuses", {})
    if not isinstance(column_statuses, dict):
        raise ValidationError(f"Artifact table item {item_id!r} column_statuses must be a mapping")
    for column, entry in column_statuses.items():
        if column not in column_names or not isinstance(entry, dict):
            raise ValidationError(f"Artifact table item {item_id!r} has an invalid column status")
        if entry.get("status") not in CELL_STATUSES or not isinstance(entry.get("reason"), str) or not entry["reason"]:
            raise ValidationError(f"Artifact table item {item_id!r} has an invalid column status payload")
        column_index = next(index for index, value in enumerate(columns) if value["name"] == column)
        if any(row[column_index] is not None for row in rows):
            raise ValidationError(f"Artifact table item {item_id!r} status column must contain only null")
        seen_cells.update((row_index, str(column)) for row_index in range(len(rows)))
    return seen_cells


def _validate_delta_window(item_id: str, window: Any) -> None:
    if window is None:
        return
    if not isinstance(window, dict):
        raise ValidationError(f"Artifact item {item_id!r} delta_window must be a mapping")
    for key in ("start_time", "finish_time"):
        value = window.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(
                f"Artifact item {item_id!r} delta_window.{key} must be a non-empty string"
            )
    duration = window.get("duration_seconds")
    if (
        not isinstance(duration, (int, float))
        or isinstance(duration, bool)
        or duration < 0
    ):
        raise ValidationError(
            f"Artifact item {item_id!r} delta_window.duration_seconds must be non-negative"
        )


def _validate_interval_coverage(item_id: str, coverage: Any) -> None:
    if coverage is None:
        return
    if not isinstance(coverage, dict):
        raise ValidationError(f"Artifact item {item_id!r} interval_coverage must be a mapping")
    values: dict[str, int] = {}
    for key in ("total", "comparable", "unmatched", "invalid"):
        value = coverage.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValidationError(
                f"Artifact item {item_id!r} interval_coverage.{key} must be a non-negative integer"
            )
        values[key] = value
    counts = coverage.get("counts")
    if not isinstance(counts, dict):
        raise ValidationError(f"Artifact item {item_id!r} interval_coverage.counts must be a mapping")
    for status, count in counts.items():
        if status not in INTERVAL_COVERAGE_STATUSES:
            raise ValidationError(
                f"Artifact item {item_id!r} interval_coverage has unknown status {status!r}"
            )
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            raise ValidationError(
                f"Artifact item {item_id!r} interval_coverage count {status!r} must be positive"
            )
    if sum(counts.values()) != values["total"]:
        raise ValidationError(f"Artifact item {item_id!r} interval_coverage counts do not match total")
    expected = interval_coverage_totals(counts)
    if values["comparable"] != expected["comparable"]:
        raise ValidationError(f"Artifact item {item_id!r} interval_coverage comparable count is inconsistent")
    if values["unmatched"] != expected["unmatched"]:
        raise ValidationError(f"Artifact item {item_id!r} interval_coverage unmatched count is inconsistent")
    if values["invalid"] != expected["invalid"]:
        raise ValidationError(f"Artifact item {item_id!r} interval_coverage invalid count is inconsistent")


def _validate_snapshot_schemas(snapshot_schemas: Any, units: set[str]) -> None:
    if not isinstance(snapshot_schemas, dict):
        raise ValidationError("Artifact field 'snapshot_schemas' must be a mapping")
    for item_id, schema in snapshot_schemas.items():
        if not isinstance(item_id, str) or not isinstance(schema, dict):
            raise ValidationError("Artifact snapshot schemas contain an invalid entry")
        columns = schema.get("columns")
        if not isinstance(columns, list):
            raise ValidationError(f"Artifact snapshot schema {item_id!r} must define columns")
        names = []
        for column in columns:
            if not isinstance(column, dict) or not isinstance(column.get("name"), str) or not column["name"]:
                raise ValidationError(f"Artifact snapshot schema {item_id!r} has an invalid column")
            _validate_column_descriptor(item_id, column, units)
            names.append(column["name"])
        if len(names) != len(set(names)):
            raise ValidationError(f"Artifact snapshot schema {item_id!r} has duplicate columns")


def _validate_snapshots(
    snapshots: Any,
    top_level_items: dict[str, Any],
    snapshot_schemas: dict[str, Any],
    units: set[str],
) -> None:
    if not isinstance(snapshots, list):
        raise ValidationError("Artifact field 'snapshots' must be a list")
    for index, snapshot in enumerate(snapshots):
        if not isinstance(snapshot, dict):
            raise ValidationError(f"Artifact snapshot at index {index} must be a mapping")
        if not isinstance(snapshot.get("timestamp"), str) or not snapshot["timestamp"]:
            raise ValidationError(f"Artifact snapshot at index {index} has an invalid timestamp")
        items = snapshot.get("items")
        if not isinstance(items, dict):
            raise ValidationError(f"Artifact snapshot at index {index} items must be a mapping")
        for item_id, item in items.items():
            if not isinstance(item_id, str) or not isinstance(item, dict):
                raise ValidationError(f"Artifact snapshot at index {index} contains an invalid item")
            if not _value_in(item.get("collection_status"), COLLECTION_STATUSES):
                raise ValidationError(
                    f"Artifact snapshot item {item_id!r} has an invalid collection_status"
                )
            result = item.get("result")
            if not isinstance(result, dict):
                raise ValidationError(f"Artifact snapshot item {item_id!r} result must be a mapping")
            if result.get("kind") == "table" and "columns" not in result:
                rows = result.get("rows", [])
                if not isinstance(rows, list) or any(not isinstance(row, list) for row in rows):
                    raise ValidationError(
                        f"Artifact compact table snapshot item {item_id!r} must contain row lists"
                    )
                schema = snapshot_schemas.get(item_id) or {}
                columns = schema.get("columns") or []
                if not columns:
                    top_result = (top_level_items.get(item_id) or {}).get("result") or {}
                    columns = top_result.get("columns") or []
                if rows and not columns:
                    raise ValidationError(
                        f"Artifact compact table snapshot item {item_id!r} has no table schema"
                    )
                if columns and any(len(row) != len(columns) for row in rows):
                    raise ValidationError(
                        f"Artifact compact table snapshot item {item_id!r} rows do not match "
                        "top-level columns"
                    )
                for row_index, row in enumerate(rows):
                    for column_index, column in enumerate(columns):
                        _validate_encoded_value(
                            row[column_index],
                            column,
                            f"Artifact snapshot item {item_id!r} row {row_index}",
                        )
            else:
                _validate_result(item_id, result, units)


def _validate_diagnostics(value: Any, label: str) -> None:
    if not isinstance(value, list) or any(not isinstance(entry, dict) for entry in value):
        raise ValidationError(f"{label} must be a list of mappings")


def _validate_json_data(value: Any, path: str, active_ids: set[int]) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValidationError(f"Artifact is not strict JSON data: non-finite number at {path}")
        return
    if isinstance(value, dict):
        object_id = id(value)
        if object_id in active_ids:
            raise ValidationError(f"Artifact is not strict JSON data: cycle at {path}")
        active_ids.add(object_id)
        try:
            for key, item in value.items():
                if not isinstance(key, str):
                    raise ValidationError(
                        f"Artifact is not strict JSON data: non-string key at {path}"
                    )
                _validate_json_data(item, f"{path}.{key}", active_ids)
        finally:
            active_ids.remove(object_id)
        return
    if isinstance(value, list):
        object_id = id(value)
        if object_id in active_ids:
            raise ValidationError(f"Artifact is not strict JSON data: cycle at {path}")
        active_ids.add(object_id)
        try:
            for index, item in enumerate(value):
                _validate_json_data(item, f"{path}[{index}]", active_ids)
        finally:
            active_ids.remove(object_id)
        return
    raise ValidationError(
        f"Artifact is not strict JSON data: unsupported {type(value).__name__} at {path}"
    )


def _value_in(value: Any, allowed: set[str] | frozenset[str]) -> bool:
    return isinstance(value, str) and value in allowed


def _valid_item_state(value: Any) -> bool:
    return _value_in(value, {"expanded", "collapsed", "hidden"})
