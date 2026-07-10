from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any

from pg_diag.executors.python import (
    PythonSourceContext,
    PythonSourceResult,
    run_blocking,
    table_result,
)


RISK_RANK = {"ok": 0, "medium": 1, "high": 2}


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


def _candidate_client_secret_files() -> list[Path]:
    candidates: list[Path] = []
    for env_name in ("PGPASSFILE", "PGSERVICEFILE"):
        value = os.environ.get(env_name)
        if value:
            candidates.append(Path(value))

    pg_sysconf = os.environ.get("PGSYSCONFDIR")
    if pg_sysconf:
        candidates.append(Path(pg_sysconf) / "pg_service.conf")

    home = os.environ.get("HOME")
    if home:
        candidates.extend([Path(home) / ".pgpass", Path(home) / ".pg_service.conf"])

    candidates.extend([
        Path("/var/lib/postgresql/.pgpass"),
        Path("/var/lib/postgresql/.pg_service.conf"),
    ])

    try:
        for home_dir in Path("/home").iterdir():
            if not home_dir.is_dir():
                continue
            candidates.extend([home_dir / ".pgpass", home_dir / ".pg_service.conf"])
    except OSError:
        pass

    result = []
    seen = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def _inspect_client_secret_file(path: Path) -> list[dict[str, Any]]:
    try:
        file_stat = path.stat()
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

    rows = []
    mode = stat.S_IMODE(file_stat.st_mode)
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

    if path.name == ".pg_service.conf" or path.name == "pg_service.conf":
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
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
        roots.append(path if path.exists() and path.is_dir() else path.parent)
    return _dedupe_paths([root for root in roots if str(root) not in {"", "."}])


def _permission_findings(
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
        file_stat = path.stat()
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

    mode = stat.S_IMODE(file_stat.st_mode)
    if not mode & disallowed_bits:
        return []
    return [
        {
            "path": str(path),
            "component": component,
            "file_mode": _octal(mode),
            "owner": _uid_name(file_stat.st_uid),
            "group": _gid_name(file_stat.st_gid),
            "expected_mode": expected_mode,
            "risk_level": "high" if mode & 0o002 or mode & 0o004 else "medium",
            "risk_reason": risk_reason,
        }
    ]


def _tls_private_key_findings(path: Path) -> list[dict[str, Any]]:
    try:
        file_stat = path.stat()
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

    mode = stat.S_IMODE(file_stat.st_mode)
    owner_only = mode & 0o077 == 0
    root_group_read = file_stat.st_uid == 0 and mode & 0o077 == 0o040
    if owner_only or root_group_read:
        return []
    return [
        {
            "path": str(path),
            "component": "tls_private_key",
            "file_mode": _octal(mode),
            "owner": _uid_name(file_stat.st_uid),
            "group": _gid_name(file_stat.st_gid),
            "expected_mode": "0600, or root-owned with group-read only",
            "risk_level": "high" if mode & 0o007 else "medium",
            "risk_reason": "PostgreSQL TLS private key permissions exceed supported owner/root-group-read patterns",
        }
    ]


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path.resolve(strict=False))
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _owner_name(path: Path) -> str:
    try:
        return _uid_name(path.stat().st_uid)
    except OSError:
        return ""


def _mode_for_path(path: Path) -> str:
    try:
        return _octal(stat.S_IMODE(path.stat().st_mode))
    except OSError:
        return ""


def _uid_name(uid: int) -> str:
    try:
        import pwd

        return pwd.getpwuid(uid).pw_name
    except (ImportError, KeyError):
        return str(uid)


def _gid_name(gid: int) -> str:
    try:
        import grp

        return grp.getgrgid(gid).gr_name
    except (ImportError, KeyError):
        return str(gid)


def _paths_from_command(command: str) -> list[Path]:
    paths: list[Path] = []
    for match in re.finditer(r"(?<![%\w])/(?:[^\s'\";|&<>]+)", command or ""):
        token = match.group(0).replace("%p", "").replace("%f", "")
        token = token.rstrip(")")
        if token:
            paths.append(Path(token))
    return _dedupe_paths(paths)


def _sudoers_files() -> list[Path]:
    paths = [Path("/etc/sudoers")]
    sudoers_d = Path("/etc/sudoers.d")
    try:
        paths.extend(sorted(path for path in sudoers_d.iterdir() if path.is_file()))
    except OSError:
        pass
    return paths


def _postgres_systemd_files(*, include_timers: bool = False) -> list[Path]:
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
        paths.extend(Path("/").glob(pattern.lstrip("/")))
    return _dedupe_paths([path for path in paths if path.is_file()])


async def _postgres_systemd_unit_names(ctx: PythonSourceContext) -> list[str]:
    names = ["postgresql.service"]
    for setting_name in ("config_file", "data_directory"):
        value = await _setting(ctx, setting_name)
        match = re.search(r"/postgresql/(?P<version>[^/]+)/(?P<cluster>[^/]+)(?:/|$)", value)
        if match:
            names.append(f"postgresql@{match.group('version')}-{match.group('cluster')}.service")
    names.extend(await run_blocking(_discover_postgres_systemd_units))
    seen = set()
    result = []
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result


def _discover_postgres_systemd_units() -> list[str]:
    if not shutil.which("systemctl"):
        return []
    try:
        completed = subprocess.run(
            (
                "systemctl",
                "list-units",
                "--type=service",
                "--all",
                "--plain",
                "--no-legend",
                "--no-pager",
            ),
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
            env={**os.environ, "LC_ALL": "C", "LANG": "C"},
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0:
        return []
    names = []
    for line in completed.stdout.splitlines():
        parts = line.split()
        if not parts:
            continue
        name = parts[0]
        if re.match(r"^postgres(?:ql)?(?:[-@].*)?\.service$", name):
            names.append(name)
    return names


def _systemctl_service_hardening_findings(unit_names: list[str]) -> list[dict[str, Any]] | None:
    if not shutil.which("systemctl"):
        return None
    args = (
        "systemctl",
        "show",
        "--property=Id,LoadState,NoNewPrivileges,PrivateTmp,ProtectSystem,ProtectHome,CapabilityBoundingSet",
        *unit_names,
    )
    try:
        completed = subprocess.run(args, capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0 or not completed.stdout.strip():
        return None

    rows: list[dict[str, Any]] = []
    loaded_units = 0
    for props in _parse_systemctl_show_blocks(completed.stdout):
        unit_name = props.get("Id", "")
        if not unit_name:
            continue
        load_state = props.get("LoadState", "")
        if load_state and load_state not in {"loaded", "linked", "linked-runtime"}:
            continue
        loaded_units += 1
        rows.extend(_service_hardening_rows(unit_name, props))
    return rows if loaded_units else None


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


def _systemd_file_hardening_findings() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in _postgres_systemd_files():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lower = text.lower()
        checks = {
            "NoNewPrivileges": "nonewprivileges=true",
            "PrivateTmp": "privatetmp=true",
            "ProtectSystem": "protectsystem=strict",
            "ProtectHome": "protecthome=true",
            "CapabilityBoundingSet": "capabilityboundingset=",
        }
        for setting_name, required in checks.items():
            if setting_name == "ProtectSystem":
                present = "protectsystem=strict" in lower or "protectsystem=full" in lower
            elif setting_name == "ProtectHome":
                present = any(value in lower for value in ("protecthome=true", "protecthome=read-only", "protecthome=tmpfs"))
            else:
                present = required in lower
            if not present:
                rows.append(
                    {
                        "unit_file": str(path),
                        "setting_name": setting_name,
                        "expected": required,
                        "risk_level": "medium",
                        "risk_reason": "PostgreSQL systemd unit file misses a hardening directive",
                    }
                )
    return rows


def _read_proc_cmdline(proc_dir: Path) -> str:
    try:
        return proc_dir.joinpath("cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace").strip()
    except OSError:
        return ""


def _candidate_history_files() -> list[Path]:
    paths = [Path("/var/lib/postgresql/.psql_history")]
    home = os.environ.get("HOME")
    if home:
        paths.append(Path(home) / ".psql_history")
    try:
        for home_dir in Path("/home").iterdir():
            if home_dir.is_dir():
                paths.append(home_dir / ".psql_history")
    except OSError:
        pass
    return _dedupe_paths(paths)


def _inspect_history_file(path: Path) -> list[dict[str, Any]]:
    try:
        file_stat = path.stat()
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
    mode = stat.S_IMODE(file_stat.st_mode)
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
        text = path.read_text(encoding="utf-8", errors="replace")[:1024 * 1024]
    except OSError:
        return rows
    sensitive_pattern = re.compile(r"\b(password|create\s+role|alter\s+role|pgpass|secret|token)\b", re.IGNORECASE)
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


def _world_writable_tree_findings(
    root: Path,
    *,
    max_depth: int,
    max_rows: int,
    max_entries: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not root.exists():
        return rows, {"complete": False, "entries": 0, "reason": f"root is unavailable: {root}"}
    base_depth = len(root.parts)
    entries = 0
    errors: list[str] = []

    def onerror(exc: OSError) -> None:
        errors.append(str(exc))

    for dirpath, dirnames, filenames in os.walk(root, onerror=onerror):
        current = Path(dirpath)
        at_depth_limit = len(current.parts) - base_depth >= max_depth
        if at_depth_limit:
            dirnames[:] = []
        names = ["."] if at_depth_limit else ["."] + dirnames + filenames
        for name in names:
            entries += 1
            if entries > max_entries:
                return rows, {
                    "complete": False,
                    "entries": entries - 1,
                    "reason": f"entry scan limit {max_entries} reached under {root}",
                }
            path = current if name == "." else current / name
            try:
                mode = stat.S_IMODE(path.lstat().st_mode)
            except OSError as exc:
                errors.append(f"{path}: {exc}")
                continue
            if mode & 0o002:
                rows.append(
                    {
                        "path": str(path),
                        "root": str(root),
                        "file_mode": _octal(mode),
                        "risk_level": "high",
                        "risk_reason": "Path under a PostgreSQL-sensitive tree is world-writable",
                    }
                )
            if len(rows) >= max_rows:
                return rows, {
                    "complete": False,
                    "entries": entries,
                    "reason": f"finding limit {max_rows} reached under {root}",
                }
    return rows, {
        "complete": not errors,
        "entries": entries,
        "reason": "; ".join(errors[:3]),
    }


def _symlink_findings(
    root: Path,
    *,
    max_depth: int,
    max_rows: int,
    max_entries: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not root.exists():
        return rows, {"complete": False, "entries": 0, "reason": f"root is unavailable: {root}"}
    base_depth = len(root.parts)
    entries = 0
    errors: list[str] = []

    def onerror(exc: OSError) -> None:
        errors.append(str(exc))

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=onerror):
        current = Path(dirpath)
        at_depth_limit = len(current.parts) - base_depth >= max_depth
        if at_depth_limit:
            dirnames[:] = []
        names = [] if at_depth_limit else dirnames + filenames
        for name in names:
            entries += 1
            if entries > max_entries:
                return rows, {
                    "complete": False,
                    "entries": entries - 1,
                    "reason": f"entry scan limit {max_entries} reached under {root}",
                }
            path = current / name
            try:
                if not path.is_symlink():
                    continue
                target = os.readlink(path)
            except OSError as exc:
                errors.append(f"{path}: {exc}")
                continue
            rows.append(
                {
                    "path": str(path),
                    "root": str(root),
                    "target": target,
                    "risk_level": "medium",
                    "risk_reason": "Symlink exists under a PostgreSQL-sensitive path and should be verified",
                }
            )
            if len(rows) >= max_rows:
                return rows, {
                    "complete": False,
                    "entries": entries,
                    "reason": f"finding limit {max_rows} reached under {root}",
                }
    return rows, {
        "complete": not errors,
        "entries": entries,
        "reason": "; ".join(errors[:3]),
    }


def _listen_is_loopback_only(value: str) -> bool:
    parts = [part.strip() for part in (value or "").split(",") if part.strip()]
    if not parts:
        return True
    loopback = {"localhost", "127.0.0.1", "::1"}
    return all(part in loopback for part in parts)


def _run_command(args: tuple[str, ...]) -> str:
    if not shutil.which(args[0]):
        return ""
    try:
        completed = subprocess.run(args, capture_output=True, text=True, timeout=2, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout or ""


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


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _mount_options_for(mount_point: str) -> str:
    for row in _mount_table():
        if row["mount"] == mount_point:
            return row["options"]
    return ""


def _mount_table() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    try:
        text = Path("/proc/mounts").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return rows
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        rows.append({"source": parts[0], "mount": parts[1], "fstype": parts[2], "options": parts[3]})
    return rows


def _mount_for_path(path: Path, mounts: list[dict[str, str]]) -> dict[str, str] | None:
    try:
        resolved = path.resolve(strict=False)
    except OSError:
        resolved = path
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


def _mount_looks_encrypted(source: str, fstype: str) -> bool:
    encrypted_fs = {"ecryptfs", "encfs", "fuse.encfs"}
    return fstype.lower() in encrypted_fs


def _encrypted_block_sources() -> set[str] | None:
    if not shutil.which("lsblk"):
        return None
    try:
        completed = subprocess.run(
            ("lsblk", "--json", "--paths", "--output", "NAME,PATH,TYPE"),
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
            env={**os.environ, "LC_ALL": "C", "LANG": "C"},
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    try:
        payload = json.loads(completed.stdout)
    except (TypeError, ValueError):
        return None

    encrypted: set[str] = set()

    def visit(node: dict[str, Any], encrypted_parent: bool = False) -> None:
        path = str(node.get("path") or "")
        is_encrypted = encrypted_parent or str(node.get("type") or "").lower() == "crypt"
        if is_encrypted and path:
            encrypted.add(path)
            try:
                encrypted.add(str(Path(path).resolve(strict=False)))
            except OSError:
                pass
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
    candidates = {source}
    try:
        candidates.add(str(Path(source).resolve(strict=False)))
    except OSError:
        pass
    return bool(candidates.intersection(encrypted_sources))


def _cron_files() -> list[Path]:
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
        paths.extend(Path("/").glob(pattern.lstrip("/")))
    return _dedupe_paths([path for path in paths if path.is_file()])


def _inspect_cron_file(path: Path) -> list[dict[str, Any]]:
    rows = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return rows
    if not _mentions_postgres_maintenance(path, text):
        return rows
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
            rows.extend(_script_permission_findings(path, line_number, script))
    return rows


def _inspect_systemd_exec_paths(path: Path) -> list[dict[str, Any]]:
    rows = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return rows
    if not _mentions_postgres_maintenance(path, text):
        return rows
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.lower().startswith("execstart"):
            continue
        for script in _paths_from_command(stripped):
            rows.extend(_script_permission_findings(path, line_number, script))
    return rows


def _script_permission_findings(parent_file: Path, line_number: int, script: Path) -> list[dict[str, Any]]:
    try:
        mode = stat.S_IMODE(script.stat().st_mode)
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


def _environment_contains_pg_secret(environ: bytes) -> bool:
    try:
        entries = environ.decode("utf-8", errors="replace").split("\x00")
    except UnicodeDecodeError:
        return False
    uri_secret_pattern = re.compile(r"postgres(?:ql)?://[^:@/\s]+:[^@/\s]+@", re.IGNORECASE)
    for entry in entries:
        if not entry:
            continue
        if entry.startswith("PGPASSWORD=") and entry != "PGPASSWORD=":
            return True
        if uri_secret_pattern.search(entry):
            return True
    return False


__all__ = [
    *[
        name
        for name in (
            "Any",
            "Path",
            "PythonSourceContext",
            "PythonSourceResult",
            "run_blocking",
            "os",
            "re",
            "shutil",
            "stat",
            "subprocess",
        )
        if name in globals()
    ],
    *[name for name in globals() if name.startswith("_") and not name.startswith("__")],
    *[name for name in globals() if name.isupper()],
]
