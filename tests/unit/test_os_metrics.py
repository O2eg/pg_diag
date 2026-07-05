from __future__ import annotations

from pg_diag.os_metrics import _cpu_row, _memory_row_from_values


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
