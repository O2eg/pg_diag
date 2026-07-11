"""Linux and PostgreSQL process sampler provider implementations."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
import time
from typing import Any

from pg_diag import runtime_config
from pg_diag.content_loader import resolve_under
from pg_diag.sampler_runtime import (
    SampleMap,
    SamplerCollection,
    SamplerProviderContext,
)

from .linux_helpers import (
    _cpu_row,
    _is_interesting_disk,
    _memory_row_from_values,
    _network_rows,
    build_backend_proc_window_samples,
    normalize_iostat_row,
    parse_iostat_reports,
)


async def collect_linux_os(ctx: SamplerProviderContext) -> SamplerCollection:
    config = ctx.manifest["config"]
    output_ids = {
        "cpu": str(config["cpu_output"]),
        "memory": str(config["memory_output"]),
        "disk": str(config["disk_output"]),
        "network": str(config["network_output"]),
    }
    samples: SampleMap = {output_id: [] for output_id in ctx.required_outputs}
    errors: list[dict[str, str]] = []
    tasks = []
    proc_outputs = {
        output_ids["cpu"],
        output_ids["memory"],
        output_ids["network"],
    }.intersection(ctx.required_outputs)
    proc_script = _read_script(ctx, str(config["proc_script"])) if proc_outputs else None
    iostat_script = (
        _read_script(ctx, str(config["iostat_script"]))
        if output_ids["disk"] in ctx.required_outputs
        else None
    )
    if proc_outputs:
        tasks.append(
            _collect_proc_samples(
                ctx,
                str(proc_script),
                output_ids,
                proc_outputs,
                samples,
                errors,
            )
        )
    if iostat_script is not None:
        tasks.append(
            _collect_iostat(
                ctx,
                iostat_script,
                output_ids["disk"],
                samples,
                errors,
            )
        )
    await asyncio.gather(*tasks)
    return SamplerCollection(samples=samples, errors=errors)


async def collect_postgresql_backend_proc(
    ctx: SamplerProviderContext,
) -> SamplerCollection:
    config = ctx.manifest["config"]
    output_id = str(config["output"])
    if output_id not in ctx.required_outputs:
        return SamplerCollection(samples={}, errors=[])
    script = _read_script(ctx, str(config["proc_script"]))
    started = time.monotonic()
    try:
        start = await _capture_backend_proc_state(ctx, script)
        delay = started + ctx.duration_seconds - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        end = await _capture_backend_proc_state(ctx, script)
        samples = build_backend_proc_window_samples(start, end)
    except Exception as exc:
        return SamplerCollection(
            samples={},
            errors=[{"sampler": output_id, "message": str(exc)}],
        )
    return SamplerCollection(samples={output_id: samples}, errors=[])


async def _collect_proc_samples(
    ctx: SamplerProviderContext,
    script: str,
    output_ids: dict[str, str],
    selected_outputs: set[str],
    samples: SampleMap,
    errors: list[dict[str, str]],
) -> None:
    offsets = runtime_config.snapshots_schedule_offsets(
        ctx.duration_seconds,
        ctx.interval_seconds,
    )
    started_mono = time.monotonic()
    previous_cpu: dict[str, int] | None = None
    previous_network: dict[str, dict[str, int]] | None = None
    previous_mono: float | None = None
    for offset in offsets:
        delay = started_mono + offset - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            result = await ctx.host.run_script(
                script,
                timeout=runtime_config.HOST_COMMAND_TIMEOUT_SECONDS,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or f"exit_code={result.returncode}")
            cpu, load, memory, network = _parse_proc_sample(result.stdout)
        except Exception as exc:
            message = str(exc)
            errors.extend(
                {"sampler": sampler, "message": message}
                for sampler in sorted(selected_outputs)
            )
            return

        now_mono = time.monotonic()
        timestamp = datetime.now(UTC).isoformat()
        if output_ids["memory"] in selected_outputs:
            samples[output_ids["memory"]].append(
                {"timestamp": timestamp, "rows": [_memory_row_from_values(memory)]}
            )
        if (
            output_ids["cpu"] in selected_outputs
            and previous_cpu is not None
            and previous_mono is not None
        ):
            cpu_row = _cpu_row(previous_cpu, cpu, now_mono - previous_mono)
            cpu_row.update(load)
            samples[output_ids["cpu"]].append({"timestamp": timestamp, "rows": [cpu_row]})
        if (
            output_ids["network"] in selected_outputs
            and previous_network is not None
            and previous_mono is not None
        ):
            samples[output_ids["network"]].append(
                {
                    "timestamp": timestamp,
                    "rows": _network_rows(previous_network, network, now_mono - previous_mono),
                }
            )
        previous_cpu = cpu
        previous_network = network
        previous_mono = now_mono


async def _collect_iostat(
    ctx: SamplerProviderContext,
    script: str,
    output_id: str,
    samples: SampleMap,
    errors: list[dict[str, str]],
) -> None:
    duration = ctx.duration_seconds
    interval_seconds = max(1, int(round(min(ctx.interval_seconds, duration))))
    points = max(1, int(duration // interval_seconds))
    started = datetime.now(UTC)
    try:
        result = await ctx.host.run_script(
            script,
            arguments=(str(interval_seconds), str(points + 1)),
            timeout=duration + runtime_config.HOST_COMMAND_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        errors.append({"sampler": output_id, "message": str(exc)})
        return
    if result.returncode != 0:
        errors.append(
            {
                "sampler": output_id,
                "message": result.stderr.strip() or f"iostat exit_code={result.returncode}",
            }
        )
        return
    reports = parse_iostat_reports(result.stdout)
    if not reports:
        errors.append(
            {"sampler": output_id, "message": "iostat output contained no parseable device reports"}
        )
        return
    interval_reports = reports[-points:] if len(reports) >= points else reports
    first_index = max(1, points - len(interval_reports) + 1)
    for report_offset, report in enumerate(interval_reports):
        index = first_index + report_offset
        rows = [
            normalize_iostat_row(row)
            for row in report
            if _is_interesting_disk(str(row.get("device") or ""))
        ]
        timestamp = (
            started + timedelta(seconds=min(index * interval_seconds, duration))
        ).isoformat()
        samples[output_id].append({"timestamp": timestamp, "rows": rows})


def _parse_proc_sample(
    output: str,
) -> tuple[
    dict[str, int],
    dict[str, float],
    dict[str, int],
    dict[str, dict[str, int]],
]:
    sections: dict[str, list[str]] = {}
    current = ""
    for line in output.splitlines():
        if line.startswith("__PG_DIAG_") and line.endswith("__"):
            current = line
            sections[current] = []
        elif current:
            sections[current].append(line)

    stat_parts = (sections.get("__PG_DIAG_STAT__") or [""])[0].split()
    if not stat_parts or stat_parts[0] != "cpu":
        raise ValueError("host /proc/stat output is missing the aggregate CPU row")
    cpu_keys = [
        "user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal",
        "guest", "guest_nice",
    ]
    cpu_values = [int(value) for value in stat_parts[1:]]
    cpu = {
        key: cpu_values[index] if index < len(cpu_values) else 0
        for index, key in enumerate(cpu_keys)
    }

    load_parts = (sections.get("__PG_DIAG_LOAD__") or [""])[0].split()
    if len(load_parts) < 3:
        raise ValueError("host /proc/loadavg output is incomplete")
    load = {
        "load1": float(load_parts[0]),
        "load5": float(load_parts[1]),
        "load15": float(load_parts[2]),
    }

    memory: dict[str, int] = {}
    for line in sections.get("__PG_DIAG_MEM__") or []:
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        parts = raw_value.strip().split()
        if parts:
            memory[key] = int(parts[0]) * 1024

    network: dict[str, dict[str, int]] = {}
    for line in (sections.get("__PG_DIAG_NET__") or [])[2:]:
        if ":" not in line:
            continue
        name, raw_values = line.split(":", 1)
        interface = name.strip()
        values = raw_values.split()
        if interface == "lo" or len(values) < 16:
            continue
        network[interface] = {
            "rx_bytes": int(values[0]),
            "rx_packets": int(values[1]),
            "tx_bytes": int(values[8]),
            "tx_packets": int(values[9]),
        }
    return cpu, load, memory, network


async def _capture_backend_proc_state(
    ctx: SamplerProviderContext,
    script: str,
) -> dict[str, Any]:
    result = await ctx.host.run_script(
        script,
        timeout=runtime_config.HOST_COMMAND_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or f"backend /proc probe exit_code={result.returncode}"
        )
    fields = result.stdout.split("\0")
    if fields and fields[-1] == "":
        fields.pop()
    if len(fields) < 2 or (len(fields) - 2) % 14:
        raise ValueError("backend /proc probe returned an invalid field frame")
    clock_ticks = int(fields[0])
    monotonic = float(fields[1])
    processes: dict[int, dict[str, Any]] = {}
    for index in range(2, len(fields), 14):
        values = fields[index:index + 14]
        pid = int(values[0])
        processes[pid] = {
            "pid": pid,
            "comm": values[1],
            "cmdline": values[2].strip(),
            "state": values[3],
            "starttime": int(values[4]),
            "utime": int(values[5]),
            "stime": int(values[6]),
            "read_bytes": int(values[7] or 0),
            "write_bytes": int(values[8] or 0),
            "cancelled_write_bytes": int(values[9] or 0),
            "syscr": int(values[10] or 0),
            "syscw": int(values[11] or 0),
            "io_access": values[12] == "1",
            "rss_bytes": int(values[13] or 0) * 1024,
        }
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "monotonic": monotonic,
        "clock_ticks": clock_ticks,
        "processes": processes,
    }


def _read_script(ctx: SamplerProviderContext, reference: str) -> str:
    path = resolve_under(ctx.content_path / "scripts", reference, "Sampler script")
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"cannot read sampler script {reference}: {exc}") from exc
