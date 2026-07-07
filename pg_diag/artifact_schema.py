"""Lightweight artifact validation."""

from __future__ import annotations

from typing import Any

from . import runtime_config
from .errors import ValidationError


COLLECTION_STATUSES = {"ok", "empty", "error", "unsupported", "skipped"}
SEVERITY_LEVELS = {"high", "medium", "ok", "unknown"}


def validate_artifact(artifact: dict[str, Any]) -> None:
    required = ["artifact_schema_version", "generator", "content", "report", "runtime", "sections", "items"]
    for key in required:
        if key not in artifact:
            raise ValidationError(f"Artifact missing required field {key!r}")
    if artifact["artifact_schema_version"] != runtime_config.ARTIFACT_SCHEMA_VERSION:
        raise ValidationError(
            "Unsupported artifact schema version: "
            f"{artifact['artifact_schema_version']}"
        )
    if not isinstance(artifact["items"], dict):
        raise ValidationError("Artifact field 'items' must be a mapping")
    for item_id, item in artifact["items"].items():
        if not isinstance(item, dict):
            raise ValidationError(f"Artifact item {item_id!r} must be a mapping")
        if "collection_status" not in item:
            raise ValidationError(f"Artifact item {item_id!r} missing required field 'collection_status'")
        if item["collection_status"] not in COLLECTION_STATUSES:
            raise ValidationError(
                f"Artifact item {item_id!r} has unsupported collection_status {item['collection_status']!r}"
            )
        if "severity_level" not in item:
            raise ValidationError(f"Artifact item {item_id!r} missing required field 'severity_level'")
        if item["severity_level"] not in SEVERITY_LEVELS:
            raise ValidationError(
                f"Artifact item {item_id!r} has unsupported severity_level {item['severity_level']!r}"
            )
