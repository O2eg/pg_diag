"""Logs report collection orchestration (csvlog files, no database)."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from . import runtime_config
from .collection import (
    close_collection,
    collect_report_object_ddl,
    execute_and_record_report_item,
    finish_collection,
    start_collection,
)
from .content_loader import ContentPack
from .logscan import collect_report_server_log
from .planner import LOGS_MODE_SKIP_REASON
from .progress import ProgressReporter
from .ssh_transport import SshConfig


async def collect_logs(
    content: ContentPack,
    out_dir: str | Path,
    log_directory: str,
    depth_minutes: int,
    collection_mode: str = runtime_config.LOCAL_COLLECTION_MODE,
    json_out: str | Path | None = None,
    html_out: str | Path | None = None,
    output_formats: str | Iterable[str] | None = None,
    content_validated: bool = False,
    ssh_config: SshConfig | None = None,
    item_id: str | Iterable[str] | None = None,
    tags: Iterable[str] | None = None,
    progress: ProgressReporter | None = None,
    strip_meta: bool = False,
    item_type: str | Iterable[str] | None = None,
    log_timezone: str | None = None,
) -> dict[str, Any]:
    """Build the ``server_log`` section from a directory of csvlog files.

    The plan keeps only ``server_log`` items; the log directory is read on the
    collector (``local``) or on the SSH target (``remote``), the window is
    anchored at the newest record, and PostgreSQL is never contacted.
    """
    if collection_mode not in runtime_config.LOGS_COLLECTION_MODES:
        raise ValueError(
            "logs mode supports only "
            + " and ".join(runtime_config.LOGS_COLLECTION_MODES)
            + " collection modes"
        )
    if depth_minutes <= 0:
        raise ValueError("logs mode requires a positive --log-depth-time-min")
    run = await start_collection(
        content=content,
        out_dir=out_dir,
        dsn=None,
        connection_kwargs={},
        mode=runtime_config.LOGS_MODE,
        collection_mode=collection_mode,
        json_out=json_out,
        html_out=html_out,
        output_formats=output_formats,
        content_validated=content_validated,
        ssh_config=ssh_config,
        item_id=item_id,
        tags=tags,
        progress=progress,
        item_type=item_type,
    )
    try:
        # Every non-server_log item is skipped by the plan itself; one summary
        # line replaces hundreds of identical SKIP entries in report.log.
        skipped = [planned for planned in run.plan.items if planned.status == "skipped"]
        deferred = [planned for planned in run.plan.items if planned.status != "skipped"]
        if progress is not None:
            progress.configure(len(deferred))
            if skipped:
                progress.info(
                    f"SKIP items={len(skipped)} reason={LOGS_MODE_SKIP_REASON}"
                )
        await collect_report_server_log(
            run,
            depth_minutes=depth_minutes,
            log_directory=log_directory,
            log_timezone=log_timezone,
        )
        for planned in deferred:
            await execute_and_record_report_item(run, planned)
        await collect_report_object_ddl(run, enabled=True)  # no database: unavailable
        return finish_collection(
            run,
            runtime_updates={
                "log_directory": log_directory,
                "log_depth_time_min": int(depth_minutes),
                "log_timezone": log_timezone,
            },
            strip_meta=strip_meta,
        )
    finally:
        await close_collection(run)
