"""Artifact inspection and stable pg_play machine contract for pg_diag."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from . import __version__, runtime_config
from .artifact import artifact_has_errors
from .artifact_schema import validate_artifact
from .errors import ValidationError

CONTRACT_VERSION = "pg_play/component/v1"
CAPABILITY_SCHEMA_VERSION = "pg_play/capabilities/v1"
MACHINE_INTERFACE = {
    "machine_flag": "--machine",
    "request_id_option": "--request-id",
    "capabilities_option": "--component-capabilities",
}
COMPONENT = "pg_diag"

EXIT_CODES = {
    "success": 0,
    "validation_error": 2,
    "precondition_failed": 3,
    "unsupported": 4,
    "partial": 5,
    "execution_error": 6,
    "cancelled": 7,
    "ownership_error": 8,
}


def canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def load_artifact(path: str | Path) -> dict[str, Any]:
    artifact_path = Path(path).expanduser().resolve()
    try:
        document = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Cannot read report artifact {artifact_path}: {exc}") from exc
    if not isinstance(document, dict):
        raise ValidationError("Report artifact root must be a JSON object")
    validate_artifact(document)
    return document


def summarize_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    validate_artifact(artifact)
    items = artifact.get("items") or {}
    collection_statuses = Counter(
        str(item.get("collection_status", "unknown")) for item in items.values()
    )
    severity_levels = Counter(str(item.get("severity_level", "unknown")) for item in items.values())
    diagnostics = artifact.get("diagnostics") or []
    item_diagnostics = sum(
        len(item.get("diagnostics") or []) for item in items.values() if isinstance(item, dict)
    )
    successful = sum(collection_statuses.get(value, 0) for value in ("ok", "empty"))
    total = len(items)
    snapshots = artifact.get("snapshots") or {}
    if isinstance(snapshots, dict):
        snapshot_count = max(
            (len(value) for value in snapshots.values() if isinstance(value, list)),
            default=0,
        )
    elif isinstance(snapshots, list):
        snapshot_count = len(snapshots)
    else:
        snapshot_count = 0
    return {
        "schema_version": "pg_diag/summary-v1",
        "artifact_schema_version": artifact.get("artifact_schema_version"),
        "artifact_hash": canonical_hash(artifact),
        "generator": artifact.get("generator"),
        "report": artifact.get("report"),
        "runtime": artifact.get("runtime"),
        "content": {
            "checksum": (artifact.get("content") or {}).get("checksum"),
            "report_id": (artifact.get("content") or {}).get("report_id"),
        },
        "section_count": len(artifact.get("sections") or []),
        "item_count": total,
        "snapshot_count": snapshot_count,
        "collection_statuses": dict(sorted(collection_statuses.items())),
        "severity_levels": dict(sorted(severity_levels.items())),
        "diagnostic_count": len(diagnostics) + item_diagnostics,
        "completeness": {
            "successful_items": successful,
            "total_items": total,
            "ratio": round(successful / total, 6) if total else 1.0,
        },
        "has_errors": artifact_has_errors(artifact),
    }


def summarize_execution_plan(plan: dict[str, Any]) -> dict[str, Any]:
    items = plan.get("items") or []
    if not isinstance(items, list):
        items = []
    status_counts = Counter(str(item.get("status", "unknown")) for item in items)
    scope_counts = Counter(str(item.get("collection_scope", "unknown")) for item in items)
    item_ids = sorted(str(item.get("item_id")) for item in items if item.get("item_id"))
    return {
        "schema_version": "pg_diag/plan-summary-v1",
        "plan_hash": canonical_hash(plan),
        "server_version_num": plan.get("server_version_num"),
        "supported_server_version": plan.get("supported_server_version"),
        "mode": plan.get("mode"),
        "collection_mode": plan.get("collection_mode"),
        "item_count": len(items),
        "status_counts": dict(sorted(status_counts.items())),
        "collection_scope_counts": dict(sorted(scope_counts.items())),
        "item_ids_hash": canonical_hash(item_ids),
    }


def capabilities() -> dict[str, Any]:
    return {
        "capability_schema_version": CAPABILITY_SCHEMA_VERSION,
        "machine_interface": MACHINE_INTERFACE,
        "contract_version": CONTRACT_VERSION,
        "component": COMPONENT,
        "component_version": __version__,
        "commands": {
            "capabilities": {
                "mutates_target": False,
                "machine_output": True,
                "accepts_plan_hash": False,
            },
            "validate": {
                "mutates_target": False,
                "machine_output": True,
                "accepts_plan_hash": False,
            },
            "explain-plan": {
                "mutates_target": False,
                "machine_output": True,
                "accepts_plan_hash": False,
            },
            "one-shot": {
                "mutates_target": False,
                "machine_output": True,
                "accepts_plan_hash": False,
            },
            "snapshots": {
                "mutates_target": False,
                "machine_output": True,
                "accepts_plan_hash": False,
            },
            "validate-artifact": {
                "mutates_target": False,
                "machine_output": True,
                "accepts_plan_hash": False,
            },
            "summarize": {
                "mutates_target": False,
                "machine_output": True,
                "accepts_plan_hash": False,
            },
            "render": {
                "mutates_target": False,
                "machine_output": True,
                "accepts_plan_hash": False,
            },
        },
        "artifact_schema_versions": [runtime_config.ARTIFACT_SCHEMA_VERSION],
        "summary_schema_versions": ["pg_diag/summary-v1"],
        "plan_summary_schema_versions": ["pg_diag/plan-summary-v1"],
        "content_schema_versions": [runtime_config.SUPPORTED_CONTENT_SCHEMA_VERSION],
        "postgresql_server_version_num": {
            "minimum": runtime_config.MIN_SUPPORTED_PG_VERSION,
            "maximum": runtime_config.MAX_SUPPORTED_PG_VERSION,
        },
        "collection_modes": list(runtime_config.COLLECTION_MODES),
        "exit_codes": EXIT_CODES,
        "secret_policy": {
            "password_sources": ["argument", "passfile"],
            "errors_are_redacted": True,
            "machine_output_contains_secrets": False,
        },
    }


def envelope(
    command: str,
    status: str,
    *,
    request_id: str | None,
    result: Any = None,
    artifacts: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "component": COMPONENT,
        "component_version": __version__,
        "command": command,
        "request_id": request_id,
        "status": status,
        "result": result,
        "artifacts": artifacts or [],
        "warnings": warnings or [],
        "error": error,
    }
