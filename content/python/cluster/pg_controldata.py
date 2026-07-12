from __future__ import annotations

from typing import Any

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result


CONTEXT_SQL = """
select
  pg_catalog.current_setting('data_directory')::text as data_directory,
  pg_catalog.current_setting('server_version_num')::int as server_version_num
"""

HOST_SCRIPT = r"""#!/bin/sh
set -eu

data_directory=$1
expected_major=$2
pg_config_bin=$(command -v pg_config 2>/dev/null || true)
if [ -z "$pg_config_bin" ]; then
  echo "pg_config is not available in PATH" >&2
  exit 127
fi

bindir=$("$pg_config_bin" --bindir)
pg_controldata_bin=$bindir/pg_controldata
if [ ! -x "$pg_controldata_bin" ]; then
  echo "pg_controldata is not executable: $pg_controldata_bin" >&2
  exit 127
fi

control_version=$("$pg_controldata_bin" --version)
case "$control_version" in
  *" $expected_major."*) ;;
  *)
    echo "pg_controldata major version does not match server major $expected_major: $control_version" >&2
    exit 2
    ;;
esac

printf 'PG_CONFIG: %s\n' "$pg_config_bin"
printf 'PG_CONFIG_BINDIR: %s\n' "$bindir"
printf 'PG_CONTROLDATA: %s\n' "$pg_controldata_bin"
"$pg_controldata_bin" -D "$data_directory"
"""


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    async with ctx.conn.transaction(readonly=True):
        context = await ctx.conn.fetchrow(CONTEXT_SQL)

    data_directory = str(context["data_directory"])
    server_version_num = int(context["server_version_num"])
    server_major = server_version_num // 10000
    try:
        command = await ctx.host.run_script(
            HOST_SCRIPT,
            arguments=(data_directory, str(server_major)),
        )
    except OSError as exc:
        return _error(
            f"Cannot execute pg_controldata on the database host: {exc}",
            "pg_controldata_unavailable",
        )

    if command.returncode != 0:
        detail = command.stderr.strip() or command.stdout.strip() or "no diagnostic output"
        return _error(
            f"pg_controldata failed for data directory {data_directory}: {detail}",
            "pg_controldata_failed",
        )

    records: list[dict[str, Any]] = [
        {"parameter": "DATA_DIRECTORY", "value": data_directory},
        {"parameter": "SERVER_VERSION_NUM", "value": str(server_version_num)},
    ]
    for line in command.stdout.splitlines():
        label, separator, value = line.partition(":")
        if not separator or not label.strip():
            continue
        records.append({"parameter": label.strip(), "value": value.strip()})

    if len(records) == 2:
        return _error(
            "pg_controldata returned no parseable control-data fields",
            "pg_controldata_empty",
        )

    return PythonSourceResult(
        collection_status="ok",
        result=table_result(records),
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
