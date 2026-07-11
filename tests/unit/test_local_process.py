from __future__ import annotations

import os
from pathlib import Path
import signal
import time

import pytest

from pg_diag.errors import CommandTimeoutError
from pg_diag.local_process import run_local_process


def test_timeout_stops_the_whole_local_process_group(tmp_path: Path) -> None:
    child_pid_file = tmp_path / "child.pid"
    script = (
        "/bin/sh -c 'trap \"\" TERM; exec >/dev/null 2>&1; "
        "printf \"%s\\n\" \"$$\" > \"$1\"; sleep 30' child \"$1\" & wait"
    )

    with pytest.raises(CommandTimeoutError, match="timed out"):
        run_local_process(
            ("/bin/sh", "-c", script, "pg-diag-timeout-test", str(child_pid_file)),
            timeout=0.1,
        )

    child_pid = int(child_pid_file.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 2.0
    while _process_is_running(child_pid) and time.monotonic() < deadline:
        time.sleep(0.02)
    try:
        assert not _process_is_running(child_pid)
    finally:
        if _process_is_running(child_pid):
            os.kill(child_pid, signal.SIGKILL)


def _process_is_running(pid: int) -> bool:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
    except (FileNotFoundError, ProcessLookupError):
        return False
    return len(fields) > 2 and fields[2] != "Z"
