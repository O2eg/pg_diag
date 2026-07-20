"""One-shot report collection orchestration."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from . import runtime_config
from .collection import (
    close_collection,
    execute_and_record_report_item,
    finish_collection,
    record_item_progress,
    start_collection,
)
from .content_loader import ContentPack
from .progress import ProgressReporter
from .ssh_transport import SshConfig


async def collect_one_shot(
    content: ContentPack,
    out_dir: str | Path,
    dsn: str | None,
    connection_kwargs: dict[str, Any],
    collection_mode: str = runtime_config.DEFAULT_COLLECTION_MODE,
    json_out: str | Path | None = None,
    html_out: str | Path | None = None,
    output_formats: str | Iterable[str] | None = None,
    content_validated: bool = False,
    ssh_config: SshConfig | None = None,
    item_id: str | Iterable[str] | None = None,
    tags: Iterable[str] | None = None,
    progress: ProgressReporter | None = None,
    strip_meta: bool = False,
) -> dict[str, Any]:
    run = await start_collection(
        content=content,
        out_dir=out_dir,
        dsn=dsn,
        connection_kwargs=connection_kwargs,
        mode=runtime_config.ONE_SHOT_MODE,
        collection_mode=collection_mode,
        json_out=json_out,
        html_out=html_out,
        output_formats=output_formats,
        content_validated=content_validated,
        ssh_config=ssh_config,
        item_id=item_id,
        tags=tags,
        progress=progress,
    )
    try:
        if progress is not None:
            progress.configure(len(run.plan.items))
        for planned in run.plan.items:
            if planned.status == "skipped":
                record_item_progress(run, planned)
                continue
            await execute_and_record_report_item(run, planned)
        return finish_collection(run, strip_meta=strip_meta)
    finally:
        await close_collection(run)
