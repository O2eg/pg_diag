from __future__ import annotations

from typing import Any

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result
from pg_diag.logscan.items_common import resolve_inventory

ACTIVE_FILE_HIGH_BYTES = 1 << 30  # 1 GiB
TOTAL_BYTES_MEDIUM = 10 << 30  # 10 GiB


def collect(context: PythonSourceContext) -> PythonSourceResult:
    inventory, early = resolve_inventory(context)
    if early is not None:
        return PythonSourceResult(**early)
    settings = inventory["settings"]
    rows: list[dict[str, Any]] = [
        {
            "file": item["name"],
            "size_bytes": item["size_bytes"],
            "modification": item["modification"],
            "in_window": item["in_window"],
            "is_current": item["is_current"],
        }
        for item in inventory["files"]
    ]
    findings: list[str] = []
    severity = "ok"
    rotation_disabled = (
        settings["log_rotation_age"] == "0" and settings["log_rotation_size"] == "0"
    )
    if rotation_disabled:
        severity = "high"
        findings.append(
            "log_rotation_age and log_rotation_size are both 0: rotation is disabled "
            "and the active csvlog grows without bound."
        )
    active = next((item for item in inventory["files"] if item["is_current"]), None)
    if active is not None and active["size_bytes"] > ACTIVE_FILE_HIGH_BYTES:
        severity = "high"
        findings.append(
            f"the active csvlog is {active['size_bytes']} bytes; bounded log reads "
            "stay cheap, but rotation is clearly not working."
        )
    if inventory["total_bytes"] > TOTAL_BYTES_MEDIUM and severity == "ok":
        severity = "medium"
        findings.append(
            f"csvlog files hold {inventory['total_bytes']} bytes in total; review "
            "retention."
        )
    issues: dict[str, Any] = {}
    if findings:
        issues = {
            "summary": {
                "severity": severity,
                "status": "review" if severity == "medium" else "fail",
                "title": "Server log rotation needs attention",
                "description": " ".join(findings),
                "recommendation": (
                    "Set log_rotation_age/log_rotation_size to sane values and define "
                    "retention for rotated csvlog files."
                ),
            },
            "items": [],
        }
    return PythonSourceResult(
        collection_status="ok" if rows else "empty",
        result=table_result(rows),
        issues=issues,
        severity_level=severity,
    )
