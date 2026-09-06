from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pg_diag.host_access import LocalHostAccess


def test_local_read_proc_sysctl_with_zero_stat_size() -> None:
    path = Path("/proc/sys/kernel/core_pattern")
    try:
        with path.open("rb") as stream:
            expected = stream.read(4096)
    except OSError:
        pytest.skip("Readable Linux core_pattern is unavailable")
    assert path.stat().st_size == 0
    assert expected
    assert asyncio.run(LocalHostAccess().read_bytes(path)) == expected


@pytest.mark.parametrize("size", [0, 1, 65535, 65536, 65537, 140000])
def test_local_read_limit_preserves_complete_file(tmp_path: Path, size: int) -> None:
    path = tmp_path / "evidence"
    expected = b"x" * size
    path.write_bytes(expected)
    host = LocalHostAccess()
    assert asyncio.run(host.read_bytes(path, limit=size)) == expected
    if size:
        with pytest.raises(OSError, match="exceeds.*read limit"):
            asyncio.run(host.read_bytes(path, limit=size - 1))


def test_local_read_propagates_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        asyncio.run(LocalHostAccess().read_bytes(tmp_path / "missing"))
