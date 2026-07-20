"""Resolve content-owned value descriptors and artifact encodings."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import math
import re
from typing import Any

from .content_loader import ContentPack
from .errors import ValidationError


DESCRIPTOR_KEYS = {
    "label",
    "value_kind",
    "semantic_role",
    "quantity",
    "quantity_ref",
    "unit",
    "unit_ref",
    "quality",
    "nullable",
    "encoding",
}
NUMERIC_KINDS = {"integer", "decimal"}
INTEGER_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)$")


def apply_presentation_contract(content: ContentPack, artifact: dict[str, Any]) -> None:
    """Attach complete descriptors and normalize values without item knowledge."""
    catalog = _catalog(content)
    items = artifact.get("items") or {}
    for item_id, item in items.items():
        if not isinstance(item, dict):
            continue
        source_kind = str(item.get("source_kind") or "")
        source_id = _item_source_id(item)
        result = item.get("result") or {}
        if result.get("kind") == "table":
            _resolve_table(
                content,
                catalog,
                result,
                source_kind=source_kind,
                source_id=source_id,
                item_id=str(item_id),
            )
        elif result.get("kind") == "chart":
            _resolve_chart(content, catalog, result, source_id=source_id)

    schemas = artifact.get("snapshot_schemas") or {}
    snapshots = artifact.get("snapshots") or []
    for source_id, schema in schemas.items():
        if not isinstance(schema, dict):
            continue
        sample_rows = _snapshot_rows(snapshots, str(source_id))
        synthetic = {
            "kind": "table",
            "columns": schema.get("columns") or [],
            "rows": sample_rows,
            "row_count": len(sample_rows),
        }
        _resolve_table(
            content,
            catalog,
            synthetic,
            source_kind="query",
            source_id=str(source_id),
            item_id=str(source_id),
        )
        schema["columns"] = synthetic["columns"]

    _normalize_snapshot_rows(artifact)
    artifact.setdefault("display", {})["numeric_locale"] = str(
        catalog.get("numeric_locale") or "en-US"
    )


def resolve_column_descriptor(
    content: ContentPack,
    column: dict[str, Any],
    values: list[Any],
    *,
    source_kind: str,
    source_id: str,
    item_id: str,
) -> dict[str, Any]:
    catalog = _catalog(content)
    name = str(column.get("name") or "").strip()
    if not name:
        raise ValidationError(f"Artifact table {item_id!r} contains a column without a name")
    pg_type = _effective_pg_type(str(column.get("pg_type") or ""), values)
    descriptor = dict((catalog.get("type_defaults") or {}).get(pg_type) or {})
    if not descriptor:
        raise ValidationError(
            f"No presentation type default for {source_id}.{name} physical type {pg_type!r}"
        )

    context = {
        "name": name,
        "pg_type": pg_type,
        "source_kind": source_kind,
        "source_id": source_id,
        "item_id": item_id,
    }
    for rule in catalog.get("rules") or []:
        if isinstance(rule, dict) and _matches(rule.get("match") or {}, context):
            update = rule.get("descriptor") or {}
            if not isinstance(update, dict):
                raise ValidationError("Presentation rule descriptor must be a mapping")
            descriptor.update(update)

    override = ((catalog.get("source_overrides") or {}).get(source_id) or {}).get(name)
    if isinstance(override, dict):
        descriptor.update(override)

    declared = _declared_column(content, source_kind, source_id, name)
    descriptor.update(declared)
    descriptor.update({key: column[key] for key in DESCRIPTOR_KEYS if key in column})
    descriptor["name"] = name
    descriptor["pg_type"] = pg_type
    if column.get("pg_type_oid") is not None:
        descriptor["pg_type_oid"] = column["pg_type_oid"]
    descriptor.setdefault(
        "label",
        _human_label(name, catalog.get("label_terms") or {}, unit=descriptor.get("unit")),
    )
    if "unit_ref" in descriptor:
        descriptor.pop("unit", None)
    if "quantity_ref" in descriptor:
        descriptor.pop("quantity", None)
    _validate_descriptor(descriptor, catalog, f"{source_id}.{name}")
    return descriptor


def _resolve_table(
    content: ContentPack,
    catalog: dict[str, Any],
    result: dict[str, Any],
    *,
    source_kind: str,
    source_id: str,
    item_id: str,
) -> None:
    columns = result.get("columns") or []
    rows = result.get("rows") or []
    if not isinstance(columns, list) or not isinstance(rows, list):
        raise ValidationError(f"Artifact table {item_id!r} has invalid columns or rows")
    resolved = []
    for index, raw_column in enumerate(columns):
        column = dict(raw_column) if isinstance(raw_column, dict) else {"name": str(raw_column)}
        values = [row[index] for row in rows if isinstance(row, list) and index < len(row)]
        resolved.append(
            resolve_column_descriptor(
                content,
                column,
                values,
                source_kind=source_kind,
                source_id=source_id,
                item_id=item_id,
            )
        )
    result["columns"] = resolved
    _normalize_unit_code_columns(result, catalog)
    for row_index, row in enumerate(rows):
        if not isinstance(row, list):
            continue
        for column_index, descriptor in enumerate(resolved):
            if column_index < len(row):
                row[column_index] = _encode_value(
                    row[column_index], descriptor, f"{item_id}[{row_index}].{descriptor['name']}"
                )
    delta_window = result.get("delta_window")
    if isinstance(delta_window, dict):
        delta_window["start_time"] = _normalize_timestamp(delta_window.get("start_time"))
        delta_window["finish_time"] = _normalize_timestamp(delta_window.get("finish_time"))


def _resolve_chart(
    content: ContentPack,
    catalog: dict[str, Any],
    result: dict[str, Any],
    *,
    source_id: str,
) -> None:
    metric = content.metrics.get(source_id) or {}
    raw_chart = result.get("chart") or {}
    raw_chart_unit = raw_chart.get("unit")
    for series in result.get("series") or []:
        if not isinstance(series, dict):
            continue
        raw_unit = series.get("unit") or raw_chart_unit or "none"
        unit = _canonical_unit(raw_unit, catalog)
        quantity = str(
            series.get("quantity")
            or (catalog.get("quantity_aliases") or {}).get(str(raw_unit))
            or _quantity_for_unit(unit)
        )
        transform = _chart_series_transform(metric, series)
        role = (
            "counter_delta"
            if transform == "delta"
            else "rate"
            if transform == "rate" or unit.endswith("/s") or unit in {"iops", "operations/s"}
            else "gauge"
        )
        exact_integer_delta = transform == "delta" and unit in {
            "bits",
            "blocks",
            "bytes",
            "count",
        }
        quality = "sampled" if metric.get("source_sampler") else "derived"
        descriptor = {
            "label": str(series.get("label") or series.get("name") or "Series"),
            "value_kind": "integer" if exact_integer_delta else "decimal",
            "semantic_role": role,
            "quantity": quantity,
            "unit": unit,
            "quality": quality,
            "nullable": True,
            "encoding": "decimal_string" if exact_integer_delta else "json_number",
        }
        descriptor.update({key: series[key] for key in DESCRIPTOR_KEYS if key in series})
        descriptor["unit"] = _canonical_unit(descriptor.get("unit", unit), catalog)
        _validate_descriptor(descriptor, catalog, f"{source_id}.{series.get('name')}")
        series.update(descriptor)
        series["unit"] = descriptor["unit"]
        for point in series.get("points") or []:
            if not isinstance(point, dict):
                continue
            point["t"] = _normalize_timestamp(point.get("t"))
            point["value"] = _encode_value(
                point.get("value"), descriptor, f"{source_id}.{series.get('name')}.point"
            )
    if isinstance(raw_chart, dict):
        raw_chart["unit"] = _canonical_unit(raw_chart_unit or _first_series_unit(result), catalog)
        raw_chart["quantity"] = _first_series_quantity(result)


def _chart_series_transform(metric: dict[str, Any], series: dict[str, Any]) -> str:
    top_n = metric.get("top_n") or {}
    if top_n:
        if top_n.get("operation") == "ratio":
            return "ratio"
        return str(top_n.get("transform") or "rate")

    definitions = metric.get("series") or []
    series_name = str(series.get("name") or "")
    transforms: set[str] = set()
    for definition in definitions:
        if not isinstance(definition, dict):
            continue
        transform = str(definition.get("transform") or "gauge")
        transforms.add(transform)
        base_name = str(
            definition.get("name")
            or definition.get("value_ref")
            or ""
        )
        if base_name and (series_name == base_name or series_name.startswith(base_name + " (")):
            return transform
    return next(iter(transforms)) if len(transforms) == 1 else "gauge"


def _normalize_snapshot_rows(artifact: dict[str, Any]) -> None:
    schemas = artifact.get("snapshot_schemas") or {}
    for snapshot_index, snapshot in enumerate(artifact.get("snapshots") or []):
        if isinstance(snapshot, dict):
            snapshot["timestamp"] = _normalize_timestamp(snapshot.get("timestamp"))
        for item_id, item in (snapshot.get("items") or {}).items():
            result = (item or {}).get("result") or {}
            if result.get("kind") != "table":
                continue
            columns = ((schemas.get(item_id) or {}).get("columns") or [])
            for row_index, row in enumerate(result.get("rows") or []):
                if not isinstance(row, list):
                    continue
                for column_index, descriptor in enumerate(columns):
                    if column_index < len(row):
                        row[column_index] = _encode_value(
                            row[column_index],
                            descriptor,
                            f"snapshot[{snapshot_index}].{item_id}[{row_index}]",
                        )


def _normalize_unit_code_columns(result: dict[str, Any], catalog: dict[str, Any]) -> None:
    columns = result.get("columns") or []
    unit_indexes = [
        index
        for index, descriptor in enumerate(columns)
        if descriptor.get("quantity") == "unit_code"
    ]
    aliases = catalog.get("unit_values") or {}
    for row in result.get("rows") or []:
        if not isinstance(row, list):
            continue
        for index in unit_indexes:
            if index < len(row) and row[index] is not None:
                row[index] = aliases.get(str(row[index]), row[index])


def _encode_value(value: Any, descriptor: dict[str, Any], location: str) -> Any:
    if value is None:
        return None
    encoding = descriptor["encoding"]
    kind = descriptor["value_kind"]
    if encoding == "decimal_string":
        if isinstance(value, bool):
            raise ValidationError(f"Boolean cannot encode as decimal_string at {location}")
        text = str(value).strip()
        if INTEGER_RE.fullmatch(text):
            return text
        try:
            decimal = Decimal(text)
        except InvalidOperation as exc:
            raise ValidationError(
                f"Non-integral decimal_string value {value!r} at {location}"
            ) from exc
        if not decimal.is_finite() or decimal != decimal.to_integral_value():
            raise ValidationError(f"Non-integral decimal_string value {value!r} at {location}")
        return format(decimal, "f").split(".", 1)[0]
    if encoding == "json_number":
        if isinstance(value, bool):
            raise ValidationError(f"Boolean cannot encode as json_number at {location}")
        try:
            number = int(value) if kind == "integer" else float(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"Invalid numeric value {value!r} at {location}") from exc
        if isinstance(number, float) and not math.isfinite(number):
            raise ValidationError(f"Non-finite numeric value at {location}")
        return number
    if encoding == "json_boolean":
        if not isinstance(value, bool):
            raise ValidationError(f"Non-boolean value {value!r} at {location}")
        return value
    if encoding == "json_string":
        text = str(value)
        return _normalize_timestamp(text) if kind == "timestamp" else text
    if encoding == "json_value":
        return value
    raise ValidationError(f"Unknown encoding {encoding!r} at {location}")


def _validate_descriptor(descriptor: dict[str, Any], catalog: dict[str, Any], location: str) -> None:
    required = set(catalog.get("descriptor_fields") or [])
    effective = set(descriptor)
    if "unit_ref" in descriptor:
        required.discard("unit")
    if "quantity_ref" in descriptor:
        required.discard("quantity")
    missing = sorted(required - effective)
    if missing:
        raise ValidationError(f"Descriptor {location} is missing {missing}")
    if descriptor.get("value_kind") not in set(catalog.get("value_kinds") or []):
        raise ValidationError(f"Descriptor {location} has invalid value_kind")
    if descriptor.get("semantic_role") not in set(catalog.get("semantic_roles") or []):
        raise ValidationError(f"Descriptor {location} has invalid semantic_role")
    if descriptor.get("quality") not in set(catalog.get("qualities") or []):
        raise ValidationError(f"Descriptor {location} has invalid quality")
    if descriptor.get("encoding") not in set(catalog.get("encodings") or []):
        raise ValidationError(f"Descriptor {location} has invalid encoding")
    if "unit" in descriptor and descriptor["unit"] not in (catalog.get("units") or {}):
        raise ValidationError(f"Descriptor {location} has unknown unit {descriptor['unit']!r}")
    if not isinstance(descriptor.get("nullable"), bool):
        raise ValidationError(f"Descriptor {location} nullable must be boolean")
    kind = descriptor.get("value_kind")
    encoding = descriptor.get("encoding")
    compatible = {
        "integer": {"json_number", "decimal_string"},
        "decimal": {"json_number", "decimal_string"},
        "boolean": {"json_boolean"},
        "json": {"json_value"},
        "text": {"json_string"},
        "timestamp": {"json_string"},
        "date": {"json_string"},
        "time": {"json_string"},
        "lsn": {"json_string"},
    }
    if encoding not in compatible.get(str(kind), set()):
        raise ValidationError(
            f"Descriptor {location} has incompatible {kind}/{encoding}"
        )


def _declared_column(
    content: ContentPack,
    source_kind: str,
    source_id: str,
    name: str,
) -> dict[str, Any]:
    if source_kind == "metric":
        manifest = content.metrics.get(source_id) or {}
        for column in (manifest.get("table") or {}).get("columns") or []:
            if isinstance(column, dict) and str(column.get("name") or column.get("ref") or "") == name:
                return {key: column[key] for key in DESCRIPTOR_KEYS if key in column}
        return {}
    catalogs = {
        "query": content.queries,
        "script": content.scripts,
        "python": content.pythons,
    }
    manifest = (catalogs.get(source_kind) or {}).get(source_id) or {}
    declared = ((manifest.get("display") or {}).get("columns") or {}).get(name)
    return (
        {key: declared[key] for key in DESCRIPTOR_KEYS if key in declared}
        if isinstance(declared, dict)
        else {}
    )


def _matches(match: dict[str, Any], context: dict[str, str]) -> bool:
    for key, expected in match.items():
        value = context.get(key, "")
        if key.endswith("_regex"):
            field = key.removesuffix("_regex")
            if re.search(str(expected), context.get(field, ""), re.IGNORECASE) is None:
                return False
        elif isinstance(expected, list):
            if value not in {str(entry) for entry in expected}:
                return False
        elif value != str(expected):
            return False
    return True


def _effective_pg_type(pg_type: str, values: list[Any]) -> str:
    normalized = pg_type.lower().strip()
    if normalized.endswith("[]"):
        return "json"
    if normalized not in {"", "json"}:
        return normalized
    non_null = [value for value in values if value is not None]
    if not non_null:
        return normalized or "json"
    if all(isinstance(value, bool) for value in non_null):
        return "bool"
    if all(isinstance(value, int) and not isinstance(value, bool) for value in non_null):
        return "int8"
    if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in non_null):
        return "float8"
    if all(isinstance(value, str) for value in non_null):
        return "text"
    return "json"


def _human_label(name: str, terms: dict[str, Any], *, unit: Any = None) -> str:
    words = []
    for raw in name.strip("_").split("_"):
        if not raw:
            continue
        if unit == "milliseconds" and raw.lower() == "ms":
            continue
        replacement = terms.get(raw.lower())
        words.append(str(replacement) if replacement is not None else raw)
    if not words:
        return name
    label = " ".join(words)
    return label[0].upper() + label[1:]


def _catalog(content: ContentPack) -> dict[str, Any]:
    catalog = content.presentation_catalog.get("presentation_catalog")
    if not isinstance(catalog, dict):
        raise ValidationError("presentation.yaml must define presentation_catalog")
    return catalog


def _item_source_id(item: dict[str, Any]) -> str:
    metadata = item.get("source_metadata") or {}
    source_kind = str(item.get("source_kind") or "")
    keys = {
        "query": ("query_id", "source_query"),
        "script": ("script_id",),
        "metric": ("metric_id",),
        "python": ("python_id",),
    }.get(source_kind, ())
    for key in keys:
        value = metadata.get(key)
        if value:
            return str(value)
    return str(item.get("item_id") or "")


def _snapshot_rows(snapshots: list[Any], item_id: str) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for snapshot in snapshots:
        result = ((((snapshot or {}).get("items") or {}).get(item_id) or {}).get("result") or {})
        for row in result.get("rows") or []:
            if isinstance(row, list):
                rows.append(row)
    return rows


def _canonical_unit(value: Any, catalog: dict[str, Any]) -> str:
    text = str(value or "none")
    unit = str((catalog.get("unit_aliases") or {}).get(text, text))
    if unit not in (catalog.get("units") or {}):
        raise ValidationError(f"Unknown presentation unit {text!r}")
    return unit


def _quantity_for_unit(unit: str) -> str:
    return {
        "bytes": "data_volume",
        "bytes/s": "data_volume",
        "blocks": "blocks",
        "blocks/s": "blocks",
        "milliseconds": "milliseconds",
        "milliseconds/s": "milliseconds",
        "seconds": "seconds",
        "percent": "percentage",
        "ratio": "ratio",
        "hertz": "frequency",
        "bits": "bit_width",
        "bits/s": "bandwidth",
        "load": "load_average",
        "iops": "operations",
        "operations/s": "operations",
        "count": "count",
        "count/s": "count",
    }.get(unit, "measurement")


def _first_series_unit(result: dict[str, Any]) -> str:
    for series in result.get("series") or []:
        if isinstance(series, dict) and series.get("unit"):
            return str(series["unit"])
    return "none"


def _first_series_quantity(result: dict[str, Any]) -> str:
    for series in result.get("series") or []:
        if isinstance(series, dict) and series.get("quantity"):
            return str(series["quantity"])
    return "measurement"


def _normalize_timestamp(value: Any) -> Any:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return text
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return text
    if parsed.tzinfo is None:
        return text
    normalized = parsed.astimezone(timezone.utc).isoformat()
    return normalized.removesuffix("+00:00") + "Z"
