"""Snapshot collection orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import runtime_config
from .collection import (
    close_collection,
    execute_and_record_report_item,
    finish_collection,
    start_collection,
)
from .content_loader import ContentPack
from .ssh_transport import SshConfig


async def collect_snapshot(
    content: ContentPack,
    out_dir: str | Path,
    dsn: str | None,
    connection_kwargs: dict[str, Any],
    collection_mode: str = runtime_config.DEFAULT_COLLECTION_MODE,
    json_out: str | Path | None = None,
    html_out: str | Path | None = None,
    content_validated: bool = False,
    ssh_config: SshConfig | None = None,
    item_id: str | None = None,
) -> dict[str, Any]:
    run = await start_collection(
        content=content,
        out_dir=out_dir,
        dsn=dsn,
        connection_kwargs=connection_kwargs,
        mode=runtime_config.SNAPSHOT_MODE,
        collection_mode=collection_mode,
        json_out=json_out,
        html_out=html_out,
        content_validated=content_validated,
        ssh_config=ssh_config,
        item_id=item_id,
    )
    try:
        for planned in run.plan.items:
            await execute_and_record_report_item(run, planned)
        return finish_collection(run)
    finally:
        await close_collection(run)
