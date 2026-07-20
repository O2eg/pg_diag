from __future__ import annotations

import re
from typing import Any

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result


CONTEXT_SQL = """
select
  pg_catalog.pg_backend_pid()::int8 as backend_pid,
  pg_catalog.current_setting('port')::int as server_port,
  pg_catalog.current_database()::text as database_name
"""

LDD_MARKER = "PGDIAG_LDD_BEGIN"

HOST_SCRIPT = r"""#!/bin/sh
set -eu

backend_pid=$1
case "$backend_pid" in
  ''|*[!0-9]*)
    echo "invalid PostgreSQL backend PID: $backend_pid" >&2
    exit 40
    ;;
esac

backend_status=/proc/$backend_pid/status
if [ ! -r "$backend_status" ]; then
  echo "PostgreSQL backend PID $backend_pid is not visible in this host PID namespace" >&2
  exit 41
fi

backend_name=
postgres_main_pid=
while IFS=: read -r key value; do
  case "$key" in
    Name)
      set -- $value
      backend_name=${1:-}
      ;;
    PPid)
      set -- $value
      postgres_main_pid=${1:-}
      ;;
  esac
done < "$backend_status"

case "$backend_name" in
  postgres|postmaster) ;;
  *)
    echo "PID $backend_pid is '$backend_name', not a PostgreSQL backend" >&2
    exit 42
    ;;
esac

case "$postgres_main_pid" in
  ''|*[!0-9]*|0|1)
    echo "cannot resolve the parent of PostgreSQL backend PID $backend_pid" >&2
    exit 43
    ;;
esac

postgres_main_status=/proc/$postgres_main_pid/status
if [ ! -r "$postgres_main_status" ]; then
  echo "parent PID $postgres_main_pid of PostgreSQL backend PID $backend_pid is not visible" >&2
  exit 43
fi

postgres_main_name=
while IFS=: read -r key value; do
  case "$key" in
    Name)
      set -- $value
      postgres_main_name=${1:-}
      break
      ;;
  esac
done < "$postgres_main_status"

case "$postgres_main_name" in
  postgres|postmaster) ;;
  *)
    echo "parent PID $postgres_main_pid of backend PID $backend_pid is '$postgres_main_name'" >&2
    echo "the parent is not a PostgreSQL main process" >&2
    exit 44
    ;;
esac

postgres_executable=$(readlink "/proc/$postgres_main_pid/exe" 2>/dev/null || true)
if [ -z "$postgres_executable" ]; then
  echo "cannot resolve /proc/$postgres_main_pid/exe for PostgreSQL backend PID $backend_pid" >&2
  exit 45
fi

ldd_bin=$(command -v ldd 2>/dev/null || true)
if [ -z "$ldd_bin" ]; then
  echo "ldd is not available in PATH on the database host" >&2
  exit 46
fi

printf 'PGDIAG_BACKEND_PID=%s\n' "$backend_pid"
printf 'PGDIAG_POSTGRES_MAIN_PID=%s\n' "$postgres_main_pid"
printf 'PGDIAG_POSTGRES_EXECUTABLE=%s\n' "$postgres_executable"
printf 'PGDIAG_LDD_PATH=%s\n' "$ldd_bin"
printf '%s\n' 'PGDIAG_LDD_BEGIN'
"$ldd_bin" "/proc/$postgres_main_pid/exe"
"""

_RESOLVED_RE = re.compile(
    r"^(?P<library>\S+)\s+=>\s+(?P<path>.+?)\s+\((?P<address>[^()]*)\)\s*$"
)
_NOT_FOUND_RE = re.compile(r"^(?P<library>\S+)\s+=>\s+not found\s*$")
_DIRECT_RE = re.compile(r"^(?P<path>/.*?)\s+\((?P<address>[^()]*)\)\s*$")
_VIRTUAL_RE = re.compile(r"^(?P<library>\S+)\s+\((?P<address>[^()]*)\)\s*$")


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    async with ctx.conn.transaction(readonly=True):
        context = await ctx.conn.fetchrow(CONTEXT_SQL)

    backend_pid = int(context["backend_pid"])
    server_port = int(context["server_port"])
    database_name = str(context["database_name"])

    try:
        command = await ctx.host.run_script(HOST_SCRIPT, arguments=(str(backend_pid),))
    except OSError as exc:
        return _unavailable(
            f"Cannot inspect PostgreSQL backend PID {backend_pid} on the selected host: {exc}",
            "postgres_main_ldd_host_unavailable",
        )

    header, marker, ldd_output = command.stdout.partition(f"{LDD_MARKER}\n")
    if not marker:
        if command.returncode in {41, 42, 43, 44, 45}:
            detail = command.stderr.strip() or command.stdout.strip() or "process is unavailable"
            return _unavailable(
                f"Cannot match connected PostgreSQL backend PID {backend_pid} to its main process "
                f"on the selected host: {detail}",
                "postgres_main_process_unavailable",
            )
        if command.returncode == 46:
            return _unavailable(
                command.stderr.strip() or "ldd is not available on the database host",
                "postgres_main_ldd_unavailable",
            )
        detail = command.stderr.strip() or command.stdout.strip() or "no diagnostic output"
        return _error(
            f"Cannot prepare ldd collection for PostgreSQL backend PID {backend_pid}: {detail}",
            "postgres_main_ldd_setup_failed",
        )

    metadata = _parse_metadata(header)
    try:
        reported_backend_pid = int(metadata["PGDIAG_BACKEND_PID"])
        postgres_main_pid = int(metadata["PGDIAG_POSTGRES_MAIN_PID"])
        postgres_executable = metadata["PGDIAG_POSTGRES_EXECUTABLE"]
        ldd_path = metadata["PGDIAG_LDD_PATH"]
    except (KeyError, TypeError, ValueError) as exc:
        return _error(
            f"Invalid ldd collection metadata for PostgreSQL backend PID {backend_pid}: {exc}",
            "postgres_main_ldd_invalid_metadata",
        )

    if reported_backend_pid != backend_pid:
        return _error(
            f"Host returned backend PID {reported_backend_pid}, expected {backend_pid}",
            "postgres_main_ldd_backend_mismatch",
        )

    if command.returncode != 0:
        detail = command.stderr.strip() or ldd_output.strip() or "no diagnostic output"
        return _error(
            f"ldd failed for PostgreSQL main process PID {postgres_main_pid} "
            f"({postgres_executable}): {detail}",
            "postgres_main_ldd_failed",
        )

    records = [
        {
            "server_port": server_port,
            "database_name": database_name,
            "backend_pid": backend_pid,
            "postgres_main_pid": postgres_main_pid,
            "postgres_executable": postgres_executable,
            **dependency,
        }
        for dependency in _parse_ldd_output(ldd_output)
    ]

    diagnostics: list[dict[str, Any]] = [
        {
            "level": "info",
            "code": "postgres_main_ldd_collected",
            "message": (
                f"Collected {len(records)} ldd row(s) via {ldd_path} for PostgreSQL main "
                f"process PID {postgres_main_pid}, selected from backend PID {backend_pid} "
                f"on port {server_port}."
            ),
        }
    ]
    if command.stderr.strip():
        diagnostics.append(
            {
                "level": "warning",
                "code": "postgres_main_ldd_stderr",
                "message": command.stderr.strip(),
            }
        )
    missing_count = sum(row["link_status"] == "not_found" for row in records)
    if missing_count:
        diagnostics.append(
            {
                "level": "warning",
                "code": "postgres_main_ldd_dependency_not_found",
                "message": f"ldd reported {missing_count} unresolved dynamic dependency row(s).",
            }
        )

    return PythonSourceResult(
        collection_status="ok" if records else "empty",
        reason=None if records else "ldd returned no dependency rows",
        result=table_result(records),
        diagnostics=diagnostics,
        severity_level="unknown",
    )


def _parse_metadata(header: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in header.splitlines():
        key, separator, value = line.partition("=")
        if separator and key.startswith("PGDIAG_"):
            metadata[key] = value
    return metadata


def _parse_ldd_output(output: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        row = {
            "library": "",
            "resolved_path": "",
            "ldd_address": "",
            "link_status": "raw",
            "ldd_output": line,
        }
        match = _NOT_FOUND_RE.match(line)
        if match:
            row.update(library=match.group("library"), link_status="not_found")
        else:
            match = _RESOLVED_RE.match(line)
            if match:
                row.update(
                    library=match.group("library"),
                    resolved_path=match.group("path"),
                    ldd_address=match.group("address"),
                    link_status="resolved",
                )
            else:
                match = _DIRECT_RE.match(line)
                if match:
                    path = match.group("path")
                    row.update(
                        library=path.rsplit("/", 1)[-1],
                        resolved_path=path,
                        ldd_address=match.group("address"),
                        link_status="loader",
                    )
                else:
                    match = _VIRTUAL_RE.match(line)
                    if match:
                        row.update(
                            library=match.group("library"),
                            ldd_address=match.group("address"),
                            link_status="virtual",
                        )
        rows.append(row)
    return rows


def _unavailable(message: str, code: str) -> PythonSourceResult:
    return PythonSourceResult(
        collection_status="unsupported",
        reason=message,
        result=table_result([]),
        diagnostics=[{"level": "warning", "code": code, "message": message}],
        severity_level="unknown",
    )


def _error(message: str, code: str) -> PythonSourceResult:
    return PythonSourceResult(
        collection_status="error",
        reason=message,
        result={"kind": "none"},
        diagnostics=[{"level": "error", "code": code, "message": message}],
        severity_level="unknown",
    )
