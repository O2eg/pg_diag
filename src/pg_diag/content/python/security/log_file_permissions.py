from __future__ import annotations

import re

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    logging_collector = str(await _setting(ctx, "logging_collector") or "").lower()
    if logging_collector not in {"on", "true", "1"}:
        return _not_applicable_result(
            "PostgreSQL logging_collector is disabled; validate the active external or journald destination separately",
            "security_log_files_not_applicable",
        )

    log_directory = await _log_directory(ctx)
    if not log_directory:
        return _unavailable_result("PostgreSQL log_directory setting is empty or unavailable", "security_log_directory_empty")

    log_name_pattern = _log_filename_pattern(await _setting(ctx, "log_filename"))

    async def inspect() -> tuple[list[dict[str, Any]], bool, str]:
        rows = await _host_permission_findings(
            ctx.host,
            log_directory,
            component="postgresql_log_directory",
            expected_mode="not world accessible or writable",
            disallowed_bits=0o007 | 0o020,
            missing_ok=False,
            risk_reason="PostgreSQL log directory permissions are broader than expected",
        )
        try:
            files = sorted(
                (
                    entry for entry in await ctx.host.list_dir(log_directory)
                    if entry.stat.is_file
                ),
                key=lambda entry: entry.stat.mtime,
                reverse=True,
            )
        except OSError as exc:
            return rows, False, f"cannot enumerate {log_directory}: {exc}"
        for entry in files[:100]:
            path = Path(entry.path)
            if log_name_pattern.match(path.name):
                rows.extend(
                    await _host_permission_findings(
                        ctx.host,
                        path,
                        component="postgresql_log_file",
                        expected_mode="0640 or stricter",
                        disallowed_bits=0o027,
                        missing_ok=True,
                        risk_reason="PostgreSQL log file permissions expose operational or SQL details",
                    )
                )
                continue
            # Files that do not follow log_filename belong to another program sharing the
            # directory (a pooler, logrotate leftovers). They are reviewed, not treated as
            # PostgreSQL logs that leak SQL text.
            for row in await _host_permission_findings(
                ctx.host,
                path,
                component="other_file_in_log_directory",
                expected_mode="0640 or stricter",
                disallowed_bits=0o027,
                missing_ok=True,
                risk_reason="File in the PostgreSQL log directory does not match log_filename; broad permissions on it require review",
            ):
                row["risk_level"] = "medium"
                rows.append(row)
        if len(files) > 100:
            return rows, False, f"only the 100 newest of {len(files)} log files were inspected"
        return rows, True, ""

    rows, coverage_complete, coverage_note = await inspect()
    return _result(
        rows,
        ok_title="PostgreSQL log file permissions are restrictive",
        fail_title="PostgreSQL log file permissions are too broad",
        recommendation="Keep PostgreSQL logs readable only by database administrators and avoid world-readable log directories.",
        diagnostic_code="security_log_file_permissions",
        coverage_complete=coverage_complete,
        coverage_note=coverage_note,
    )


_STRFTIME_CLASSES = {
    "Y": r"\d{4}",
    "m": r"\d{2}",
    "d": r"\d{2}",
    "H": r"\d{2}",
    "M": r"\d{2}",
    "S": r"\d{2}",
    "j": r"\d{3}",
    "a": r"[A-Za-z]{3}",
    "A": r"[A-Za-z]+",
    "b": r"[A-Za-z]{3}",
    "B": r"[A-Za-z]+",
    "e": r"[ \d]\d",
    "s": r"\d+",
    "y": r"\d{2}",
    "u": r"\d",
    "w": r"\d",
    "%": "%",
}


def _log_filename_pattern(log_filename: str) -> re.Pattern[str]:
    """Regular expression matching files produced from ``log_filename``.

    The collector replaces strftime escapes with their character classes and
    accepts the ``.csv``/``.json`` suffixes PostgreSQL substitutes for ``.log``
    when csvlog or jsonlog are enabled.
    """
    template = log_filename or "postgresql-%Y-%m-%d_%H%M%S.log"
    parts: list[str] = []
    index = 0
    while index < len(template):
        char = template[index]
        if char == "%" and index + 1 < len(template):
            parts.append(_STRFTIME_CLASSES.get(template[index + 1], ".*?"))
            index += 2
            continue
        parts.append(re.escape(char))
        index += 1
    pattern = "".join(parts)
    if pattern.endswith(re.escape(".log")):
        pattern = pattern[: -len(re.escape(".log"))] + r"\.(?:log|csv|json)"
    return re.compile("^" + pattern + "$")
