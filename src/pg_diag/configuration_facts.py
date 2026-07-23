"""Extract a compact configuration-tuning contract from a pg_diag report."""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from . import __version__
from .artifact_schema import validate_artifact
from .errors import ValidationError

SCHEMA_VERSION = "pg_diag/configuration-facts-v1"
KIND = "PostgreSQLConfigurationFacts"
CONFIGURATION_ITEM_IDS = (
    "overview.server_version",
    "overview.pg_settings",
    "overview.database_volume",
    "os.total_ram",
    "os.cpu_info",
    "os.disk_usage",
    "os.mounts",
    "os.lshw_disk",
    "cluster_inventory.extensions",
)
CRITICAL_ITEM_IDS = (
    "overview.server_version",
    "overview.pg_settings",
    "os.total_ram",
    "os.cpu_info",
)


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def configuration_facts_hash(facts: dict[str, Any]) -> str:
    stable = json.loads(json.dumps(facts))
    stable.pop("facts_hash", None)
    source = stable.get("source_artifact")
    if isinstance(source, dict):
        source.pop("path", None)
    return _canonical_hash(stable)


def _table_rows(item: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(item, dict) or item.get("collection_status") not in {"ok", "empty"}:
        return []
    result = item.get("result")
    if not isinstance(result, dict) or result.get("kind") != "table":
        return []
    columns = result.get("columns")
    rows = result.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        return []
    names = [column.get("name") for column in columns if isinstance(column, dict)]
    if len(names) != len(columns) or any(not isinstance(name, str) for name in names):
        return []
    return [dict(zip(names, row, strict=False)) for row in rows if isinstance(row, list)]


def _plain_text(item: dict[str, Any] | None) -> str | None:
    if not isinstance(item, dict) or item.get("collection_status") not in {"ok", "empty"}:
        return None
    result = item.get("result")
    if not isinstance(result, dict):
        return None
    if result.get("kind") == "plain_text" and isinstance(result.get("data"), str):
        return result["data"]
    rows = _table_rows(item)
    if rows and rows[0]:
        value = next(iter(rows[0].values()))
        return None if value is None else str(value)
    return None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "on", "true", "yes"}


def _as_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite():
        return None
    return int(number) if number == number.to_integral_value() else float(number)


def _parse_cpu(text: str | None) -> dict[str, Any]:
    fields: dict[str, str] = {}
    for line in (text or "").splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip() and value.strip():
            fields[key.strip()] = value.strip()
    return {
        "logical_cores": _as_int(fields.get("CPU(s)")),
        "sockets": _as_int(fields.get("Socket(s)")),
        "cores_per_socket": _as_int(fields.get("Core(s) per socket")),
        "threads_per_core": _as_int(fields.get("Thread(s) per core")),
        "architecture": fields.get("Architecture"),
        "model_name": fields.get("Model name"),
    }


def _postgresql_major(server_version_num: int | None, version_text: str | None) -> str | None:
    if server_version_num is not None:
        if server_version_num >= 100000:
            return str(server_version_num // 10000)
        return f"{server_version_num // 10000}.{server_version_num // 100 % 100}"
    match = re.search(r"PostgreSQL\s+(\d+)(?:\.(\d+))?", version_text or "")
    if not match:
        return None
    major = int(match.group(1))
    return str(major) if major >= 10 else f"{major}.{match.group(2) or '0'}"


def extract_configuration_facts(
    artifact: dict[str, Any],
    *,
    source_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate a report and extract only facts needed by configuration tooling."""
    validate_artifact(artifact)
    items = artifact["items"]
    missing = [item_id for item_id in CONFIGURATION_ITEM_IDS if item_id not in items]
    failed = [
        item_id
        for item_id in CONFIGURATION_ITEM_IDS
        if item_id in items and items[item_id].get("collection_status") not in {"ok", "empty"}
    ]
    critical_failures = sorted(set(missing + failed).intersection(CRITICAL_ITEM_IDS))

    runtime = artifact.get("runtime") or {}
    version_text = _plain_text(items.get("overview.server_version"))
    version_num = _as_int(runtime.get("server_version_num"))

    settings: dict[str, dict[str, Any]] = {}
    for row in _table_rows(items.get("overview.pg_settings")):
        name = row.get("setting_name")
        if not isinstance(name, str) or not name:
            continue
        settings[name] = {
            "value": row.get("setting_value"),
            "normalized_value": _as_number(row.get("setting_normalized")),
            "normalized_unit": row.get("unit_normalized"),
            "quantity": row.get("quantity_normalized"),
            "source_unit": row.get("source_unit"),
            "source": row.get("source"),
            "context": row.get("context"),
            "pending_restart": _as_bool(row.get("pending_restart")),
            "boot_value": row.get("boot_val"),
            "reset_value": row.get("reset_val"),
            "is_default": _as_bool(row.get("is_default")),
        }

    ram_rows = _table_rows(items.get("os.total_ram"))
    ram_bytes = _as_int(ram_rows[0].get("total_ram_bytes")) if ram_rows else None
    cpu = _parse_cpu(_plain_text(items.get("os.cpu_info")))
    database_sizes = _table_rows(items.get("overview.database_volume"))
    size_values = [
        value
        for value in (_as_int(row.get("database_size_bytes")) for row in database_sizes)
        if value is not None and value >= 0
    ]
    extension_rows = _table_rows(items.get("cluster_inventory.extensions"))
    installed_extensions = sorted(
        str(row["name"])
        for row in extension_rows
        if row.get("name") and _as_bool(row.get("installed"))
    )
    available_extensions = sorted(str(row["name"]) for row in extension_rows if row.get("name"))
    invalid = []
    if version_num is None and not version_text:
        invalid.append("overview.server_version")
    if not settings:
        invalid.append("overview.pg_settings")
    if ram_bytes is None or ram_bytes <= 0:
        invalid.append("os.total_ram")
    if cpu["logical_cores"] is None or cpu["logical_cores"] <= 0:
        invalid.append("os.cpu_info")

    facts: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generator": {"name": "pg_diag", "version": __version__},
        "source_artifact": {
            "path": str(Path(source_path).expanduser().resolve()) if source_path else None,
            "schema_version": artifact.get("artifact_schema_version"),
            "hash": _canonical_hash(artifact),
        },
        "collected_at": runtime.get("started_at"),
        "postgresql": {
            "version": version_text,
            "version_num": version_num,
            "major": _postgresql_major(version_num, version_text),
            "database_size_bytes": sum(size_values) if size_values else None,
            "database_sizes": database_sizes,
            "settings": dict(sorted(settings.items())),
            "installed_extensions": installed_extensions,
            "available_extensions": available_extensions,
        },
        "host": {
            "cpu_cores": cpu["logical_cores"],
            "cpu": cpu,
            "ram_bytes": ram_bytes,
            "filesystems": _table_rows(items.get("os.disk_usage")),
            "mounts": _plain_text(items.get("os.mounts")),
            "disks": _table_rows(items.get("os.lshw_disk")),
        },
        "collection": {
            "item_ids": list(CONFIGURATION_ITEM_IDS),
            "critical_item_ids": list(CRITICAL_ITEM_IDS),
            "missing_item_ids": missing,
            "failed_item_ids": failed,
            "invalid_item_ids": invalid,
            "usable": not critical_failures and not invalid,
        },
    }
    facts["facts_hash"] = configuration_facts_hash(facts)
    validate_configuration_facts(facts)
    return facts


def validate_configuration_facts(facts: Any) -> dict[str, Any]:
    """Apply the small runtime subset of the packaged JSON Schema contract."""
    if not isinstance(facts, dict):
        raise ValidationError("Configuration facts must be a JSON object")
    required_fields = {
        "schema_version",
        "kind",
        "generator",
        "source_artifact",
        "collected_at",
        "postgresql",
        "host",
        "collection",
        "facts_hash",
    }
    if set(facts) != required_fields:
        raise ValidationError("Configuration facts root fields do not match the v1 contract")
    if facts.get("schema_version") != SCHEMA_VERSION or facts.get("kind") != KIND:
        raise ValidationError("Unsupported configuration facts contract")
    for key in ("generator", "source_artifact", "postgresql", "host", "collection"):
        if not isinstance(facts.get(key), dict):
            raise ValidationError(f"Configuration facts field {key!r} must be an object")
    settings = facts["postgresql"].get("settings")
    if not isinstance(settings, dict):
        raise ValidationError("Configuration facts PostgreSQL settings must be an object")
    for field in ("installed_extensions", "available_extensions"):
        values = facts["postgresql"].get(field)
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise ValidationError(f"Configuration facts PostgreSQL {field} must be a string list")
    for field in (
        "item_ids",
        "critical_item_ids",
        "missing_item_ids",
        "failed_item_ids",
        "invalid_item_ids",
    ):
        values = facts["collection"].get(field)
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise ValidationError(f"Configuration facts collection.{field} must be a string list")
    if not isinstance(facts["collection"].get("usable"), bool):
        raise ValidationError("Configuration facts collection.usable must be boolean")
    facts_hash = facts.get("facts_hash")
    if not isinstance(facts_hash, str) or facts_hash != configuration_facts_hash(facts):
        raise ValidationError("Configuration facts hash does not match the artifact")
    return facts


def load_configuration_facts(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Cannot read configuration facts: {exc}") from exc
    return validate_configuration_facts(document)
