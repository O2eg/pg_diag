"""Local shell source executor."""

from __future__ import annotations

import json
import subprocess
import time
from typing import Any

from pg_diag.artifact import item_error_from_exception, item_from_plan
from pg_diag.content_loader import ContentPack
from pg_diag.executors.common import (
    elapsed_ms,
    exception_diagnostic,
    read_source_text,
    table_result_from_records,
)
from pg_diag.planner import PlannedItem
from pg_diag.security import redact_error, redact_text


UNSUPPORTED_EXIT_CODE = 3


def execute_shell_item(content: ContentPack, planned: PlannedItem) -> dict[str, Any]:
    started = time.perf_counter()
    script_file = planned.script_file
    if not script_file:
        return item_from_plan(
            planned,
            collection_status="error",
            reason="script_file is missing",
            result={"kind": "plain_text", "data": ""},
        )

    script_path = content.path / "scripts" / script_file
    source_text = read_source_text(script_path)
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
            timing_ms=elapsed_ms(started),
            source_text=source_text,
            source_language="bash",
        )

    output = proc.stdout if proc.returncode == 0 or proc.stdout else proc.stderr
    if proc.returncode == UNSUPPORTED_EXIT_CODE:
        status = "unsupported"
    elif proc.returncode == 0:
        status = "ok" if (proc.stdout or "").strip() else "empty"
    else:
        status = "error"
    if status == "ok" and _script_output_mode(content, planned) == "table_json":
        try:
            result = table_json_result(output)
        except ValueError as exc:
            message = redact_error(exc)
            return item_from_plan(
                planned,
                collection_status="error",
                reason=message,
                timing_ms=elapsed_ms(started),
                result={"kind": "plain_text", "data": redact_text(output)},
                diagnostics=[
                    exception_diagnostic("shell_json_parse", message, exc),
                    {"level": "error", "code": "shell_output", "message": "Shell output", "output": redact_text(output)},
                ],
                source_text=source_text,
                source_language="bash",
            )
        return item_from_plan(
            planned,
            collection_status="ok" if result["row_count"] else "empty",
            timing_ms=elapsed_ms(started),
            result=result,
            diagnostics=_success_diagnostics(proc),
            source_text=source_text,
            source_language="bash",
        )

    return item_from_plan(
        planned,
        collection_status=status,
        reason=_process_reason(proc, status),
        timing_ms=elapsed_ms(started),
        result={"kind": "plain_text", "data": redact_text(output)},
        diagnostics=_success_diagnostics(proc) if proc.returncode == 0 else [_process_diagnostic(proc)],
        source_text=source_text,
        source_language="bash",
    )


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

    return table_result_from_records(records)


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


def _process_diagnostic(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return {
        "level": "error",
        "code": "shell_exit",
        "message": f"Shell command exited with code {proc.returncode}",
        "exit_code": proc.returncode,
        "stdout": redact_text(proc.stdout or ""),
        "stderr": redact_text(proc.stderr or ""),
    }


def _process_reason(proc: subprocess.CompletedProcess[str], status: str) -> str | None:
    if proc.returncode == 0:
        return None
    if status == "unsupported":
        message = (proc.stderr or proc.stdout or "required local command is unavailable").strip()
        return redact_text(message[:500])
    return f"exit_code={proc.returncode}"


def _success_diagnostics(proc: subprocess.CompletedProcess[str]) -> list[dict[str, Any]]:
    stderr = redact_text(proc.stderr or "").strip()
    if not stderr:
        return []
    return [
        {
            "level": "warning",
            "code": "shell_stderr",
            "message": "Shell command completed with diagnostic output",
            "stderr": stderr,
        }
    ]
