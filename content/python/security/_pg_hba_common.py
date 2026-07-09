from __future__ import annotations

import ipaddress
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result


HOST_TYPES = {"host", "hostssl", "hostnossl", "hostgssenc", "hostnogssenc"}
CONNECTION_TYPES = {"local", *HOST_TYPES}
INCLUDE_DIRECTIVES = {"include", "include_if_exists", "include_dir"}
INSECURE_AUTH_METHODS = {"trust": "high", "password": "high", "ident": "high", "md5": "medium"}
RISK_RANK = {"ok": 0, "medium": 1, "high": 2}


@dataclass(frozen=True)
class HbaEntry:
    file_path: str
    line_number: int
    raw_line: str
    fields: list[str]

async def _read_hba_from_context(ctx: PythonSourceContext) -> tuple[list[HbaEntry], Path]:
    hba_file = await ctx.conn.fetchval("select setting from pg_settings where name = 'hba_file'")
    if not hba_file:
        raise RuntimeError("PostgreSQL hba_file setting is empty or unavailable")
    hba_path = Path(str(hba_file))
    try:
        return _read_hba_entries(hba_path), hba_path
    except FileNotFoundError:
        return _unsupported_read_result(
            f"PostgreSQL reports hba_file as {hba_path}, but the file is not visible locally",
            hba_path,
        )
    except PermissionError:
        return _unsupported_read_result(
            f"The collector cannot read PostgreSQL hba_file {hba_path}",
            hba_path,
        )


def _unsupported_read_result(reason: str, hba_path: Path) -> tuple[list[HbaEntry], Path]:
    raise PermissionError(reason) if "cannot read" in reason else FileNotFoundError(reason)


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


def _unavailable_code(exc: BaseException) -> str:
    if isinstance(exc, PermissionError):
        return "security_pg_hba_file_permission"
    return "security_pg_hba_file_missing"


def _entry_row(entry: HbaEntry) -> dict[str, Any] | None:
    if not entry.fields or entry.fields[0] not in CONNECTION_TYPES:
        return None
    connection_type = entry.fields[0]
    database = entry.fields[1] if len(entry.fields) > 1 else ""
    user = entry.fields[2] if len(entry.fields) > 2 else ""
    if connection_type == "local":
        address = ""
        auth_method = entry.fields[3] if len(entry.fields) > 3 else ""
    else:
        address, auth_method = _host_address_and_auth_method(entry.fields)
    return {
        "file_path": entry.file_path,
        "line_number": entry.line_number,
        "connection_type": connection_type,
        "database": database,
        "user": user,
        "address": address,
        "auth_method": auth_method,
        "raw_line": entry.raw_line,
    }


def _result(
    rows: list[dict[str, Any]],
    hba_path: Path,
    *,
    ok_title: str,
    fail_title: str,
    recommendation: str,
) -> PythonSourceResult:
    severity_level = _max_risk(row.get("risk_level") for row in rows)
    if rows:
        issues = {
            "summary": {
                "severity": severity_level,
                "status": "fail",
                "title": fail_title,
                "description": f"{len(rows)} pg_hba.conf rule(s) matched this security check.",
                "recommendation": recommendation,
            },
            "items": [
                {
                    "severity": row.get("risk_level", "medium"),
                    "title": f"line {row['line_number']}: {row.get('risk_reason', 'pg_hba.conf finding')}",
                    "description": row["raw_line"],
                    "recommendation": recommendation,
                    "evidence": row,
                }
                for row in rows
            ],
        }
    else:
        issues = {
            "summary": {
                "severity": "ok",
                "status": "pass",
                "title": ok_title,
                "description": f"Checked pg_hba.conf at {hba_path}.",
                "recommendation": "Keep pg_hba.conf rules narrow, explicit, and protected by strong authentication.",
            },
            "items": [],
        }
    return PythonSourceResult(
        collection_status="ok" if rows else "empty",
        result=table_result(rows),
        issues=issues,
        severity_level=severity_level,
        diagnostics=[
            {
                "level": "info",
                "code": "security_pg_hba_check",
                "message": f"Checked {len(rows)} matching pg_hba.conf rule(s) from {hba_path}",
            }
        ],
    )


def _read_hba_entries(path: Path, seen: set[Path] | None = None) -> list[HbaEntry]:
    real_path = path.resolve()
    if seen is None:
        seen = set()
    if real_path in seen:
        return []
    seen.add(real_path)

    entries: list[HbaEntry] = []
    for line_number, raw_line in enumerate(real_path.read_text(encoding="utf-8").splitlines(), start=1):
        fields = _split_hba_line(raw_line)
        if not fields:
            continue
        directive = fields[0]
        if directive in INCLUDE_DIRECTIVES:
            entries.extend(_read_include_entries(real_path, fields, seen))
            continue
        entries.append(HbaEntry(str(real_path), line_number, raw_line.strip(), fields))
    return entries


def _read_include_entries(current_file: Path, fields: list[str], seen: set[Path]) -> list[HbaEntry]:
    if len(fields) < 2:
        return []
    directive, include_ref = fields[0], fields[1]
    include_path = _resolve_hba_path(current_file.parent, include_ref)
    if directive == "include_if_exists" and not include_path.exists():
        return []
    if directive == "include_dir":
        if not include_path.is_dir():
            return []
        entries: list[HbaEntry] = []
        for child in sorted(include_path.iterdir()):
            if child.name.startswith(".") or child.suffix != ".conf" or not child.is_file():
                continue
            entries.extend(_read_hba_entries(child, seen))
        return entries
    return _read_hba_entries(include_path, seen)


def _split_hba_line(line: str) -> list[str]:
    try:
        return shlex.split(line, comments=True, posix=True)
    except ValueError:
        return []


def _network_range_risk(address: str) -> tuple[str, str] | None:
    value = str(address or "").strip().lower()
    if value in {"all", "0.0.0.0/0", "::/0"}:
        return "high", "pg_hba.conf rule allows clients from any address"
    try:
        network = ipaddress.ip_network(value, strict=False)
    except ValueError:
        return None
    if network.is_loopback:
        return None
    if network.version == 4 and network.prefixlen <= 8:
        return "high", f"IPv4 CIDR /{network.prefixlen} is very broad"
    if network.version == 4 and network.prefixlen <= 16:
        return "medium", f"IPv4 CIDR /{network.prefixlen} is broad"
    if network.version == 6 and network.prefixlen <= 32:
        return "high", f"IPv6 CIDR /{network.prefixlen} is very broad"
    if network.version == 6 and network.prefixlen <= 64:
        return "medium", f"IPv6 CIDR /{network.prefixlen} is broad"
    return None


def _host_address_and_auth_method(fields: list[str]) -> tuple[str, str]:
    address = fields[3] if len(fields) > 3 else ""
    if len(fields) >= 6 and _looks_like_ip_mask(address, fields[4]):
        return _address_with_prefix(address, fields[4]), fields[5]
    return address, fields[4] if len(fields) > 4 else ""


def _looks_like_ip_mask(address: str, mask: str) -> bool:
    try:
        ipaddress.ip_address(address)
        ipaddress.ip_address(mask)
    except ValueError:
        return False
    return True


def _address_with_prefix(address: str, mask: str) -> str:
    try:
        return ipaddress.ip_network(f"{address}/{mask}", strict=False).with_prefixlen
    except ValueError:
        return f"{address}/{mask}"


def _network_scope(address: str) -> str:
    value = str(address or "").strip().lower()
    if not value:
        return "unknown"
    if value == "samehost":
        return "samehost"
    if value == "samenet":
        return "samenet"
    if value in {"localhost", "local"}:
        return "loopback"
    if value in {"all", "0.0.0.0/0", "::/0"}:
        return "external"
    try:
        network = ipaddress.ip_network(value, strict=False)
    except ValueError:
        return "hostname"
    if network.is_loopback:
        return "loopback"
    if network.is_private:
        return "private"
    return "external"


def _insecure_auth_reason(auth_method: str) -> str:
    if auth_method == "trust":
        return "trust authentication allows login without a password"
    if auth_method == "password":
        return "password authentication sends cleartext password inside the PostgreSQL auth exchange"
    if auth_method == "ident":
        return "ident authentication trusts client-side identity service"
    if auth_method == "md5":
        return "md5 authentication is weaker than SCRAM-SHA-256"
    return "insecure authentication method"


def _max_risk(levels: Any) -> str:
    best = "ok"
    for level in levels:
        normalized = str(level or "ok").lower()
        if RISK_RANK.get(normalized, -1) > RISK_RANK.get(best, -1):
            best = normalized
    return best


def _split_csv(value: str) -> set[str]:
    return {token.strip().lower() for token in str(value or "").split(",") if token.strip()}


def _resolve_hba_path(base_dir: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return base_dir / path


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
            "shutil",
            "stat",
            "subprocess",
        )
        if name in globals()
    ],
    *[name for name in globals() if name.startswith("_") and not name.startswith("__")],
    *[name for name in globals() if name.isupper()],
]
