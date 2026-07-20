from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result


CONTEXT_SQL = """
with selected_settings as (
  select name, setting, unit
  from pg_catalog.pg_settings
  where name in (
    'huge_pages',
    'huge_page_size',
    'huge_pages_status',
    'shared_buffers',
    'shared_memory_size',
    'shared_memory_size_in_huge_pages'
  )
)
select
  pg_catalog.current_setting('server_version_num')::int as server_version_num,
  pg_catalog.pg_backend_pid()::int8 as backend_pid,
  max(setting) filter (where name = 'huge_pages') as huge_pages_requested,
  max(setting) filter (where name = 'huge_page_size') as huge_page_size_setting,
  max(unit) filter (where name = 'huge_page_size') as huge_page_size_unit,
  max(setting) filter (where name = 'huge_pages_status') as huge_pages_status,
  max(setting) filter (where name = 'shared_buffers') as shared_buffers_setting,
  max(unit) filter (where name = 'shared_buffers') as shared_buffers_unit,
  max(setting) filter (where name = 'shared_memory_size') as shared_memory_size_setting,
  max(unit) filter (where name = 'shared_memory_size') as shared_memory_size_unit,
  max(setting) filter (where name = 'shared_memory_size_in_huge_pages')
    as required_huge_pages
from selected_settings
"""


HOST_SCRIPT = r"""#!/bin/sh
set -eu

backend_pid=$1
case "$backend_pid" in
  ''|*[!0-9]*)
    echo "invalid PostgreSQL backend PID: $backend_pid" >&2
    exit 40
    ;;
esac

meminfo_path=/proc/meminfo
if [ ! -r "$meminfo_path" ]; then
  echo "/proc/meminfo is unavailable" >&2
  exit 3
fi

if ! awk '
  function emit(name, value) { printf "%s=%.0f\n", name, value }
  $1 == "MemTotal:" { emit("MEM_TOTAL_BYTES", $2 * 1024); mem_total = 1 }
  $1 == "PageTables:" { emit("PAGE_TABLES_BYTES", $2 * 1024) }
  $1 == "SecPageTables:" { emit("SEC_PAGE_TABLES_BYTES", $2 * 1024) }
  $1 == "HugePages_Total:" { emit("POOL_TOTAL_PAGES", $2) }
  $1 == "HugePages_Free:" { emit("POOL_FREE_PAGES", $2) }
  $1 == "HugePages_Rsvd:" { emit("POOL_RESERVED_PAGES", $2) }
  $1 == "HugePages_Surp:" { emit("POOL_SURPLUS_PAGES", $2) }
  $1 == "Hugepagesize:" { emit("OS_DEFAULT_HUGE_PAGE_SIZE_BYTES", $2 * 1024) }
  $1 == "Hugetlb:" { emit("HUGETLB_BYTES", $2 * 1024) }
  $1 == "AnonHugePages:" { emit("ANON_HUGE_PAGES_BYTES", $2 * 1024) }
  END { if (!mem_total) exit 1 }
' "$meminfo_path"; then
  echo "cannot parse MemTotal from /proc/meminfo" >&2
  exit 3
fi

thp_mode=unknown
thp_enabled=/sys/kernel/mm/transparent_hugepage/enabled
if [ -r "$thp_enabled" ]; then
  thp_mode=$(sed -n 's/.*\[\([^]]*\)\].*/\1/p' "$thp_enabled" | sed -n '1p')
  [ -n "$thp_mode" ] || thp_mode=unknown
fi
printf 'THP_MODE=%s\n' "$thp_mode"

backend_status=/proc/$backend_pid/status

if [ -r "$backend_status" ]; then
  backend_name=$(awk '$1 == "Name:" { print $2; exit }' "$backend_status")
  postgres_main_pid=$(awk '$1 == "PPid:" { print $2; exit }' "$backend_status")
  case "$backend_name:$postgres_main_pid" in
    postgres:*|postmaster:*)
      postgres_main_status=/proc/$postgres_main_pid/status
      if [ -r "$postgres_main_status" ]; then
        postgres_main_name=$(awk '$1 == "Name:" { print $2; exit }' "$postgres_main_status")
        case "$postgres_main_name" in
          postgres|postmaster)
            child_pids=
            children_file=/proc/$postgres_main_pid/task/$postgres_main_pid/children
            if [ -r "$children_file" ]; then
              child_pids=$(sed -n '1p' "$children_file")
            fi
            set -- "$postgres_main_status"
            for process_pid in $child_pids; do
              process_status=/proc/$process_pid/status
              [ -r "$process_status" ] || continue
              set -- "$@" "$process_status"
            done
            instance_metrics=$(
              awk -v main_status="$postgres_main_status" '
                function finish_file() {
                  if (!started || (name != "postgres" && name != "postmaster")) return
                  process_count++
                  vmpte_kib += process_vmpte_kib
                  if (current_file == main_status) {
                    main_seen = 1
                    main_hugetlb_kib = process_hugetlb_kib
                  }
                }
                FNR == 1 {
                  finish_file()
                  started = 1
                  current_file = FILENAME
                  name = ""
                  process_vmpte_kib = 0
                  process_hugetlb_kib = 0
                }
                $1 == "Name:" { name = $2 }
                $1 == "VmPTE:" { process_vmpte_kib = $2 }
                $1 == "HugetlbPages:" { process_hugetlb_kib = $2 }
                END {
                  finish_file()
                  if (main_seen) {
                    print "INSTANCE_STATUS=available"
                    printf "POSTGRES_PROCESS_COUNT=%.0f\n", process_count
                    printf "POSTGRES_VMPTE_BYTES=%.0f\n", vmpte_kib * 1024
                    printf "POSTGRES_MAIN_HUGETLB_BYTES=%.0f\n", main_hugetlb_kib * 1024
                  }
                }
              ' "$@" 2>/dev/null || true
            )
            if [ -n "$instance_metrics" ]; then
              printf '%s\n' "$instance_metrics"
              exit 0
            fi
            ;;
        esac
      fi
      ;;
  esac
fi

printf '%s\n' 'INSTANCE_STATUS=unavailable'
printf '%s\n' 'POSTGRES_PROCESS_COUNT=0'
printf '%s\n' 'POSTGRES_VMPTE_BYTES=0'
printf '%s\n' 'POSTGRES_MAIN_HUGETLB_BYTES=0'
"""


PAGE_TABLES_MIN_BYTES = 512 * 1024 * 1024
PAGE_TABLES_MIN_PCT_RAM = 1.0
POSTGRES_VMPTE_SHARE_PCT = 50.0


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    async with ctx.conn.transaction(readonly=True):
        context = dict(await ctx.conn.fetchrow(CONTEXT_SQL))

    backend_pid = _as_int(context.get("backend_pid"))
    if backend_pid is None:
        return _unsupported(
            "PostgreSQL did not return a backend PID for host correlation",
            "postgresql_huge_pages_backend_pid_unavailable",
        )

    try:
        command = await ctx.host.run_script(HOST_SCRIPT, arguments=(str(backend_pid),))
    except OSError as exc:
        return _unsupported(
            f"Cannot inspect huge-page state on the selected database host: {exc}",
            "postgresql_huge_pages_host_unavailable",
        )

    if command.returncode != 0:
        detail = command.stderr.strip() or command.stdout.strip() or "no diagnostic output"
        return _unsupported(
            f"Cannot collect huge-page evidence on the selected database host: {detail}",
            "postgresql_huge_pages_host_probe_failed",
        )

    host = _parse_key_values(command.stdout)
    mem_total_bytes = _host_int(host, "MEM_TOTAL_BYTES")
    if not mem_total_bytes:
        return _unsupported(
            "The host probe returned no usable MemTotal value",
            "postgresql_huge_pages_memtotal_unavailable",
        )

    row = _build_row(context, host, mem_total_bytes)
    issue_items = _evaluate(row)
    severity_level = "medium" if issue_items else "ok"
    row["risk_level"] = severity_level
    row["recommendation"] = _combined_recommendation(issue_items)

    if issue_items:
        summary = {
            "severity": "medium",
            "status": "review",
            "title": "Huge-page configuration requires review",
            "description": f"Detected {len(issue_items)} huge-page or page-table finding(s).",
            "recommendation": row["recommendation"],
        }
    else:
        summary = {
            "severity": "ok",
            "status": "pass",
            "title": "No huge-page finding was detected",
            "description": (
                "PostgreSQL and the default OS HugeTLB pool show no condition that crosses "
                "the conservative checks used by this item."
            ),
            "recommendation": (
                "Keep the pool sized for PostgreSQL startup requirements and recheck after "
                "shared-memory or workload changes."
            ),
        }

    diagnostics: list[dict[str, Any]] = [
        {
            "level": "info",
            "code": "postgresql_huge_pages_collected",
            "message": (
                "Correlated PostgreSQL huge-page settings with the default HugeTLB pool and "
                "host page-table counters."
            ),
        }
    ]
    if row["postgres_instance_procfs_status"] != "available":
        diagnostics.append(
            {
                "level": "warning",
                "code": "postgresql_huge_pages_instance_procfs_unavailable",
                "message": (
                    f"Connected backend PID {backend_pid} could not be matched to its PostgreSQL "
                    "main process in the selected host PID namespace; instance VmPTE and "
                    "HugetlbPages evidence is unavailable."
                ),
            }
        )
    if command.stderr.strip():
        diagnostics.append(
            {
                "level": "warning",
                "code": "postgresql_huge_pages_host_probe_stderr",
                "message": command.stderr.strip(),
            }
        )

    return PythonSourceResult(
        collection_status="ok",
        result=table_result([row]),
        diagnostics=diagnostics,
        issues={"summary": summary, "items": issue_items},
        severity_level=severity_level,
    )


def _build_row(
    context: dict[str, Any],
    host: dict[str, str],
    mem_total_bytes: int,
) -> dict[str, Any]:
    requested = _text(context.get("huge_pages_requested"), default="unknown").lower()
    configured_page_size = _setting_bytes(
        context.get("huge_page_size_setting"),
        context.get("huge_page_size_unit"),
    )
    os_page_size = _host_int(host, "OS_DEFAULT_HUGE_PAGE_SIZE_BYTES")
    postgresql_page_size = configured_page_size or os_page_size
    required_pages = _as_int(context.get("required_huge_pages"))
    if required_pages is not None and required_pages < 0:
        required_pages = None

    instance_status = host.get("INSTANCE_STATUS", "unavailable")
    postgres_hugetlb_bytes = (
        _host_int(host, "POSTGRES_MAIN_HUGETLB_BYTES")
        if instance_status == "available"
        else None
    )
    actual_status, status_source = _actual_status(
        context.get("huge_pages_status"),
        requested,
        instance_status,
        postgres_hugetlb_bytes,
    )

    pool_total_pages = _host_int(host, "POOL_TOTAL_PAGES") or 0
    pool_free_pages = _host_int(host, "POOL_FREE_PAGES") or 0
    pool_reserved_pages = _host_int(host, "POOL_RESERVED_PAGES") or 0
    pool_surplus_pages = _host_int(host, "POOL_SURPLUS_PAGES") or 0
    pool_used_pages = max(pool_total_pages - pool_free_pages, 0)
    pool_free_unreserved_pages = max(pool_free_pages - pool_reserved_pages, 0)
    pool_matches = bool(
        postgresql_page_size
        and os_page_size
        and postgresql_page_size == os_page_size
    )
    pool_shortfall_pages = (
        max(required_pages - pool_total_pages, 0)
        if required_pages is not None and pool_matches
        else None
    )

    page_tables_bytes = _host_int(host, "PAGE_TABLES_BYTES") or 0
    page_tables_pct_ram = page_tables_bytes * 100.0 / mem_total_bytes
    postgres_vmpte_bytes = (
        _host_int(host, "POSTGRES_VMPTE_BYTES")
        if instance_status == "available"
        else None
    )
    postgres_vmpte_share_pct = (
        postgres_vmpte_bytes * 100.0 / page_tables_bytes
        if postgres_vmpte_bytes is not None and page_tables_bytes > 0
        else None
    )

    return {
        "server_version_num": str(context.get("server_version_num") or ""),
        "huge_pages_requested": requested,
        "huge_pages_actual": actual_status,
        "huge_pages_status_source": status_source,
        "postgresql_huge_page_size_bytes": postgresql_page_size,
        "shared_buffers_bytes": _setting_bytes(
            context.get("shared_buffers_setting"),
            context.get("shared_buffers_unit"),
        ),
        "shared_memory_size_bytes": _setting_bytes(
            context.get("shared_memory_size_setting"),
            context.get("shared_memory_size_unit"),
        ),
        "required_huge_pages": required_pages,
        "required_huge_pages_bytes": (
            required_pages * postgresql_page_size
            if required_pages is not None and postgresql_page_size
            else None
        ),
        "os_default_huge_page_size_bytes": os_page_size,
        "default_pool_matches_postgresql_page_size": pool_matches,
        "default_pool_total_pages": pool_total_pages,
        "default_pool_used_pages": pool_used_pages,
        "default_pool_free_pages": pool_free_pages,
        "default_pool_reserved_pages": pool_reserved_pages,
        "default_pool_free_unreserved_pages": pool_free_unreserved_pages,
        "default_pool_surplus_pages": pool_surplus_pages,
        "default_pool_total_bytes": pool_total_pages * (os_page_size or 0),
        "default_pool_shortfall_pages": pool_shortfall_pages,
        "host_ram_bytes": mem_total_bytes,
        "host_page_tables_bytes": page_tables_bytes,
        "host_page_tables_pct_ram": page_tables_pct_ram,
        "host_secondary_page_tables_bytes": _host_int(host, "SEC_PAGE_TABLES_BYTES") or 0,
        "host_hugetlb_bytes": _host_int(host, "HUGETLB_BYTES") or 0,
        "postgres_instance_procfs_status": instance_status,
        "postgres_process_count": (
            _host_int(host, "POSTGRES_PROCESS_COUNT")
            if instance_status == "available"
            else None
        ),
        "postgres_vmpte_bytes": postgres_vmpte_bytes,
        "postgres_vmpte_share_pct": postgres_vmpte_share_pct,
        "postgres_main_hugetlb_bytes": postgres_hugetlb_bytes,
        "transparent_huge_pages_mode": host.get("THP_MODE", "unknown"),
        "anonymous_huge_pages_bytes": _host_int(host, "ANON_HUGE_PAGES_BYTES") or 0,
    }


def _evaluate(row: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    requested = row["huge_pages_requested"]
    actual = row["huge_pages_actual"]

    if requested == "try" and actual == "off":
        issues.append(
            _issue(
                "PostgreSQL fell back to regular pages",
                (
                    "huge_pages=try was requested, but the connected instance is not using "
                    "explicit huge pages."
                ),
                (
                    "Size and reserve the matching HugeTLB pool, then restart PostgreSQL and "
                    "verify actual use."
                ),
                row,
            )
        )

    shortfall = row["default_pool_shortfall_pages"]
    if requested in {"on", "try"} and shortfall is not None and shortfall > 0:
        issues.append(
            _issue(
                "Default HugeTLB pool is smaller than PostgreSQL requirement",
                f"The default pool is short by {shortfall} page(s) at the reported page size.",
                (
                    "Increase the persistent HugeTLB reservation for the matching page size and "
                    "account for other consumers before restarting PostgreSQL."
                ),
                row,
            )
        )

    page_tables_elevated = (
        row["host_page_tables_bytes"] >= PAGE_TABLES_MIN_BYTES
        and row["host_page_tables_pct_ram"] >= PAGE_TABLES_MIN_PCT_RAM
    )
    if page_tables_elevated:
        postgres_share = row["postgres_vmpte_share_pct"]
        if postgres_share is not None and postgres_share >= POSTGRES_VMPTE_SHARE_PCT:
            if actual == "on":
                recommendation = (
                    "PostgreSQL already uses explicit huge pages; inspect backend count, "
                    "mappings, and other processes before changing the HugeTLB pool."
                )
            else:
                recommendation = (
                    "The connected PostgreSQL instance accounts for at least half of host VmPTE; "
                    "consider explicit PostgreSQL huge pages after validating the required pool "
                    "size."
                )
        else:
            recommendation = (
                "Attribute page-table memory to processes and guests before changing PostgreSQL; "
                "consider explicit PostgreSQL huge pages only if its mappings are a material "
                "contributor."
            )
        issues.append(
            _issue(
                "Host page-table memory is elevated",
                (
                    f"PageTables is {row['host_page_tables_pct_ram']:.2f}% of host RAM and exceeds "
                    "the 512 MiB review floor."
                ),
                recommendation,
                row,
            )
        )

    if row["transparent_huge_pages_mode"] == "always":
        issues.append(
            _issue(
                "Transparent Huge Pages are set to always",
                (
                    "The host-wide THP policy is always; THP is separate from PostgreSQL "
                    "explicit HugeTLB use."
                ),
                (
                    "Review the THP policy for database latency and use explicit HugeTLB pages "
                    "for PostgreSQL instead of treating THP as a substitute."
                ),
                row,
            )
        )

    return issues


def _issue(
    title: str,
    description: str,
    recommendation: str,
    row: dict[str, Any],
) -> dict[str, Any]:
    return {
        "severity": "medium",
        "title": title,
        "description": description,
        "recommendation": recommendation,
        "evidence": {
            "huge_pages_requested": row["huge_pages_requested"],
            "huge_pages_actual": row["huge_pages_actual"],
            "required_huge_pages": row["required_huge_pages"],
            "default_pool_total_pages": row["default_pool_total_pages"],
            "default_pool_shortfall_pages": row["default_pool_shortfall_pages"],
            "host_page_tables_bytes": row["host_page_tables_bytes"],
            "host_page_tables_pct_ram": row["host_page_tables_pct_ram"],
            "postgres_vmpte_share_pct": row["postgres_vmpte_share_pct"],
            "transparent_huge_pages_mode": row["transparent_huge_pages_mode"],
        },
    }


def _combined_recommendation(issue_items: list[dict[str, Any]]) -> str:
    if not issue_items:
        return "No immediate change is indicated by the conservative automatic checks."
    recommendations: list[str] = []
    for item in issue_items:
        recommendation = str(item["recommendation"])
        if recommendation not in recommendations:
            recommendations.append(recommendation)
    return " ".join(recommendations)


def _actual_status(
    reported: Any,
    requested: str,
    instance_status: str,
    postgres_hugetlb_bytes: int | None,
) -> tuple[str, str]:
    reported_status = _text(reported).lower()
    if reported_status in {"on", "off"}:
        return reported_status, "pg_settings.huge_pages_status"
    if instance_status == "available" and postgres_hugetlb_bytes is not None:
        if postgres_hugetlb_bytes > 0:
            return "on", "/proc/main/status:HugetlbPages"
        if requested in {"off", "try"}:
            return "off", "/proc/main/status:HugetlbPages"
        if requested == "on":
            return "on", "huge_pages=on startup semantics"
    if requested == "off":
        return "off", "pg_settings.huge_pages"
    return "unknown", "unavailable"


def _setting_bytes(setting: Any, unit: Any) -> int | None:
    if setting is None:
        return None
    try:
        value = Decimal(str(setting))
    except InvalidOperation:
        return None
    unit_text = _text(unit).strip()
    if not unit_text:
        return int(value)
    match = re.fullmatch(r"(?:(\d+)\s*)?(B|kB|MB|GB|TB)", unit_text, re.IGNORECASE)
    if not match:
        return None
    block_count = int(match.group(1) or "1")
    prefix = match.group(2).lower()
    multiplier = {
        "b": 1,
        "kb": 1024,
        "mb": 1024**2,
        "gb": 1024**3,
        "tb": 1024**4,
    }[prefix]
    return int(value * block_count * multiplier)


def _parse_key_values(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if separator and key:
            values[key] = value.strip()
    return values


def _host_int(values: dict[str, str], key: str) -> int | None:
    return _as_int(values.get(key))


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _text(value: Any, *, default: str = "") -> str:
    return default if value is None else str(value)


def _unsupported(reason: str, code: str) -> PythonSourceResult:
    return PythonSourceResult(
        collection_status="unsupported",
        reason=reason,
        result=table_result([]),
        diagnostics=[{"level": "warning", "code": code, "message": reason}],
        severity_level="unknown",
    )
