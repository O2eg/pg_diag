"""Local shell source executor."""

from __future__ import annotations

import json
import subprocess
import traceback
import time
from pathlib import Path
from typing import Any

from pg_diag.artifact import item_error_from_exception, item_from_plan
from pg_diag.content_loader import ContentPack
from pg_diag.planner import PlannedItem
from pg_diag.security import json_safe, redact_error, redact_row, redact_text


def execute_shell_item(content: ContentPack, planned: PlannedItem) -> dict[str, Any]:
    started = time.perf_counter()
    script_file = planned.script_file
    if not script_file:
        return item_from_plan(
            planned,
            status="error",
            reason="script_file is missing",
            result={"kind": "plain_text", "data": ""},
        )

    script_path = content.path / "scripts" / script_file
    source_text = _read_source_text(script_path)
    try:
        proc = subprocess.run(
            [str(script_path)],
            cwd=str(script_path.parent),
            capture_output=True,
            text=True,
            timeout=_timeout_seconds(content, planned),
            check=False,
        )
    except Exception as exc:
        return item_error_from_exception(
            planned,
            exc,
            timing_ms=_elapsed_ms(started),
            source_text=source_text,
            source_language="bash",
        )

    output = proc.stdout if proc.stdout else proc.stderr
    status = "ok" if proc.returncode == 0 else "error"
    if status == "ok" and _script_output_mode(content, planned) == "table_json":
        try:
            result = table_json_result(output)
        except ValueError as exc:
            message = redact_error(exc)
            return item_from_plan(
                planned,
                status="error",
                reason=message,
                timing_ms=_elapsed_ms(started),
                result={"kind": "plain_text", "data": redact_text(output)},
                diagnostics=[
                    _exception_diagnostic("shell_json_parse", message, exc),
                    {"level": "error", "code": "shell_output", "message": "Shell output", "output": redact_text(output)},
                ],
                source_text=source_text,
                source_language="bash",
            )
        return item_from_plan(
            planned,
            status="ok" if result["row_count"] else "empty",
            timing_ms=_elapsed_ms(started),
            result=result,
            source_text=source_text,
            source_language="bash",
        )

    return item_from_plan(
        planned,
        status=status,
        reason=None if proc.returncode == 0 else f"exit_code={proc.returncode}",
        timing_ms=_elapsed_ms(started),
        result={"kind": "plain_text", "data": redact_text(output)},
        diagnostics=[] if proc.returncode == 0 else [_process_diagnostic(proc)],
        source_text=source_text,
        source_language="bash",
    )


def _read_source_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def table_json_result(output: str) -> dict[str, Any]:
    text = output.strip()
    if not text:
        return {"kind": "table", "columns": [], "rows": [], "row_count": 0}

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"cannot parse shell JSON output: {exc}") from exc

    if isinstance(parsed, dict):
        records = [parsed]
    elif isinstance(parsed, list):
        records = parsed
    else:
        records = [{"value": parsed}]

    normalized_records = [
        record if isinstance(record, dict) else {"value": record}
        for record in records
    ]
    columns = _columns_from_records(normalized_records)
    rows = [_row_from_record(columns, record) for record in normalized_records]
    return {"kind": "table", "columns": columns, "rows": rows, "row_count": len(rows)}


def _row_from_record(columns: list[dict[str, Any]], record: dict[str, Any]) -> list[Any]:
    missing_indexes = set()
    row = []
    for index, column in enumerate(columns):
        name = column["name"]
        if name not in record:
            missing_indexes.add(index)
            row.append(None)
        else:
            row.append(json_safe(record.get(name)))
    redacted = redact_row(columns, row)
    for index in missing_indexes:
        redacted[index] = None
    return redacted


def _columns_from_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    columns: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        for key in record:
            name = str(key)
            if name in seen:
                continue
            seen.add(name)
            columns.append({"name": name, "pg_type": "json", "pg_type_oid": None})
    return columns


def _script_output_mode(content: ContentPack, planned: PlannedItem) -> str:
    script_id = planned.source_id
    if script_id and script_id in content.scripts:
        return str(content.scripts[script_id].get("output") or "plain_text")
    return "plain_text"


def _timeout_seconds(content: ContentPack, planned: PlannedItem) -> float:
    script_id = planned.source_id
    timeout_ms = (content.report.get("runtime_policy") or {}).get("default_shell_timeout_ms", 5000)
    if script_id and script_id in content.scripts:
        timeout_ms = content.scripts[script_id].get("timeout_ms", timeout_ms)
    return float(timeout_ms) / 1000.0


def _exception_diagnostic(code: str, message: str, exc: BaseException) -> dict[str, Any]:
    trace = redact_text("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    return {"level": "error", "code": code, "message": message, "traceback": trace}


def _process_diagnostic(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return {
        "level": "error",
        "code": "shell_exit",
        "message": f"Shell command exited with code {proc.returncode}",
        "exit_code": proc.returncode,
        "stdout": redact_text(proc.stdout or ""),
        "stderr": redact_text(proc.stderr or ""),
    }


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)
