"""Pure normalization helpers for the declared Linux sampler providers."""

from __future__ import annotations

import re
import os
from typing import Any

def build_backend_proc_window_samples(
    start: dict[str, Any],
    end: dict[str, Any],
) -> list[dict[str, Any]]:
    elapsed = max(float(end["monotonic"]) - float(start["monotonic"]), 0.001)
    clock_ticks = int(end.get("clock_ticks") or start.get("clock_ticks") or 0)
    rows = _backend_proc_rows(
        start.get("processes") or {},
        end.get("processes") or {},
        elapsed,
        clock_ticks=clock_ticks or None,
    )
    return [{"timestamp": str(end["timestamp"]), "rows": rows}]


def parse_iostat_reports(output: str) -> list[list[dict[str, Any]]]:
    reports: list[list[dict[str, Any]]] = []
    header: list[str] | None = None
    rows: list[dict[str, Any]] = []

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("Linux"):
            continue
        if line.startswith("avg-cpu:"):
            header = None
            continue
        if line.startswith("Device"):
            if header is not None and rows:
                reports.append(rows)
            header = re.sub(r"^Device:", "Device", line).split()
            rows = []
            continue
        if header is None:
            continue

        parts = line.split()
        if len(parts) < 2:
            continue
        row: dict[str, Any] = {"device": parts[0]}
        for key, value in zip(header[1:], parts[1:]):
            row[key] = _float_or_none(value)
        rows.append(row)

    if header is not None and rows:
        reports.append(rows)
    return reports


def normalize_iostat_row(row: dict[str, Any]) -> dict[str, Any]:
    read_kb = _first_number(row, ["rkB/s", "kB_read/s", "KB_read/s"])
    write_kb = _first_number(row, ["wkB/s", "kB_wrtn/s", "KB_wrtn/s"])
    discard_kb = _first_number(row, ["dkB/s", "kB_dscd/s", "KB_dscd/s"])
    read_mb = _first_number(row, ["rMB/s", "MB_read/s"])
    write_mb = _first_number(row, ["wMB/s", "MB_wrtn/s"])
    discard_mb = _first_number(row, ["dMB/s", "MB_dscd/s"])

    r_await = _first_number(row, ["r_await"])
    w_await = _first_number(row, ["w_await"])
    await_ms = _first_number(row, ["await"])
    if await_ms is None and (r_await is not None or w_await is not None):
        await_ms = max(value for value in (r_await, w_await) if value is not None)

    return {
        "device": str(row.get("device") or ""),
        "read_bytes_per_sec": _throughput_bytes(read_kb, read_mb),
        "write_bytes_per_sec": _throughput_bytes(write_kb, write_mb),
        "discard_bytes_per_sec": _throughput_bytes(discard_kb, discard_mb),
        "read_iops": _first_number(row, ["r/s"]),
        "write_iops": _first_number(row, ["w/s"]),
        "discard_iops": _first_number(row, ["d/s"]),
        "util_pct": _first_number(row, ["%util"]),
        "await_ms": await_ms,
        "r_await_ms": r_await,
        "w_await_ms": w_await,
        "queue_size": _first_number(row, ["aqu-sz", "avgqu-sz"]),
    }


def _cpu_row(previous: dict[str, int], current: dict[str, int], elapsed: float) -> dict[str, Any]:
    deltas = {key: current.get(key, 0) - previous.get(key, 0) for key in current}
    # Linux includes guest time in user/nice already, so adding guest fields again
    # inflates the denominator and makes the stacked CPU series sum below 100%.
    total = sum(
        max(value, 0)
        for key, value in deltas.items()
        if key not in {"guest", "guest_nice"}
    )
    idle = max(deltas.get("idle", 0), 0) + max(deltas.get("iowait", 0), 0)
    busy = max(total - idle, 0)

    def pct(*names: str) -> float:
        if total <= 0:
            return 0.0
        return sum(max(deltas.get(name, 0), 0) for name in names) * 100.0 / total

    return {
        "cpu": "total",
        "util_pct": busy * 100.0 / total if total > 0 else 0.0,
        "user_pct": pct("user", "nice"),
        "system_pct": pct("system", "irq", "softirq"),
        "idle_pct": pct("idle"),
        "iowait_pct": pct("iowait"),
        "steal_pct": pct("steal"),
        "elapsed_seconds": elapsed,
    }


def _memory_row_from_values(values: dict[str, int]) -> dict[str, Any]:
    total = values.get("MemTotal", 0)
    free = values.get("MemFree", 0)
    available = values.get("MemAvailable", values.get("MemFree", 0))
    buffers = values.get("Buffers", 0)
    shmem = values.get("Shmem", 0)
    page_cache = max(values.get("Cached", 0) - shmem, 0)
    slab_reclaimable = values.get("SReclaimable", 0)
    slab_total = values.get("Slab", slab_reclaimable + values.get("SUnreclaim", 0))
    slab_unreclaimable = values.get("SUnreclaim", max(slab_total - slab_reclaimable, 0))
    page_tables = values.get("PageTables", 0)
    kernel_stack = values.get("KernelStack", 0)
    swap_cached = values.get("SwapCached", 0)

    accounted = (
        free
        + buffers
        + page_cache
        + shmem
        + slab_reclaimable
        + slab_unreclaimable
        + page_tables
        + kernel_stack
        + swap_cached
    )
    application = max(total - accounted, 0)
    used = max(total - available, 0)
    swap_total = values.get("SwapTotal", 0)
    swap_free = values.get("SwapFree", 0)
    swap_used = max(swap_total - swap_free, 0)
    return {
        "memory": "host",
        "total_bytes": total,
        "free_bytes": free,
        "available_bytes": available,
        "used_bytes": used,
        "used_pct": used * 100.0 / total if total else 0.0,
        "application_bytes": application,
        "buffers_bytes": buffers,
        "cached_bytes": page_cache,
        "shared_bytes": shmem,
        "slab_bytes": slab_total,
        "slab_reclaimable_bytes": slab_reclaimable,
        "slab_unreclaimable_bytes": slab_unreclaimable,
        "page_tables_bytes": page_tables,
        "kernel_stack_bytes": kernel_stack,
        "swap_cached_bytes": swap_cached,
        "mapped_bytes": values.get("Mapped", 0),
        "dirty_bytes": values.get("Dirty", 0),
        "writeback_bytes": values.get("Writeback", 0),
        "anon_pages_bytes": values.get("AnonPages", 0),
        "active_bytes": values.get("Active", 0),
        "inactive_bytes": values.get("Inactive", 0),
        "active_anon_bytes": values.get("Active(anon)", 0),
        "inactive_anon_bytes": values.get("Inactive(anon)", 0),
        "active_file_bytes": values.get("Active(file)", 0),
        "inactive_file_bytes": values.get("Inactive(file)", 0),
        "unevictable_bytes": values.get("Unevictable", 0),
        "committed_as_bytes": values.get("Committed_AS", 0),
        "vmalloc_used_bytes": values.get("VmallocUsed", 0),
        "swap_total_bytes": swap_total,
        "swap_used_bytes": swap_used,
        "swap_used_pct": swap_used * 100.0 / swap_total if swap_total else 0.0,
    }


def _network_rows(
    previous: dict[str, dict[str, int]],
    current: dict[str, dict[str, int]],
    elapsed: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seconds = max(elapsed, 0.001)
    for iface in sorted(current):
        prev = previous.get(iface)
        cur = current[iface]
        if not prev:
            continue
        rows.append(
            {
                "interface": iface,
                "rx_bytes_per_sec": _counter_rate(prev["rx_bytes"], cur["rx_bytes"], seconds),
                "tx_bytes_per_sec": _counter_rate(prev["tx_bytes"], cur["tx_bytes"], seconds),
                "rx_packets_per_sec": _counter_rate(prev["rx_packets"], cur["rx_packets"], seconds),
                "tx_packets_per_sec": _counter_rate(prev["tx_packets"], cur["tx_packets"], seconds),
            }
        )
    return rows


def _backend_proc_rows(
    previous: dict[int, dict[str, Any]],
    current: dict[int, dict[str, Any]],
    elapsed: float,
    *,
    clock_ticks: int | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seconds = max(elapsed, 0.001)
    if clock_ticks is None:
        clock_ticks = os.sysconf(os.sysconf_names.get("SC_CLK_TCK", "SC_CLK_TCK"))
    for pid in sorted(current):
        prev = previous.get(pid)
        cur = current[pid]
        if not prev or prev.get("starttime") != cur.get("starttime"):
            continue
        cpu_ticks = max((cur["utime"] + cur["stime"]) - (prev["utime"] + prev["stime"]), 0)
        cpu_pct = (cpu_ticks / clock_ticks) * 100.0 / seconds if clock_ticks else 0.0
        io_access = bool(prev.get("io_access")) and bool(cur.get("io_access"))
        rows.append(
            {
                "pid": pid,
                "process": cur.get("comm") or "",
                "state": cur.get("state") or "",
                "cpu_pct": cpu_pct,
                "rss_bytes": cur.get("rss_bytes", 0),
                "io_access": io_access,
                "read_bytes_per_sec": (
                    _counter_rate(prev["read_bytes"], cur["read_bytes"], seconds)
                    if io_access else None
                ),
                "write_bytes_per_sec": (
                    _counter_rate(prev["write_bytes"], cur["write_bytes"], seconds)
                    if io_access else None
                ),
                "cancelled_write_bytes_per_sec": (
                    _counter_rate(prev["cancelled_write_bytes"], cur["cancelled_write_bytes"], seconds)
                    if io_access else None
                ),
                "read_syscalls_per_sec": (
                    _counter_rate(prev["syscr"], cur["syscr"], seconds)
                    if io_access else None
                ),
                "write_syscalls_per_sec": (
                    _counter_rate(prev["syscw"], cur["syscw"], seconds)
                    if io_access else None
                ),
                "command": str(cur.get("cmdline") or "")[:220],
            }
        )
    return rows


def _counter_rate(previous: int, current: int, seconds: float) -> float | None:
    if current < previous:
        return None
    return (current - previous) / seconds


def _is_interesting_disk(device: str) -> bool:
    return not re.match(r"^(loop|ram|zram|fd)\d+", device)


def _throughput_bytes(kb_value: float | None, mb_value: float | None) -> float | None:
    if mb_value is not None:
        return mb_value * 1024 * 1024
    if kb_value is not None:
        return kb_value * 1024
    return None


def _first_number(row: dict[str, Any], keys: list[str]) -> float | None:
    for key in keys:
        value = row.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _float_or_none(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
