"""Lightweight artifact validation."""

from __future__ import annotations

from typing import Any

from . import runtime_config
from .errors import ValidationError


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
