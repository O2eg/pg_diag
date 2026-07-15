"""Local and SSH-host shell source executor."""

from __future__ import annotations

import json
import re
import subprocess
import time
from typing import Any, TYPE_CHECKING

from pg_diag.artifact import item_from_plan
from pg_diag.content_loader import ContentPack
from pg_diag.errors import CommandTimeoutError
from pg_diag.executors.common import (
    elapsed_ms,
    exception_diagnostic,
    read_source_text,
    table_result_from_records,
)
from pg_diag.planner import PlannedItem
from pg_diag.local_process import run_local_process
from pg_diag.security import redact_error, redact_text

if TYPE_CHECKING:
    from pg_diag.ssh_transport import SshTransport


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
    timeout_seconds = _timeout_seconds(content, planned)
    try:
        proc = run_local_process(
            (str(script_path),),
            cwd=str(script_path.parent),
            timeout=timeout_seconds,
        )
    except (CommandTimeoutError, TimeoutError, subprocess.TimeoutExpired):
        return _timeout_item(planned, timeout_seconds, started, source_text)
    except Exception as exc:
        return _shell_error_item(
            planned,
            exc,
            started,
            source_text,
        )

    return _item_from_process(content, planned, proc, source_text, started)


async def execute_remote_shell_item(
    content: ContentPack,
    planned: PlannedItem,
    transport: SshTransport,
) -> dict[str, Any]:
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
    timeout_seconds = _timeout_seconds(content, planned)
    try:
        remote = await transport.run_script(
            source_text,
            timeout=timeout_seconds,
        )
        proc = subprocess.CompletedProcess(
            args=[script_file],
            returncode=remote.returncode,
            stdout=remote.stdout,
            stderr=remote.stderr,
        )
    except (CommandTimeoutError, TimeoutError, subprocess.TimeoutExpired):
        return _timeout_item(planned, timeout_seconds, started, source_text)
    except Exception as exc:
        return _shell_error_item(
            planned,
            exc,
            started,
            source_text,
        )

    return _item_from_process(content, planned, proc, source_text, started)


def _timeout_item(
    planned: PlannedItem,
    timeout_seconds: float,
    started: float,
    source_text: str | None,
) -> dict[str, Any]:
    timeout_ms = int(round(timeout_seconds * 1000))
    message = f"Shell source timed out after {timeout_ms} ms"
    return item_from_plan(
        planned,
        collection_status="error",
        reason=message,
        timing_ms=elapsed_ms(started),
        result={"kind": "plain_text", "data": message},
        diagnostics=[{"level": "error", "code": "shell_timeout", "message": message}],
        source_text=source_text,
        source_language="bash",
    )


def _shell_error_item(
    planned: PlannedItem,
    exc: BaseException,
    started: float,
    source_text: str | None,
) -> dict[str, Any]:
    message = redact_error(exc)
    return item_from_plan(
        planned,
        collection_status="error",
        reason=message,
        timing_ms=elapsed_ms(started),
        result={"kind": "plain_text", "data": message},
        diagnostics=[{"level": "error", "code": "shell_exception", "message": message}],
        source_text=source_text,
        source_language="bash",
    )


def _item_from_process(
    content: ContentPack,
    planned: PlannedItem,
    proc: subprocess.CompletedProcess[str],
    source_text: str | None,
    started: float,
) -> dict[str, Any]:

    output = proc.stdout if proc.returncode == 0 or proc.stdout else proc.stderr
    if proc.returncode == UNSUPPORTED_EXIT_CODE:
        status = "unsupported"
    elif proc.returncode == 0:
        status = "ok" if (proc.stdout or "").strip() else "empty"
    else:
        status = "error"
    if status == "ok" and _script_output_mode(content, planned) == "table_json":
        try:
            result = table_json_result(
                output,
                repair_legacy_lshw=bool(
                    planned.source_id and planned.source_id.startswith("os.lshw_")
                ),
            )
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


def table_json_result(
    output: str,
    *,
    repair_legacy_lshw: bool = False,
) -> dict[str, Any]:
    text = output.strip()
    if not text:
        return {"kind": "table", "columns": [], "rows": [], "row_count": 0}

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        if repair_legacy_lshw:
            try:
                parsed = _parse_legacy_lshw_json(text)
            except json.JSONDecodeError:
                pass
            else:
                return table_result_from_records(
                    parsed if isinstance(parsed, list) else [parsed]
                )
        raise ValueError(f"cannot parse shell JSON output: {exc}") from exc

    if isinstance(parsed, dict):
        records = [parsed]
    elif isinstance(parsed, list):
        records = parsed
    else:
        records = [{"value": parsed}]
    return table_result_from_records(records)


def _parse_legacy_lshw_json(text: str) -> Any:
    """Repair the malformed filtered JSON emitted by lshw 02.18.x.

    That release can omit an outer object terminator before a selected child,
    leave the parent terminator behind, or emit only a closing bracket for an
    empty class.  The transformations are deliberately narrow and are used
    only for declared lshw sources after strict JSON parsing has failed.
    """
    if text.strip() == "]":
        return []

    repaired = re.sub(r"}\s+{", "}}, {", text)
    repaired = re.sub(
        r'("(?:\\.|[^"\\])*"|-?\d+(?:\.\d+)?|true|false|null)\s+{',
        r"\1}, {",
        repaired,
    )
    repaired = re.sub(r",\s*}\s*]\s*$", "\n]", repaired)
    repaired = re.sub(r",\s*]\s*$", "\n]", repaired)
    return json.loads(repaired)


def _script_output_mode(content: ContentPack, planned: PlannedItem) -> str:
    return str(content.scripts[planned.source_id]["output"])


def _timeout_seconds(content: ContentPack, planned: PlannedItem) -> float:
    script_id = planned.source_id
    timeout_ms = content.report["runtime_policy"]["default_shell_timeout_ms"]
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
        message = (proc.stderr or proc.stdout or "required host command is unavailable").strip()
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
