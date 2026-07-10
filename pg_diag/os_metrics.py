"""Threaded local operating system metric samplers."""

from __future__ import annotations

import re
import os
import shutil
import subprocess
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from . import runtime_config


SampleMap = dict[str, list[dict[str, Any]]]


def collect_os_metrics(
    duration_seconds: float,
    interval_seconds: float,
    stop_event: threading.Event | None = None,
) -> tuple[SampleMap, list[dict[str, str]]]:
    collector = _OSMetricsCollector(duration_seconds, interval_seconds, stop_event=stop_event)
    return collector.collect()


def capture_backend_proc_state() -> dict[str, Any]:
    """Capture one endpoint for window-wide PostgreSQL process rates."""
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "monotonic": time.monotonic(),
        "processes": _read_postgres_processes(),
    }


def build_backend_proc_window_samples(
    start: dict[str, Any],
    end: dict[str, Any],
) -> list[dict[str, Any]]:
    elapsed = max(float(end["monotonic"]) - float(start["monotonic"]), 0.001)
    rows = _backend_proc_rows(
        start.get("processes") or {},
        end.get("processes") or {},
        elapsed,
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


class _OSMetricsCollector:
    def __init__(
        self,
        duration_seconds: float,
        interval_seconds: float,
        *,
        stop_event: threading.Event | None = None,
    ) -> None:
        self.duration_seconds = max(float(duration_seconds), 1.0)
        self.interval_seconds = max(float(interval_seconds), 1.0)
        self.schedule_offsets = runtime_config.snapshots_schedule_offsets(
            self.duration_seconds,
            self.interval_seconds,
        )
        self.data: SampleMap = {
            "os.cpu": [],
            "os.memory": [],
            "os.disk": [],
            "os.network": [],
        }
        self.errors: list[dict[str, str]] = []
        self._lock = threading.Lock()
        self._stop_event = stop_event or threading.Event()
        self._iostat_process: subprocess.Popen[str] | None = None
        self._start_dt = datetime.now(UTC)
        self._start_mono = time.monotonic()

    def collect(self) -> tuple[SampleMap, list[dict[str, str]]]:
        threads = [
            threading.Thread(target=self._collect_cpu, name="pg_diag_os_cpu", daemon=True),
            threading.Thread(target=self._collect_memory, name="pg_diag_os_memory", daemon=True),
            threading.Thread(target=self._collect_network, name="pg_diag_os_network", daemon=True),
            threading.Thread(target=self._collect_disk_iostat, name="pg_diag_os_iostat", daemon=True),
        ]
        for thread in threads:
            thread.start()

        deadline = self._start_mono + self.duration_seconds + 10.0
        while any(thread.is_alive() for thread in threads):
            if self._stop_event.is_set() or time.monotonic() >= deadline:
                self._stop_event.set()
                self._terminate_iostat()
                break
            for thread in threads:
                thread.join(0.1)

        for thread in threads:
            thread.join(1.0)
            if thread.is_alive():
                sampler = {
                    "pg_diag_os_cpu": "os.cpu",
                    "pg_diag_os_memory": "os.memory",
                    "pg_diag_os_network": "os.network",
                    "pg_diag_os_iostat": "os.disk",
                }.get(thread.name, thread.name)
                self._error(sampler, "sampler thread did not stop")
        return self.data, self.errors

    def _collect_cpu(self) -> None:
        try:
            previous = _read_proc_stat_cpu()
            previous_time = time.monotonic()
            for offset in self.schedule_offsets[1:]:
                if not self._sleep_until_offset(offset):
                    break
                current = _read_proc_stat_cpu()
                current_time = time.monotonic()
                rows = [_cpu_row(previous, current, current_time - previous_time)]
                load = _read_loadavg()
                rows[0].update(load)
                self._append("os.cpu", self._timestamp_now(), rows)
                previous = current
                previous_time = current_time
        except Exception as exc:  # pragma: no cover - defensive sampler isolation
            self._error("os.cpu", str(exc))

    def _collect_memory(self) -> None:
        try:
            for offset in self.schedule_offsets:
                if offset and not self._sleep_until_offset(offset):
                    break
                if self._stop_event.is_set():
                    break
                self._append("os.memory", self._timestamp_now(), [_memory_row()])
        except Exception as exc:  # pragma: no cover - defensive sampler isolation
            self._error("os.memory", str(exc))

    def _collect_network(self) -> None:
        try:
            previous = _read_proc_net_dev()
            previous_time = time.monotonic()
            for offset in self.schedule_offsets[1:]:
                if not self._sleep_until_offset(offset):
                    break
                current = _read_proc_net_dev()
                current_time = time.monotonic()
                rows = _network_rows(previous, current, current_time - previous_time)
                self._append("os.network", self._timestamp_now(), rows)
                previous = current
                previous_time = current_time
        except Exception as exc:  # pragma: no cover - defensive sampler isolation
            self._error("os.network", str(exc))

    def _collect_disk_iostat(self) -> None:
        if self._stop_event.is_set():
            return
        iostat = shutil.which("iostat")
        if not iostat:
            self._error("os.disk", "iostat executable not found")
            return

        interval_seconds = max(1, int(round(min(self.interval_seconds, self.duration_seconds))))
        points = max(1, int(self.duration_seconds // interval_seconds))
        try:
            proc = subprocess.Popen(
                [iostat, "-dxk", str(interval_seconds), str(points + 1)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "LC_ALL": "C", "LANG": "C"},
            )
            with self._lock:
                self._iostat_process = proc
            if self._stop_event.is_set():
                self._terminate_iostat()
            stdout, stderr = proc.communicate(timeout=self.duration_seconds + 5.0)
        except subprocess.TimeoutExpired:
            self._terminate_iostat()
            self._error("os.disk", "iostat exceeded the collection window")
            return
        except Exception as exc:  # pragma: no cover - depends on host utility behavior
            self._error("os.disk", str(exc))
            return
        finally:
            with self._lock:
                self._iostat_process = None

        if proc.returncode != 0:
            if not self._stop_event.is_set():
                self._error("os.disk", stderr.strip() or f"iostat exit_code={proc.returncode}")
            return

        reports = parse_iostat_reports(stdout)
        if not reports:
            self._error("os.disk", "iostat output contained no parseable device reports")
            return
        interval_reports = reports[-points:] if len(reports) >= points else reports
        first_index = max(1, points - len(interval_reports) + 1)
        for offset, report in enumerate(interval_reports):
            index = first_index + offset
            rows = [
                normalize_iostat_row(row)
                for row in report
                if _is_interesting_disk(str(row.get("device") or ""))
            ]
            self._append(
                "os.disk",
                self._timestamp_for_offset(min(index * interval_seconds, self.duration_seconds)),
                rows,
            )

    def _sleep_until_offset(self, offset: float) -> bool:
        target = self._start_mono + offset
        delay = target - time.monotonic()
        if delay > 0:
            self._stop_event.wait(delay)
        return not self._stop_event.is_set()

    def _timestamp_for_offset(self, offset: float) -> str:
        return (self._start_dt + timedelta(seconds=offset)).isoformat()

    def _timestamp_now(self) -> str:
        return datetime.now(UTC).isoformat()

    def _terminate_iostat(self) -> None:
        with self._lock:
            proc = self._iostat_process
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=2.0)
        except (OSError, subprocess.TimeoutExpired):
            try:
                proc.kill()
            except OSError:
                pass

    def _append(self, sampler: str, timestamp: str, rows: list[dict[str, Any]]) -> None:
        with self._lock:
            self.data.setdefault(sampler, []).append({"timestamp": timestamp, "rows": rows})

    def _error(self, sampler: str, message: str) -> None:
        with self._lock:
            self.errors.append({"sampler": sampler, "message": message})


def _read_proc_stat_cpu() -> dict[str, int]:
    line = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0]
    parts = line.split()
    values = [int(value) for value in parts[1:]]
    keys = ["user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal", "guest", "guest_nice"]
    return {key: values[index] if index < len(values) else 0 for index, key in enumerate(keys)}


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
        return round(sum(max(deltas.get(name, 0), 0) for name in names) * 100.0 / total, 3)

    return {
        "cpu": "total",
        "util_pct": round(busy * 100.0 / total, 3) if total > 0 else 0.0,
        "user_pct": pct("user", "nice"),
        "system_pct": pct("system", "irq", "softirq"),
        "idle_pct": pct("idle"),
        "iowait_pct": pct("iowait"),
        "steal_pct": pct("steal"),
        "elapsed_seconds": round(elapsed, 3),
    }


def _read_loadavg() -> dict[str, float]:
    parts = Path("/proc/loadavg").read_text(encoding="utf-8").split()
    return {
        "load1": _float_or_none(parts[0]) or 0.0,
        "load5": _float_or_none(parts[1]) or 0.0,
        "load15": _float_or_none(parts[2]) or 0.0,
    }


def _memory_row() -> dict[str, Any]:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, raw_value = line.split(":", 1)
        parts = raw_value.strip().split()
        if parts:
            values[key] = int(parts[0]) * 1024
    return _memory_row_from_values(values)


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
        "used_pct": round(used * 100.0 / total, 3) if total else 0.0,
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
        "swap_used_pct": round(swap_used * 100.0 / swap_total, 3) if swap_total else 0.0,
    }


def _read_proc_net_dev() -> dict[str, dict[str, int]]:
    interfaces: dict[str, dict[str, int]] = {}
    for line in Path("/proc/net/dev").read_text(encoding="utf-8").splitlines()[2:]:
        if ":" not in line:
            continue
        name, data = line.split(":", 1)
        iface = name.strip()
        if iface == "lo":
            continue
        parts = data.split()
        if len(parts) < 16:
            continue
        interfaces[iface] = {
            "rx_bytes": int(parts[0]),
            "rx_packets": int(parts[1]),
            "tx_bytes": int(parts[8]),
            "tx_packets": int(parts[9]),
        }
    return interfaces


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


def _read_postgres_processes() -> dict[int, dict[str, Any]]:
    processes: dict[int, dict[str, Any]] = {}
    proc_root = Path("/proc")
    for path in proc_root.iterdir():
        if not path.name.isdigit():
            continue
        pid = int(path.name)
        try:
            proc = _read_process_snapshot(pid)
        except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError, OSError):
            continue
        if _is_postgres_process(proc):
            processes[pid] = proc
    return processes


def _read_process_snapshot(pid: int) -> dict[str, Any]:
    root = Path("/proc") / str(pid)
    stat = _read_proc_pid_stat(root / "stat")
    io_data = _read_key_value_file(root / "io")
    status = _read_key_value_file(root / "status")
    cmdline = (root / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", errors="replace").strip()
    comm = (root / "comm").read_text(encoding="utf-8", errors="replace").strip()
    rss_kb = _status_kb(status, "VmRSS")
    return {
        "pid": pid,
        "comm": comm,
        "cmdline": cmdline,
        "state": stat["state"],
        "starttime": stat["starttime"],
        "utime": stat["utime"],
        "stime": stat["stime"],
        "read_bytes": int(io_data.get("read_bytes", 0)),
        "write_bytes": int(io_data.get("write_bytes", 0)),
        "cancelled_write_bytes": int(io_data.get("cancelled_write_bytes", 0)),
        "syscr": int(io_data.get("syscr", 0)),
        "syscw": int(io_data.get("syscw", 0)),
        "io_access": bool(io_data),
        "rss_bytes": rss_kb * 1024,
    }


def _read_proc_pid_stat(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    right = text.rfind(")")
    left = text.find("(")
    if left < 0 or right < 0:
        raise ValueError("malformed proc stat")
    after = text[right + 2 :].split()
    if len(after) < 20:
        raise ValueError("short proc stat")
    return {
        "state": after[0],
        "utime": int(after[11]),
        "stime": int(after[12]),
        "starttime": int(after[19]),
    }


def _read_key_value_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, PermissionError, OSError):
        return values
    for line in lines:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def _status_kb(status: dict[str, str], key: str) -> int:
    value = status.get(key)
    if not value:
        return 0
    parts = value.split()
    if not parts:
        return 0
    try:
        return int(parts[0])
    except ValueError:
        return 0


def _is_postgres_process(proc: dict[str, Any]) -> bool:
    comm = str(proc.get("comm") or "").lower()
    if comm in {"postgres", "postmaster"} or comm.startswith("postgres:"):
        return True
    cmdline = str(proc.get("cmdline") or "").lower()
    return (
        cmdline.startswith("postgres ")
        or cmdline.startswith("postmaster ")
        or "/postgres " in cmdline
        or "/postmaster " in cmdline
    )


def _backend_proc_rows(
    previous: dict[int, dict[str, Any]],
    current: dict[int, dict[str, Any]],
    elapsed: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seconds = max(elapsed, 0.001)
    clock_ticks = os.sysconf(os.sysconf_names.get("SC_CLK_TCK", "SC_CLK_TCK"))
    for pid in sorted(current):
        prev = previous.get(pid)
        cur = current[pid]
        if not prev or prev.get("starttime") != cur.get("starttime"):
            continue
        cpu_ticks = max((cur["utime"] + cur["stime"]) - (prev["utime"] + prev["stime"]), 0)
        cpu_pct = round((cpu_ticks / clock_ticks) * 100.0 / seconds, 3) if clock_ticks else 0.0
        rows.append(
            {
                "pid": pid,
                "process": cur.get("comm") or "",
                "state": cur.get("state") or "",
                "cpu_pct": cpu_pct,
                "rss_bytes": cur.get("rss_bytes", 0),
                "io_access": cur.get("io_access", False),
                "read_bytes_per_sec": _counter_rate(prev["read_bytes"], cur["read_bytes"], seconds),
                "write_bytes_per_sec": _counter_rate(prev["write_bytes"], cur["write_bytes"], seconds),
                "cancelled_write_bytes_per_sec": _counter_rate(
                    prev["cancelled_write_bytes"], cur["cancelled_write_bytes"], seconds
                ),
                "read_syscalls_per_sec": _counter_rate(prev["syscr"], cur["syscr"], seconds),
                "write_syscalls_per_sec": _counter_rate(prev["syscw"], cur["syscw"], seconds),
                "command": str(cur.get("cmdline") or "")[:220],
            }
        )
    return rows


def _counter_rate(previous: int, current: int, seconds: float) -> float | None:
    if current < previous:
        return None
    return round((current - previous) / seconds, 3)


def _is_interesting_disk(device: str) -> bool:
    return not re.match(r"^(loop|ram|zram|fd)\d+", device)


def _throughput_bytes(kb_value: float | None, mb_value: float | None) -> float | None:
    if mb_value is not None:
        return round(mb_value * 1024 * 1024, 3)
    if kb_value is not None:
        return round(kb_value * 1024, 3)
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
