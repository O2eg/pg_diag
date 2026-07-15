from __future__ import annotations

from _local_security_common import *


_PROCESS_ENVIRONMENT_SCRIPT = r"""
set -u
readable=0
unreadable=0
for proc_dir in /proc/[0-9]*; do
  [ -d "$proc_dir" ] || continue
  if environment="$(tr '\000' '\n' < "$proc_dir/environ" 2>/dev/null)"; then
    readable=$((readable + 1))
  else
    unreadable=$((unreadable + 1))
    continue
  fi
  if ! printf '%s\n' "$environment" | grep -Eq \
    '^PGPASSWORD=.+$|postgres(ql)?://[^:@/[:space:]]+:[^@/[:space:]]+@'; then
    continue
  fi
  cmdline="$(tr '\000' ' ' < "$proc_dir/cmdline" 2>/dev/null)" || cmdline=""
  printf 'F\0%s\0%s\0' "${proc_dir##*/}" "$cmdline"
done
printf 'C\0%s\0%s\0' "$readable" "$unreadable"
"""


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    probe = await ctx.host.run_script(_PROCESS_ENVIRONMENT_SCRIPT)
    if probe.returncode != 0:
        return _unavailable_result(
            probe.stderr.strip() or "Process environments could not be inspected through the host connection",
            "security_proc_environ_unavailable",
        )

    fields = probe.stdout.split("\0")
    if fields and fields[-1] == "":
        fields.pop()
    rows = []
    readable = 0
    unreadable = 0
    index = 0
    while index < len(fields):
        record_type = fields[index]
        if record_type == "F" and index + 2 < len(fields):
            rows.append(
                {
                    "pid": fields[index + 1],
                    "process": fields[index + 2][:240],
                    "finding_type": "environment_secret",
                    "risk_level": "high",
                    "risk_reason": "Process environment appears to contain PostgreSQL credentials",
                }
            )
            index += 3
        elif record_type == "C" and index + 2 < len(fields):
            readable = int(fields[index + 1] or 0)
            unreadable = int(fields[index + 2] or 0)
            index += 3
        else:
            return _unavailable_result(
                "Process environment probe returned an invalid field frame",
                "security_proc_environ_invalid_output",
            )

    if not readable:
        return _unavailable_result(
            "No process environment could be read from /proc",
            "security_proc_environ_unavailable",
        )
    return _result(
        rows,
        ok_title="No PostgreSQL credentials detected in readable process environments",
        fail_title="PostgreSQL credentials detected in process environments",
        recommendation="Avoid PGPASSWORD and URI passwords in long-lived process environments; prefer protected service files, peer auth, or secret managers.",
        diagnostic_code="security_postgres_env_secret_leaks",
        coverage_complete=unreadable == 0,
        coverage_note=(
            f"read {readable} process environment(s); {unreadable} were inaccessible or disappeared"
            if unreadable else ""
        ),
    )
