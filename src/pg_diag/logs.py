"""Logs report collection orchestration (csvlog files, no database)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from functools import wraps
from pathlib import Path
import time
from typing import Any
from uuid import uuid4

from . import runtime_config
from .collection import (
    close_collection,
    collect_report_object_ddl,
    execute_and_record_report_item,
    finish_collection,
    start_collection,
)
from .content_loader import ContentPack
from .errors import CommandTimeoutError
from .executors.python import run_blocking
from .logscan import collect_report_server_log
from .logscan import model as logscan_model
from .logscan.work import run_log_work
from .planner import LOGS_MODE_SKIP_REASON
from .progress import ProgressReporter
from .ssh_transport import SshConfig


async def _collect_logs(
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
    *,
    _deadline_monotonic: float,
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
    if not 1 <= depth_minutes <= logscan_model.DEPTH_MAX_MINUTES:
        raise ValueError(
            f"logs mode requires --log-depth-time-min between 1 and "
            f"{logscan_model.DEPTH_MAX_MINUTES}"
        )
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
        deadline_monotonic=_deadline_monotonic,
    )
    run.report_deadline_monotonic = _deadline_monotonic
    temporary_paths = {
        path: path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        for path in (run.json_path, run.html_path) if path is not None
    }
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
        return await run_blocking(
            finish_collection,
            run,
            runtime_updates={
                "log_directory": log_directory,
                "log_depth_time_min": int(depth_minutes),
                "log_timezone": log_timezone,
            },
            strip_meta=strip_meta,
            temporary_paths=temporary_paths,
        )
    finally:
        # run_blocking has terminated and reaped its writer before returning
        # or raising. Clean only this run's files, including an interrupted
        # write/flush/fsync; the worker's own finally cannot run after SIGKILL.
        try:
            remaining = max(0.001, _deadline_monotonic - time.monotonic())
            await asyncio.wait_for(
                run_log_work(_remove_temporary_files, tuple(temporary_paths.values())),
                timeout=min(2.0, remaining),
            )
        finally:
            await _close_logs_collection(run, _deadline_monotonic)


def _remove_temporary_files(paths: tuple[Path, ...]) -> None:
    for temporary in paths:
        temporary.unlink(missing_ok=True)


async def _close_logs_collection(run: Any, deadline: float) -> None:
    # Bound shutdown as well. The collection phase leaves 30 seconds for
    # item construction, serialization, rendering and connection cleanup.
    remaining = max(0.001, deadline - time.monotonic())
    await asyncio.wait_for(close_collection(run), timeout=min(2.0, remaining))


@wraps(_collect_logs)
async def collect_logs(*args: Any, **kwargs: Any) -> dict[str, Any]:
    seconds = logscan_model.LOGS_REPORT_WALLCLOCK_SECONDS
    deadline = time.monotonic() + seconds
    try:
        return await asyncio.wait_for(
            _collect_logs(*args, **kwargs, _deadline_monotonic=deadline),
            # Keep the final five seconds for cancellation and SSH teardown.
            timeout=max(0.0, seconds - min(5.0, seconds * 0.1)),
        )
    except (TimeoutError, asyncio.TimeoutError) as exc:
        raise CommandTimeoutError(
            f"logs report exceeded its {seconds:g}s deadline"
        ) from exc
