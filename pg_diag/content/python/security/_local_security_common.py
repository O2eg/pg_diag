from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path
from typing import Any

from pg_diag.executors.python import (
    PythonSourceContext,
    PythonSourceResult,
    table_result,
)
from pg_diag.errors import CommandTimeoutError
from pg_diag.host_access import HostAccess


RISK_RANK = {"ok": 0, "unknown": 1, "medium": 2, "high": 3}


def _unavailable_result(reason: str, code: str) -> PythonSourceResult:
    return PythonSourceResult(
        collection_status="unsupported",
        reason=reason,
        result=table_result([]),
        severity_level="unknown",
        diagnostics=[
            {
                "level": "warning",
                "code": code,
                "message": reason,
            }
        ],
    )


def _not_applicable_result(reason: str, code: str) -> PythonSourceResult:
    return PythonSourceResult(
        collection_status="skipped",
        reason=reason,
        result=table_result([]),
        severity_level="unknown",
        diagnostics=[
            {
                "level": "info",
                "code": code,
                "message": reason,
            }
        ],
    )


def _result(
    rows: list[dict[str, Any]],
    *,
    ok_title: str,
    fail_title: str,
    recommendation: str,
    diagnostic_code: str,
    coverage_complete: bool = True,
    coverage_note: str = "",
) -> PythonSourceResult:
    severity_level = _max_risk(row.get("risk_level") for row in rows)
    if not rows and not coverage_complete:
        severity_level = "unknown"
    if rows:
        issues = {
            "summary": {
                "severity": severity_level,
                "status": "fail",
                "title": fail_title,
                "description": (
                    f"{len(rows)} local security finding(s) matched this check."
                    + (f" Coverage note: {coverage_note}" if coverage_note else "")
                ),
                "recommendation": recommendation,
            },
            "items": [
                {
                    "severity": row.get("risk_level", "medium"),
                    "title": row.get("risk_reason", fail_title),
                    "description": str(row),
                    "recommendation": recommendation,
                    "evidence": row,
                }
                for row in rows
            ],
        }
    elif coverage_complete:
        issues = {
            "summary": {
                "severity": "ok",
                "status": "pass",
                "title": ok_title,
                "description": "No matching local security findings were detected.",
                "recommendation": "Keep local PostgreSQL security-sensitive files and sockets restrictive.",
            },
            "items": [],
        }
    else:
        issues = {
            "summary": {
                "severity": "unknown",
                "status": "review",
                "title": "Local security evidence is incomplete",
                "description": coverage_note or "The collector could inspect only part of the required local evidence.",
                "recommendation": recommendation,
            },
            "items": [],
        }
    return PythonSourceResult(
        collection_status="ok" if rows or not coverage_complete else "empty",
        result=table_result(rows),
        issues=issues,
        severity_level=severity_level,
        diagnostics=[
            {
                "level": "info" if coverage_complete else "warning",
                "code": diagnostic_code,
                "message": (
                    f"Collected {len(rows)} local security finding(s)"
                    + (f"; coverage incomplete: {coverage_note}" if coverage_note else "")
                ),
            }
        ],
    )


def _split_socket_directories(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


async def _host_candidate_client_secret_files(ctx: PythonSourceContext) -> list[Path]:
    env = await ctx.host.environ()
    candidates: list[Path] = []
    for env_name in ("PGPASSFILE", "PGSERVICEFILE"):
        value = env.get(env_name)
        if value:
            candidates.append(Path(value))
    if env.get("PGSYSCONFDIR"):
        candidates.append(Path(env["PGSYSCONFDIR"]) / "pg_service.conf")
    if env.get("HOME"):
        candidates.extend(
            [Path(env["HOME"]) / ".pgpass", Path(env["HOME"]) / ".pg_service.conf"]
        )
    candidates.extend(
        [Path("/var/lib/postgresql/.pgpass"), Path("/var/lib/postgresql/.pg_service.conf")]
    )
    try:
        for entry in await ctx.host.list_dir("/home"):
            if entry.stat.is_dir:
                candidates.extend(
                    [Path(entry.path) / ".pgpass", Path(entry.path) / ".pg_service.conf"]
                )
    except OSError:
        pass
    return _dedupe_paths(candidates)


async def _host_inspect_client_secret_file(
    host: HostAccess,
    path: Path,
) -> list[dict[str, Any]]:
    try:
        file_stat = await host.stat(path)
    except FileNotFoundError:
        return []
    except PermissionError:
        return [
            {
                "file_path": str(path),
                "finding_type": "permission",
                "file_mode": "",
                "risk_level": "medium",
                "risk_reason": "collector cannot stat PostgreSQL client secret file",
            }
        ]

    rows: list[dict[str, Any]] = []
    mode = stat.S_IMODE(file_stat.mode)
    if mode & 0o077:
        rows.append(
            {
                "file_path": str(path),
                "finding_type": "file_mode",
                "file_mode": _octal(mode),
                "risk_level": "high" if mode & 0o007 else "medium",
                "risk_reason": "PostgreSQL client secret file permissions are broader than owner-only",
            }
        )
    if path.name == ".pgpass":
        rows.append(
            {
                "file_path": str(path),
                "finding_type": "pgpass_present",
                "file_mode": _octal(mode),
                "risk_level": "medium",
                "risk_reason": ".pgpass file stores PostgreSQL connection secrets",
            }
        )
        return rows
    if path.name in {".pg_service.conf", "pg_service.conf"}:
        try:
            text = await host.read_text(path)
        except PermissionError:
            rows.append(
                {
                    "file_path": str(path),
                    "finding_type": "permission",
                    "file_mode": _octal(mode),
                    "risk_level": "medium",
                    "risk_reason": "collector cannot read PostgreSQL service file",
                }
            )
            return rows
        except OSError:
            return rows
        for line_number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            key = stripped.split("=", 1)[0].strip().lower() if "=" in stripped else ""
            if key == "password":
                rows.append(
                    {
                        "file_path": str(path),
                        "finding_type": "service_password",
                        "line_number": line_number,
                        "file_mode": _octal(mode),
                        "risk_level": "high",
                        "risk_reason": "PostgreSQL service file contains a password entry",
                    }
                )
    return rows


def _parse_octal(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(text, 8)
    except ValueError:
        return None


def _octal(value: int | None) -> str:
    if value is None:
        return ""
    return f"{value:04o}"


def _max_risk(levels: Any) -> str:
    best = "ok"
    for level in levels:
        normalized = str(level or "ok").lower()
        if RISK_RANK.get(normalized, -1) > RISK_RANK.get(best, -1):
            best = normalized
    return best


def _dedupe_rows(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for row in rows:
        marker = tuple(row.get(key) for key in keys)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(row)
    return result


async def _setting(ctx: PythonSourceContext, name: str) -> str:
    value = await ctx.conn.fetchval("select setting from pg_settings where name = $1", name)
    return str(value or "")


async def _setting_path(ctx: PythonSourceContext, name: str) -> Path | None:
    value = await _setting(ctx, name)
    if not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    data_directory = await _setting(ctx, "data_directory")
    if not data_directory:
        return path
    return Path(data_directory) / path


async def _log_directory(ctx: PythonSourceContext) -> Path | None:
    value = await _setting(ctx, "log_directory")
    if not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    data_directory = await _setting(ctx, "data_directory")
    if data_directory:
        return Path(data_directory) / path
    return path


async def _tablespaces(ctx: PythonSourceContext) -> list[dict[str, str]]:
    rows = await ctx.conn.fetch(
        """
        select spcname as name, pg_tablespace_location(oid) as path
        from pg_tablespace
        where pg_tablespace_location(oid) <> ''
        order by spcname
        """
    )
    return [{"name": str(row["name"]), "path": str(row["path"])} for row in rows]


async def _sensitive_roots(ctx: PythonSourceContext) -> list[Path]:
    roots: list[Path] = []
    for setting_name in ("data_directory",):
        path = await _setting_path(ctx, setting_name)
        if path:
            roots.append(path)
    log_directory = await _log_directory(ctx)
    if log_directory:
        roots.append(log_directory)
    for tablespace in await _tablespaces(ctx):
        roots.append(Path(tablespace["path"]))
    archive_command = await _setting(ctx, "archive_command")
    for path in _paths_from_command(archive_command):
        roots.append(path if await ctx.host.is_dir(path) else path.parent)
    return _dedupe_paths([root for root in roots if str(root) not in {"", "."}])


async def _host_permission_findings(
    host: HostAccess,
    path: Path,
    *,
    component: str,
    expected_mode: str,
    disallowed_bits: int,
    missing_ok: bool,
    permission_denied_is_finding: bool = True,
    risk_reason: str,
) -> list[dict[str, Any]]:
    try:
        file_stat = await host.stat(path)
    except FileNotFoundError:
        if missing_ok:
            return []
        return [
            {
                "path": str(path),
                "component": component,
                "file_mode": "",
                "expected_mode": expected_mode,
                "risk_level": "medium",
                "risk_reason": f"{component} path is missing",
            }
        ]
    except PermissionError:
        if not permission_denied_is_finding:
            return []
        return [
            {
                "path": str(path),
                "component": component,
                "file_mode": "",
                "expected_mode": expected_mode,
                "risk_level": "medium",
                "risk_reason": f"collector cannot stat {component} path",
            }
        ]
    except OSError as exc:
        return [
            {
                "path": str(path),
                "component": component,
                "file_mode": "",
                "expected_mode": expected_mode,
                "risk_level": "medium",
                "risk_reason": f"collector cannot inspect {component} path: {exc}",
            }
        ]
    mode = stat.S_IMODE(file_stat.mode)
    if not mode & disallowed_bits:
        return []
    return [
        {
            "path": str(path),
            "component": component,
            "file_mode": _octal(mode),
            "owner": file_stat.owner,
            "group": file_stat.group,
            "expected_mode": expected_mode,
            "risk_level": "high" if mode & 0o002 or mode & 0o004 else "medium",
            "risk_reason": risk_reason,
        }
    ]


async def _host_tls_private_key_findings(
    host: HostAccess,
    path: Path,
) -> list[dict[str, Any]]:
    try:
        file_stat = await host.stat(path)
    except FileNotFoundError:
        return [
            {
                "path": str(path),
                "component": "tls_private_key",
                "file_mode": "",
                "expected_mode": "0600, or root-owned with group-read only",
                "risk_level": "medium",
                "risk_reason": "PostgreSQL TLS private key path is missing",
            }
        ]
    except OSError as exc:
        return [
            {
                "path": str(path),
                "component": "tls_private_key",
                "file_mode": "",
                "expected_mode": "0600, or root-owned with group-read only",
                "risk_level": "medium",
                "risk_reason": f"collector cannot inspect PostgreSQL TLS private key: {exc}",
            }
        ]
    mode = stat.S_IMODE(file_stat.mode)
    owner_only = mode & 0o077 == 0
    root_group_read = file_stat.uid == 0 and mode & 0o077 == 0o040
    if owner_only or root_group_read:
        return []
    return [
        {
            "path": str(path),
            "component": "tls_private_key",
            "file_mode": _octal(mode),
            "owner": file_stat.owner,
            "group": file_stat.group,
            "expected_mode": "0600, or root-owned with group-read only",
            "risk_level": "high" if mode & 0o007 else "medium",
            "risk_reason": "PostgreSQL TLS private key permissions exceed supported owner/root-group-read patterns",
        }
    ]


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = os.path.normpath(str(path))
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _paths_from_command(command: str) -> list[Path]:
    paths: list[Path] = []
    for match in re.finditer(r"(?<![%\w])/(?:[^\s'\";|&<>]+)", command or ""):
        token = match.group(0).replace("%p", "").replace("%f", "")
        token = token.rstrip(")")
        if token:
            paths.append(Path(token))
    return _dedupe_paths(paths)


def _parse_systemctl_show_blocks(text: str) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        props: dict[str, str] = {}
        for line in block.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            props[key] = value
        if props:
            blocks.append(props)
    return blocks


def _service_hardening_rows(unit_name: str, props: dict[str, str]) -> list[dict[str, Any]]:
    checks = (
        ("NoNewPrivileges", props.get("NoNewPrivileges", ""), {"yes"}, "yes"),
        ("PrivateTmp", props.get("PrivateTmp", ""), {"yes"}, "yes"),
        ("ProtectSystem", props.get("ProtectSystem", ""), {"yes", "full", "strict"}, "full or strict"),
        ("ProtectHome", props.get("ProtectHome", ""), {"yes", "read-only", "tmpfs"}, "true, read-only, or tmpfs"),
    )
    rows: list[dict[str, Any]] = []
    for setting_name, value, allowed, expected in checks:
        if value in allowed:
            continue
        rows.append(
            {
                "unit_name": unit_name,
                "setting_name": setting_name,
                "value": value,
                "expected": expected,
                "risk_level": "medium",
                "risk_reason": "PostgreSQL systemd unit misses an effective hardening directive",
            }
        )

    capability_set = props.get("CapabilityBoundingSet", "")
    broad_caps = {
        "cap_dac_read_search",
        "cap_sys_admin",
        "cap_sys_module",
        "cap_sys_ptrace",
        "cap_sys_rawio",
    }
    present_broad_caps = sorted(cap for cap in broad_caps if cap in capability_set.split())
    if present_broad_caps:
        rows.append(
            {
                "unit_name": unit_name,
                "setting_name": "CapabilityBoundingSet",
                "value": " ".join(present_broad_caps),
                "expected": "empty or restricted set without broad admin capabilities",
                "risk_level": "medium",
                "risk_reason": "PostgreSQL systemd unit retains broad Linux capabilities",
            }
        )
    return rows


def _listen_is_loopback_only(value: str) -> bool:
    parts = [part.strip() for part in (value or "").split(",") if part.strip()]
    if not parts:
        return True
    loopback = {"localhost", "127.0.0.1", "::1"}
    return all(part in loopback for part in parts)


def _firewall_has_broad_accept(text: str, port: str) -> bool:
    port_pattern = re.compile(rf"(?<!\d){re.escape(port)}(?!\d)")
    for line in text.splitlines():
        lower = line.lower()
        if not port_pattern.search(lower):
            continue
        if "accept" in lower and ("0.0.0.0/0" in lower or "::/0" in lower or " anywhere" in lower or " any " in lower):
            return True
        if "allow" in lower and ("anywhere" in lower or "0.0.0.0/0" in lower or "::/0" in lower):
            return True
    return False


def _matching_firewall_lines(text: str, port: str) -> str:
    port_pattern = re.compile(rf"(?<!\d){re.escape(port)}(?!\d)")
    lines = [line.strip() for line in text.splitlines() if port_pattern.search(line)]
    return "\n".join(lines[:8])[:1000]


def _mount_table_from_text(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        rows.append({"source": parts[0], "mount": parts[1], "fstype": parts[2], "options": parts[3]})
    return rows


def _mount_for_path(path: Path, mounts: list[dict[str, str]]) -> dict[str, str] | None:
    resolved = Path(os.path.normpath(str(path)))
    best: dict[str, str] | None = None
    best_len = -1
    for mount in mounts:
        mount_path = Path(mount["mount"])
        try:
            is_relative = resolved == mount_path or resolved.is_relative_to(mount_path)
        except ValueError:
            is_relative = False
        if is_relative and len(mount_path.parts) > best_len:
            best = mount
            best_len = len(mount_path.parts)
    return best


async def _host_mount_for_path(
    ctx: PythonSourceContext,
    path: Path,
    mounts: list[dict[str, str]],
) -> dict[str, str] | None:
    try:
        resolved = Path(await ctx.host.realpath(path))
    except OSError:
        resolved = Path(os.path.normpath(str(path)))
    return _mount_for_path(resolved, mounts)


def _mount_looks_encrypted(source: str, fstype: str) -> bool:
    encrypted_fs = {"ecryptfs", "encfs", "fuse.encfs"}
    return fstype.lower() in encrypted_fs


def _encrypted_sources_from_lsblk(text: str) -> set[str] | None:
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return None

    encrypted: set[str] = set()

    def visit(node: dict[str, Any], encrypted_parent: bool = False) -> None:
        path = str(node.get("path") or "")
        is_encrypted = encrypted_parent or str(node.get("type") or "").lower() == "crypt"
        if is_encrypted and path:
            encrypted.add(path)
            encrypted.add(os.path.normpath(path))
        for child in node.get("children") or []:
            if isinstance(child, dict):
                visit(child, is_encrypted)

    for device in payload.get("blockdevices") or []:
        if isinstance(device, dict):
            visit(device)
    return encrypted


def _source_is_confirmed_encrypted(source: str, fstype: str, encrypted_sources: set[str]) -> bool:
    if _mount_looks_encrypted(source, fstype):
        return True
    candidates = {source, os.path.normpath(source)}
    return bool(candidates.intersection(encrypted_sources))


def _mentions_postgres_maintenance(path: Path, text: str) -> bool:
    haystack = f"{path} {text}".lower()
    return any(
        marker in haystack
        for marker in (
            "postgres",
            "pgsql",
            "pg_",
            "pgbackrest",
            "psql",
            "pg_dump",
            "pg_basebackup",
            "pg_ctl",
            "pg_ctlcluster",
        )
    )


async def _host_sudoers_files(ctx: PythonSourceContext) -> list[Path]:
    paths = [Path("/etc/sudoers")]
    try:
        paths.extend(Path(path) for path in await ctx.host.glob("/etc/sudoers.d/*"))
    except OSError:
        pass
    return _dedupe_paths([path for path in paths if await ctx.host.is_file(path)])


async def _host_postgres_systemd_files(
    ctx: PythonSourceContext,
    *,
    include_timers: bool = False,
) -> list[Path]:
    patterns = [
        "/lib/systemd/system/postgresql*.service",
        "/usr/lib/systemd/system/postgresql*.service",
        "/etc/systemd/system/postgresql*.service",
        "/etc/systemd/system/postgresql.service.d/*.conf",
        "/etc/systemd/system/postgresql@*.service.d/*.conf",
    ]
    if include_timers:
        patterns.extend(
            [
                "/lib/systemd/system/postgresql*.timer",
                "/usr/lib/systemd/system/postgresql*.timer",
                "/etc/systemd/system/postgresql*.timer",
                "/etc/systemd/system/*.timer",
                "/etc/systemd/system/*.service",
            ]
        )
    paths: list[Path] = []
    for pattern in patterns:
        try:
            paths.extend(Path(path) for path in await ctx.host.glob(pattern))
        except OSError:
            continue
    return _dedupe_paths([path for path in paths if await ctx.host.is_file(path)])


async def _host_postgres_systemd_unit_names(ctx: PythonSourceContext) -> list[str]:
    names = ["postgresql.service"]
    for setting_name in ("config_file", "data_directory"):
        value = await _setting(ctx, setting_name)
        match = re.search(r"/postgresql/(?P<version>[^/]+)/(?P<cluster>[^/]+)(?:/|$)", value)
        if match:
            names.append(f"postgresql@{match.group('version')}-{match.group('cluster')}.service")
    result = await ctx.host.run(
        (
            "systemctl",
            "list-units",
            "--type=service",
            "--all",
            "--plain",
            "--no-legend",
            "--no-pager",
        ),
    )
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            parts = line.split()
            if parts and re.match(r"^postgres(?:ql)?(?:[-@].*)?\.service$", parts[0]):
                names.append(parts[0])
    return list(dict.fromkeys(names))


async def _host_systemctl_service_hardening_findings(
    ctx: PythonSourceContext,
    unit_names: list[str],
) -> list[dict[str, Any]] | None:
    result = await ctx.host.run(
        (
            "systemctl",
            "show",
            "--property=Id,LoadState,NoNewPrivileges,PrivateTmp,ProtectSystem,ProtectHome,CapabilityBoundingSet",
            *unit_names,
        ),
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    rows: list[dict[str, Any]] = []
    loaded_units = 0
    for props in _parse_systemctl_show_blocks(result.stdout):
        unit_name = props.get("Id", "")
        if not unit_name:
            continue
        load_state = props.get("LoadState", "")
        if load_state and load_state not in {"loaded", "linked", "linked-runtime"}:
            continue
        loaded_units += 1
        rows.extend(_service_hardening_rows(unit_name, props))
    return rows if loaded_units else None


async def _host_candidate_history_files(ctx: PythonSourceContext) -> list[Path]:
    paths = [Path("/var/lib/postgresql/.psql_history")]
    env = await ctx.host.environ()
    if env.get("HOME"):
        paths.append(Path(env["HOME"]) / ".psql_history")
    try:
        for entry in await ctx.host.list_dir("/home"):
            if entry.stat.is_dir:
                paths.append(Path(entry.path) / ".psql_history")
    except OSError:
        pass
    return _dedupe_paths(paths)


async def _host_inspect_history_file(
    host: HostAccess,
    path: Path,
) -> list[dict[str, Any]]:
    try:
        file_stat = await host.stat(path)
    except FileNotFoundError:
        return []
    except PermissionError:
        return [
            {
                "file_path": str(path),
                "finding_type": "permission",
                "line_number": "",
                "file_mode": "",
                "risk_level": "medium",
                "risk_reason": "collector cannot stat PostgreSQL history file",
            }
        ]
    rows: list[dict[str, Any]] = []
    mode = stat.S_IMODE(file_stat.mode)
    if mode & 0o077:
        rows.append(
            {
                "file_path": str(path),
                "finding_type": "file_mode",
                "line_number": "",
                "file_mode": _octal(mode),
                "risk_level": "high" if mode & 0o007 else "medium",
                "risk_reason": "PostgreSQL history file permissions are broader than owner-only",
            }
        )
    try:
        text = await host.read_text(path, limit=1024 * 1024)
    except OSError:
        return rows
    sensitive_pattern = re.compile(
        r"\b(password|create\s+role|alter\s+role|pgpass|secret|token)\b",
        re.IGNORECASE,
    )
    for line_number, line in enumerate(text.splitlines(), start=1):
        if sensitive_pattern.search(line):
            rows.append(
                {
                    "file_path": str(path),
                    "finding_type": "sensitive_history_entry",
                    "line_number": line_number,
                    "file_mode": _octal(mode),
                    "risk_level": "high",
                    "risk_reason": "PostgreSQL history file contains potentially sensitive SQL or secret text",
                }
            )
            if len(rows) >= 20:
                break
    return rows


_BOUNDED_FIND_SCRIPT = r"""
set -eu
root="$1"
depth="$2"
frames="$3"
[ -e "$root" ] || exit 4
find -H "$root" -maxdepth "$depth" -printf '%m\0%y\0%p\0%l\0' |
  head -z -n "$frames"
"""


async def _host_tree_entries(
    ctx: PythonSourceContext,
    root: Path,
    *,
    max_depth: int,
    max_entries: int,
) -> tuple[list[tuple[int, str, str, str]], dict[str, Any]]:
    try:
        result = await ctx.host.run_script(
            _BOUNDED_FIND_SCRIPT,
            arguments=(str(root), str(max_depth), str((max_entries + 1) * 4)),
        )
    except (TimeoutError, CommandTimeoutError):
        raise
    except Exception as exc:
        return [], {
            "complete": False,
            "entries": 0,
            "reason": f"bounded scan failed under {root}: {exc}",
        }
    if result.returncode == 4:
        return [], {"complete": False, "entries": 0, "reason": f"root is unavailable: {root}"}
    if result.returncode != 0 and not result.stdout:
        return [], {
            "complete": False,
            "entries": 0,
            "reason": result.stderr.strip() or f"find failed under {root}",
        }
    fields = result.stdout.split("\0")
    if fields and fields[-1] == "":
        fields.pop()
    entries: list[tuple[int, str, str, str]] = []
    for index in range(0, len(fields) - 3, 4):
        try:
            mode = int(fields[index], 8)
        except ValueError:
            continue
        entries.append((mode, fields[index + 1], fields[index + 2], fields[index + 3]))
    truncated = len(entries) > max_entries
    entries = entries[:max_entries]
    reasons = []
    if truncated:
        reasons.append(f"entry scan limit {max_entries} reached under {root}")
    if result.stderr.strip():
        reasons.append(result.stderr.strip()[:500])
    return entries, {
        "complete": not reasons,
        "entries": len(entries),
        "reason": "; ".join(reasons),
    }


async def _host_world_writable_tree_findings(
    ctx: PythonSourceContext,
    root: Path,
    *,
    max_depth: int,
    max_rows: int,
    max_entries: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    entries, coverage = await _host_tree_entries(
        ctx, root, max_depth=max_depth, max_entries=max_entries
    )
    rows = [
        {
            "path": path,
            "root": str(root),
            "file_mode": _octal(mode),
            "risk_level": "high",
            "risk_reason": "Path under a PostgreSQL-sensitive tree is world-writable",
        }
        for mode, _kind, path, _target in entries
        if mode & 0o002
    ]
    if len(rows) > max_rows:
        rows = rows[:max_rows]
        coverage = {
            "complete": False,
            "entries": coverage["entries"],
            "reason": f"finding limit {max_rows} reached under {root}",
        }
    return rows, coverage


async def _host_symlink_findings(
    ctx: PythonSourceContext,
    root: Path,
    *,
    max_depth: int,
    max_rows: int,
    max_entries: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    entries, coverage = await _host_tree_entries(
        ctx, root, max_depth=max_depth, max_entries=max_entries
    )
    rows = [
        {
            "path": path,
            "root": str(root),
            "target": target,
            "risk_level": "medium",
            "risk_reason": "Symlink in a PostgreSQL-sensitive path requires target and ownership review",
        }
        for _mode, kind, path, target in entries
        if kind == "l"
    ]
    if len(rows) > max_rows:
        rows = rows[:max_rows]
        coverage = {
            "complete": False,
            "entries": coverage["entries"],
            "reason": f"finding limit {max_rows} reached under {root}",
        }
    return rows, coverage


async def _host_run_command(ctx: PythonSourceContext, args: tuple[str, ...]) -> str:
    try:
        result = await ctx.host.run(args)
    except (TimeoutError, CommandTimeoutError):
        raise
    except Exception:
        return ""
    return result.stdout if result.returncode == 0 else ""


async def _host_mount_table(ctx: PythonSourceContext) -> list[dict[str, str]]:
    try:
        text = await ctx.host.read_text("/proc/mounts")
    except OSError:
        return []
    return _mount_table_from_text(text)


async def _host_encrypted_block_sources(ctx: PythonSourceContext) -> set[str] | None:
    result = await ctx.host.run(
        ("lsblk", "--json", "--paths", "--output", "NAME,PATH,TYPE"),
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return _encrypted_sources_from_lsblk(result.stdout)


async def _host_cron_files(ctx: PythonSourceContext) -> list[Path]:
    paths: list[Path] = []
    for pattern in (
        "/etc/crontab",
        "/etc/cron.d/*",
        "/etc/cron.daily/*",
        "/etc/cron.hourly/*",
        "/etc/cron.weekly/*",
        "/etc/cron.monthly/*",
        "/var/spool/cron/crontabs/postgres",
        "/var/spool/cron/postgres",
    ):
        try:
            paths.extend(Path(path) for path in await ctx.host.glob(pattern))
        except OSError:
            continue
    return _dedupe_paths([path for path in paths if await ctx.host.is_file(path)])


async def _host_script_permission_findings(
    ctx: PythonSourceContext,
    parent_file: Path,
    line_number: int,
    script: Path,
) -> list[dict[str, Any]]:
    try:
        mode = stat.S_IMODE((await ctx.host.stat(script)).mode)
    except OSError:
        return []
    if not mode & 0o022:
        return []
    return [
        {
            "file_path": str(parent_file),
            "line_number": line_number,
            "script_path": str(script),
            "file_mode": _octal(mode),
            "risk_level": "high" if mode & 0o002 else "medium",
            "risk_reason": "PostgreSQL scheduled maintenance script is group/world writable",
        }
    ]


async def _host_inspect_cron_file(
    ctx: PythonSourceContext,
    path: Path,
) -> list[dict[str, Any]]:
    try:
        text = await ctx.host.read_text(path)
        mode = stat.S_IMODE((await ctx.host.stat(path)).mode)
    except OSError:
        return []
    if not _mentions_postgres_maintenance(path, text):
        return []
    rows: list[dict[str, Any]] = []
    if mode & 0o022:
        rows.append(
            {
                "file_path": str(path),
                "line_number": "",
                "script_path": "",
                "file_mode": _octal(mode),
                "risk_level": "high" if mode & 0o002 else "medium",
                "risk_reason": "Cron file related to PostgreSQL maintenance is group/world writable",
            }
        )
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or not _mentions_postgres_maintenance(path, stripped):
            continue
        for script in _paths_from_command(stripped):
            rows.extend(await _host_script_permission_findings(ctx, path, line_number, script))
    return rows


async def _host_inspect_systemd_exec_paths(
    ctx: PythonSourceContext,
    path: Path,
) -> list[dict[str, Any]]:
    try:
        text = await ctx.host.read_text(path)
    except OSError:
        return []
    if not _mentions_postgres_maintenance(path, text):
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.lower().startswith("execstart"):
            continue
        for script in _paths_from_command(stripped):
            rows.extend(await _host_script_permission_findings(ctx, path, line_number, script))
    return rows


__all__ = [
    *[
        name
        for name in (
            "Any",
            "Path",
            "PythonSourceContext",
            "PythonSourceResult",
            "os",
            "re",
            "stat",
        )
        if name in globals()
    ],
    *[name for name in globals() if name.startswith("_") and not name.startswith("__")],
    *[name for name in globals() if name.isupper()],
]
