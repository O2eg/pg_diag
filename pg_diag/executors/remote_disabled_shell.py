"""Skipped shell executor for remote DB-only collection mode."""

from __future__ import annotations

from typing import Any

from pg_diag.artifact import item_from_plan
from pg_diag.planner import PlannedItem


def skipped_shell_item(planned: PlannedItem, message: str, source_text: str | None = None) -> dict[str, Any]:
    return item_from_plan(
        planned,
        status="skipped",
        reason="remote_db_only",
        result={"kind": "plain_text", "data": message},
        source_text=source_text,
        source_language="bash" if source_text is not None else None,
    )
