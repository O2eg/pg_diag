"""Bounded local subprocess execution with process-group cleanup."""

from __future__ import annotations

import os
import signal
import subprocess
from collections.abc import Mapping, Sequence

from .errors import CommandTimeoutError


PROCESS_STOP_GRACE_SECONDS = 0.25


def run_local_process(
    arguments: Sequence[str],
    *,
    timeout: float,
    input_data: str | None = None,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command and terminate its whole process group on timeout."""
    argv = tuple(arguments)
    process = subprocess.Popen(
        argv,
        cwd=cwd,
        env=dict(env) if env is not None else None,
        stdin=subprocess.PIPE if input_data is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(input=input_data, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _stop_process_group(process)
        raise CommandTimeoutError(
            f"local command timed out after {timeout:g} seconds"
        ) from exc
    except BaseException:
        _stop_process_group(process)
        raise
    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


def _stop_process_group(process: subprocess.Popen[str]) -> None:
    _signal_process_group(process, signal.SIGTERM)
    try:
        process.communicate(timeout=PROCESS_STOP_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        pass

    if not _process_group_exists(process.pid):
        return
    _signal_process_group(process, signal.SIGKILL)
    try:
        process.communicate(timeout=PROCESS_STOP_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()


def _process_group_exists(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _signal_process_group(process: subprocess.Popen[str], sig: signal.Signals) -> None:
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        return
    except OSError:
        try:
            process.send_signal(sig)
        except ProcessLookupError:
            pass
