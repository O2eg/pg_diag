"""Secure run logging mirrored to the interactive standard output."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import sys
from typing import TextIO


def report_log_path(out_dir: str | Path) -> Path:
    return Path(out_dir) / "report.log"


class ProgressReporter:
    """Write identical progress events to report.log and stdout."""

    def __init__(self, path: str | Path, *, stream: TextIO | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.path, flags, 0o600)
        os.fchmod(fd, 0o600)
        self._file = os.fdopen(fd, "w", encoding="utf-8")
        self._stream = stream if stream is not None else sys.stdout
        self._total_units = 1
        self._completed_units = 0
        self._closed = False

    def configure(self, total_units: int) -> None:
        self._total_units = max(1, int(total_units))
        self._completed_units = 0

    @property
    def percent(self) -> int:
        return min(100, int(self._completed_units * 100 / self._total_units))

    def info(self, message: str) -> None:
        self._emit("INFO", message)

    def error(self, message: str) -> None:
        self._emit("ERROR", message)

    def advance(self, message: str, *, units: int = 1, level: str = "INFO") -> None:
        self._completed_units = min(
            self._total_units,
            self._completed_units + max(0, int(units)),
        )
        self._emit(level, message)

    def item(self, item_id: str, status: str, reason: str | None = None) -> None:
        if status == "skipped":
            message = f"SKIP item={item_id} reason={_single_line(reason or 'collection skipped')}"
        else:
            message = f"ITEM item={item_id} status={_single_line(status)}"
            if reason:
                message += f" reason={_single_line(reason)}"
        self.advance(message, level="ERROR" if status == "error" else "INFO")

    def complete(self, message: str = "DONE") -> None:
        self._completed_units = self._total_units
        self._emit("INFO", message)

    def close(self) -> None:
        if self._closed:
            return
        self._file.close()
        self._closed = True

    def _emit(self, level: str, message: str) -> None:
        if self._closed:
            return
        timestamp = datetime.now(timezone.utc).isoformat().removesuffix("+00:00") + "Z"
        line = (
            f"{timestamp} level={level} progress={self.percent}% "
            f"{_single_line(message)}"
        )
        self._file.write(line + "\n")
        self._file.flush()
        self._stream.write(line + "\n")
        self._stream.flush()


def _single_line(value: str) -> str:
    return " ".join(str(value).splitlines()).strip()
