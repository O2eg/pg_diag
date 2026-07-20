"""PostgreSQL version handling and query variant selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import runtime_config


@dataclass(frozen=True)
class VariantSelection:
    query_id: str
    variant: dict[str, Any] | None
    status: str
    reason: str | None = None


def is_supported_server_version(server_version_num: int) -> bool:
    return (
        runtime_config.MIN_SUPPORTED_PG_VERSION
        <= server_version_num
        <= runtime_config.MAX_SUPPORTED_PG_VERSION
    )


def supported_version_reason(server_version_num: int) -> str | None:
    if is_supported_server_version(server_version_num):
        return None
    return (
        "PostgreSQL server version is outside supported window "
        f"10-18 ({runtime_config.MIN_SUPPORTED_PG_VERSION}-"
        f"{runtime_config.MAX_SUPPORTED_PG_VERSION}): {server_version_num}"
    )


def variant_supports_version(variant: dict[str, Any], server_version_num: int) -> bool:
    min_version = int(variant["min_pg_version"])
    max_version = variant.get("max_pg_version")
    if server_version_num < min_version:
        return False
    if max_version is not None and server_version_num > int(max_version):
        return False
    return True


def variant_intersects_supported_window(variant: dict[str, Any]) -> bool:
    min_version = int(variant["min_pg_version"])
    max_version = int(variant.get("max_pg_version") or runtime_config.MAX_SUPPORTED_PG_VERSION)
    return (
        min_version <= runtime_config.MAX_SUPPORTED_PG_VERSION
        and max_version >= runtime_config.MIN_SUPPORTED_PG_VERSION
    )


def select_query_variant(
    query_id: str, query_manifest: dict[str, Any], server_version_num: int
) -> VariantSelection:
    if not is_supported_server_version(server_version_num):
        return VariantSelection(
            query_id=query_id,
            variant=None,
            status="unsupported",
            reason=supported_version_reason(server_version_num),
        )

    for variant in query_manifest.get("variants", []) or []:
        if variant_supports_version(variant, server_version_num):
            return VariantSelection(query_id=query_id, variant=variant, status="ok")

    requirements = query_manifest.get("requirements") or {}
    reason = requirements.get("unsupported_versions_reason")
    if not reason:
        reason = f"No query variant supports PostgreSQL version {server_version_num}"
    return VariantSelection(query_id=query_id, variant=None, status="unsupported", reason=reason)


async def detect_server_version_num(conn: Any) -> int:
    value = await conn.fetchval("select current_setting('server_version_num')::int")
    return int(value)
