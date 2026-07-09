from __future__ import annotations

from pg_diag.os_metrics import (
    _cpu_row,
    _memory_row_from_values,
    build_backend_proc_window_samples,
)


def test_cpu_row_reports_idle_iowait_and_steal_separately() -> None:
    previous = {
        "user": 100,
        "nice": 100,
        "system": 100,
        "idle": 100,
        "iowait": 100,
        "irq": 100,
        "softirq": 100,
        "steal": 100,
    }
    current = {
        "user": 110,
        "nice": 105,
        "system": 103,
        "idle": 170,
        "iowait": 108,
        "irq": 101,
        "softirq": 101,
        "steal": 102,
    }

    row = _cpu_row(previous, current, 1.25)

    assert row["user_pct"] == 15.0
    assert row["system_pct"] == 5.0
    assert row["idle_pct"] == 70.0
    assert row["iowait_pct"] == 8.0
    assert row["steal_pct"] == 2.0
    assert row["util_pct"] == 22.0
    assert row["elapsed_seconds"] == 1.25


def test_memory_row_from_values_calculates_stack_components() -> None:
    row = _memory_row_from_values(
        {
            "MemTotal": 1000,
            "MemFree": 100,
            "MemAvailable": 250,
            "Buffers": 50,
            "Cached": 300,
            "Shmem": 40,
            "SReclaimable": 30,
            "SUnreclaim": 20,
            "PageTables": 10,
            "KernelStack": 5,
            "SwapCached": 3,
            "SwapTotal": 200,
            "SwapFree": 150,
        }
    )

    assert row["used_bytes"] == 750
    assert row["used_pct"] == 75.0
    assert row["cached_bytes"] == 260
    assert row["shared_bytes"] == 40
    assert row["application_bytes"] == 482
    assert row["swap_used_bytes"] == 50
    assert row["swap_used_pct"] == 25.0


def test_backend_proc_window_sample_uses_only_same_process_at_both_endpoints(
    monkeypatch,
) -> None:
    monkeypatch.setattr("pg_diag.os_metrics.os.sysconf", lambda _name: 100)

    def process(starttime: int, *, utime: int, read_bytes: int) -> dict:
        return {
            "comm": "postgres",
            "cmdline": "postgres: app testdb idle",
            "state": "S",
            "starttime": starttime,
            "utime": utime,
            "stime": 50,
            "read_bytes": read_bytes,
            "write_bytes": 500,
            "cancelled_write_bytes": 0,
            "syscr": 10,
            "syscw": 5,
            "io_access": True,
            "rss_bytes": 4096,
        }

    start = {
        "timestamp": "2026-07-10T00:00:00+00:00",
        "monotonic": 10.0,
        "processes": {
            101: process(1000, utime=100, read_bytes=1000),
            202: process(2000, utime=100, read_bytes=1000),
        },
    }
    end = {
        "timestamp": "2026-07-10T00:00:02+00:00",
        "monotonic": 12.0,
        "processes": {
            101: process(1000, utime=120, read_bytes=2000),
            202: process(2001, utime=500, read_bytes=9000),
            303: process(3000, utime=10, read_bytes=100),
        },
    }

    samples = build_backend_proc_window_samples(start, end)

    assert samples[0]["timestamp"] == end["timestamp"]
    assert [row["pid"] for row in samples[0]["rows"]] == [101]
    assert samples[0]["rows"][0]["cpu_pct"] == 10.0
    assert samples[0]["rows"][0]["read_bytes_per_sec"] == 500.0
