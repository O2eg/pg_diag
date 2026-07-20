from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Any

from _pg_hba_common import (
    HOST_TYPES,
    HbaEntry,
    _host_address_and_auth_method,
    _host_read_hba_entries,
    _resolve_hba_path,
    _split_hba_line,
)
from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result


RISK_RANK = {"ok": 0, "unknown": 1, "medium": 2, "high": 3}


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    hba_file = await ctx.conn.fetchval("select setting from pg_settings where name = 'hba_file'")
    listen_addresses = await ctx.conn.fetchval(
        "select setting from pg_settings where name = 'listen_addresses'"
    )
    current_user = await ctx.conn.fetchval("select current_user")
    superuser_rows = await ctx.conn.fetch(
        "select rolname, rolcanlogin from pg_roles where rolsuper order by rolname"
    )
    membership_rows = await ctx.conn.fetch(
        """
        with recursive role_membership(member, roleid) as (
          select member, roleid
          from pg_auth_members
          union
          select rm.member, am.roleid
          from role_membership rm
          join pg_auth_members am on am.member = rm.roleid
        )
        select u.rolname as superuser, g.rolname as member_of
        from pg_roles u
        join role_membership rm on rm.member = u.oid
        join pg_roles g on g.oid = rm.roleid
        where u.rolsuper
        order by u.rolname, g.rolname
        """
    )

    superusers = set()
    login_superusers = set()
    for row in superuser_rows:
        rolname = _value(row, "rolname")
        if not rolname:
            continue
        superusers.add(str(rolname))
        if _as_bool(_value(row, "rolcanlogin")):
            login_superusers.add(str(rolname))
    superuser_roles = {name: {name} for name in superusers}
    for row in membership_rows:
        superuser = _value(row, "superuser")
        member_of = _value(row, "member_of")
        if superuser and member_of:
            superuser_roles.setdefault(superuser, {superuser}).add(member_of)

    if not hba_file:
        return _unavailable_result(
            "PostgreSQL hba_file setting is empty or unavailable",
            "security_remote_superuser_access_hba_file",
        )

    hba_path = Path(str(hba_file))
    try:
        hba_entries = await _host_read_hba_entries(ctx.host, hba_path)
    except FileNotFoundError:
        return _unavailable_result(
            f"PostgreSQL reports hba_file as {hba_path}, but the file is not visible locally",
            "security_remote_superuser_access_hba_file_missing",
        )
    except PermissionError:
        return _unavailable_result(
            f"The collector cannot read PostgreSQL hba_file {hba_path}",
            "security_remote_superuser_access_hba_file_permission",
        )

    rows = []
    issues = []
    for entry in hba_entries:
        if not entry.fields or entry.fields[0] not in HOST_TYPES:
            continue
        row = await _host_row(ctx, entry, superusers, superuser_roles)
        row = _classify_host_row(
            row,
            listen_addresses=str(listen_addresses or ""),
            login_superusers=login_superusers,
            current_user=str(current_user or ""),
        )
        rows.append(row)
        if row["allows_superuser"]:
            issues.append(_issue_for_row(row))

    if issues:
        severity_level = _max_severity(issue["severity"] for issue in issues)
        issue_block = {
            "summary": _issue_summary(issues, str(listen_addresses or ""), str(current_user or "")),
            "items": issues,
        }
    else:
        severity_level = "ok"
        issue_block = {
            "summary": {
                "severity": "ok",
                "status": "pass",
                "title": "Remote superuser access was not found",
                "description": "No host* pg_hba.conf rules were found that allow network access for superusers.",
                "recommendation": "Keep superuser access local-only and review pg_hba.conf after access changes.",
            },
            "items": [],
        }

    return PythonSourceResult(
        collection_status="ok",
        result=table_result(rows),
        issues=issue_block,
        severity_level=severity_level,
        diagnostics=[
            {
                "level": "info",
                "code": "security_remote_superuser_access",
                "message": (
                    f"Checked {len(rows)} host pg_hba.conf rule(s) from {hba_path}; "
                    f"listen_addresses={listen_addresses or ''}"
                ),
            }
        ],
    )


def _unavailable_result(reason: str, code: str) -> PythonSourceResult:
    return PythonSourceResult(
        collection_status="unsupported",
        reason=reason,
        result=table_result([]),
        diagnostics=[
            {
                "level": "warning",
                "code": code,
                "message": reason,
            }
        ],
    )


async def _host_row(
    ctx: PythonSourceContext,
    entry: HbaEntry,
    superusers: set[str],
    superuser_roles: dict[str, set[str]],
) -> dict[str, Any]:
    fields = entry.fields
    connection_type = fields[0]
    database = fields[1] if len(fields) > 1 else ""
    user = fields[2] if len(fields) > 2 else ""
    address, method = _host_address_and_auth_method(fields)
    matched = []
    if method != "reject":
        matched = await _allowed_superusers(
            ctx,
            user,
            Path(entry.file_path).parent,
            superusers,
            superuser_roles,
        )
    return {
        "file_path": entry.file_path,
        "line_number": entry.line_number,
        "connection_type": connection_type,
        "database": database,
        "user": user,
        "address": address,
        "auth_method": method,
        "matched_superuser_roles": ", ".join(matched),
        "raw_line": entry.raw_line,
    }


def _classify_host_row(
    row: dict[str, Any],
    *,
    listen_addresses: str,
    login_superusers: set[str],
    current_user: str,
) -> dict[str, Any]:
    matched = _csv_set(row["matched_superuser_roles"])
    allowed = sorted(matched.intersection(login_superusers))
    network_scope = _network_scope(row["address"])
    listen_reachable = _listen_reachable(network_scope, listen_addresses)
    auth_risk = _auth_risk(row["auth_method"])
    risk_level = _risk_level(
        allows_superuser=bool(allowed),
        network_scope=network_scope,
        listen_reachable=listen_reachable,
        auth_risk=auth_risk,
    )
    row.update(
        {
            "database_scope": _database_scope(row["database"]),
            "network_scope": network_scope,
            "listen_addresses": listen_addresses,
            "listen_reachable": listen_reachable,
            "auth_risk": auth_risk,
            "risk_level": risk_level,
            "allows_superuser": bool(allowed),
            "allowed_superusers": ", ".join(allowed),
            "current_database_user": current_user,
            "current_user_is_matched_superuser": bool(current_user and current_user in allowed),
        }
    )
    return row


def _issue_for_row(row: dict[str, Any]) -> dict[str, Any]:
    severity = row["risk_level"]
    title = _issue_title(row)
    description = (
        f"{row['file_path']}:{row['line_number']} allows {row['allowed_superusers']} "
        f"through user field {row['user']!r}; scope={row['network_scope']}, "
        f"listen_reachable={row['listen_reachable']}, auth={row['auth_method']}."
    )
    if row["current_user_is_matched_superuser"]:
        description += (
            f" Current database user {row['current_database_user']!r} is among the matched superusers."
        )
    return {
        "severity": severity,
        "title": title,
        "description": description,
        "recommendation": _recommendation_for_row(row),
        "evidence": row,
    }


def _issue_title(row: dict[str, Any]) -> str:
    roles = row["allowed_superusers"] or "superuser"
    if row["auth_risk"] == "trust":
        return (
            f"line {row['line_number']}: {row['network_scope']} trust rule allows "
            f"{roles}"
        )
    if row["network_scope"] not in {"loopback", "samehost"} and row["listen_reachable"] != "no":
        return (
            f"line {row['line_number']}: externally reachable rule allows "
            f"{roles} from {row['address']}"
        )
    return (
        f"line {row['line_number']}: {row['network_scope']} host rule allows "
        f"{roles} via {row['auth_method']}"
    )


def _recommendation_for_row(row: dict[str, Any]) -> str:
    if row["auth_risk"] == "trust":
        return (
            "Do not use trust authentication for login superusers. Prefer local peer authentication "
            "for postgres and password/cert authentication for non-superuser roles."
        )
    if row["network_scope"] not in {"loopback", "samehost"}:
        return (
            "Remove login superusers from non-loopback host* rules, narrow the address range, "
            "and use non-superuser roles for remote administration."
        )
    return (
        "Keep login superusers local-only where possible and avoid matching application roles "
        "that have rolsuper."
    )


def _issue_summary(issues: list[dict[str, Any]], listen_addresses: str, current_user: str) -> dict[str, Any]:
    severity = _max_severity(issue["severity"] for issue in issues)
    rows = [issue["evidence"] for issue in issues]
    external = [
        row for row in rows
        if row["network_scope"] not in {"loopback", "samehost"} and row["listen_reachable"] != "no"
    ]
    loopback = [row for row in rows if row["network_scope"] in {"loopback", "samehost"}]
    trust = [row for row in rows if row["auth_risk"] == "trust"]
    matched_roles = sorted({role for row in rows for role in _csv_set(row["allowed_superusers"])})

    if external:
        title = "Externally reachable superuser host access is allowed"
    elif trust:
        title = "Trust authentication allows local superuser access"
    else:
        title = "Host rules allow superuser access"

    parts = []
    if external:
        parts.append(f"{len(external)} non-loopback reachable rule(s)")
    if loopback:
        parts.append(f"{len(loopback)} loopback/samehost rule(s)")
    if trust:
        parts.append(f"{len(trust)} trust-auth rule(s)")
    description = (
        f"{', '.join(parts)} allow PostgreSQL login superusers through pg_hba.conf."
        if parts
        else "pg_hba.conf host rules allow PostgreSQL login superusers."
    )
    if matched_roles:
        description += f" Matched login superusers: {', '.join(matched_roles)}."
    if current_user and current_user in matched_roles:
        description += f" Current database user {current_user!r} is a superuser."
    description += f" listen_addresses={listen_addresses or '<empty>'}."

    return {
        "severity": severity,
        "status": "fail",
        "title": title,
        "description": description,
        "recommendation": (
            "Revoke rolsuper from application/login roles where possible, remove superusers from "
            "host* pg_hba.conf rules, restrict broad address ranges such as 0.0.0.0/0, and reload PostgreSQL."
        ),
    }


async def _allowed_superusers(
    ctx: PythonSourceContext,
    user_field: str,
    base_dir: Path,
    superusers: set[str],
    superuser_roles: dict[str, set[str]],
) -> list[str]:
    tokens = await _expand_hba_list(ctx, user_field, base_dir)
    if "all" in tokens:
        return sorted(superusers)

    allowed: set[str] = set()
    for token in tokens:
        if token in superusers:
            allowed.add(token)
            continue
        if token.startswith("+"):
            role_name = token[1:]
            for superuser, roles in superuser_roles.items():
                if role_name in roles:
                    allowed.add(superuser)
    return sorted(allowed)


def _database_scope(database_field: str) -> str:
    tokens = {token.lower() for token in _split_csv(database_field)}
    if "replication" in tokens:
        return "replication"
    if "all" in tokens:
        return "all"
    if not tokens:
        return "unknown"
    return "database"


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
    if network.version == 4 and network.prefixlen == 0:
        return "external"
    if network.version == 6 and network.prefixlen == 0:
        return "external"
    if network.is_private:
        return "private"
    if network.is_link_local:
        return "link_local"
    return "external"


def _listen_reachable(network_scope: str, listen_addresses: str) -> str:
    profile = _listen_profile(listen_addresses)
    if profile["unknown"]:
        return "unknown"
    if network_scope in {"loopback", "samehost"}:
        return "yes" if profile["loopback"] or profile["external"] else "no"
    if network_scope in {"external", "private", "link_local", "samenet", "hostname"}:
        return "yes" if profile["external"] else "no"
    return "unknown"


def _listen_profile(listen_addresses: str) -> dict[str, bool]:
    values = [token.strip().lower() for token in str(listen_addresses or "").split(",") if token.strip()]
    if not values:
        return {"loopback": False, "external": False, "unknown": True}

    loopback = False
    external = False
    unknown = False
    for value in values:
        if value == "*":
            loopback = True
            external = True
            continue
        if value in {"localhost", "127.0.0.1", "::1"}:
            loopback = True
            continue
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            unknown = True
            external = True
            continue
        if address.is_loopback:
            loopback = True
        else:
            external = True
    return {"loopback": loopback, "external": external, "unknown": unknown and not (loopback or external)}


def _auth_risk(method: str) -> str:
    value = str(method or "").strip().lower()
    if value == "reject":
        return "reject"
    if value == "trust":
        return "trust"
    if value in {"password", "md5", "scram-sha-256"}:
        return "password"
    if value == "cert":
        return "certificate"
    if value in {"gss", "sspi", "ident", "peer", "pam", "ldap", "radius", "oauth"}:
        return "external_auth"
    if not value:
        return "unknown"
    return "other"


def _risk_level(
    *,
    allows_superuser: bool,
    network_scope: str,
    listen_reachable: str,
    auth_risk: str,
) -> str:
    if not allows_superuser or auth_risk == "reject":
        return "ok"
    if auth_risk == "trust":
        return "high"
    if network_scope not in {"loopback", "samehost"} and listen_reachable != "no":
        return "high"
    return "medium"


def _max_severity(levels: Any) -> str:
    best = "ok"
    for level in levels:
        normalized = str(level or "unknown").lower()
        if RISK_RANK.get(normalized, -1) > RISK_RANK.get(best, -1):
            best = normalized
    return best


def _csv_set(value: str) -> set[str]:
    return {token for token in _split_csv(value) if token}


def _split_csv(value: str) -> list[str]:
    return [token.strip() for token in str(value or "").split(",") if token.strip()]


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "t", "true", "yes", "on"}


async def _expand_hba_list(
    ctx: PythonSourceContext,
    value: str,
    base_dir: Path,
    seen_files: set[str] | None = None,
) -> list[str]:
    if seen_files is None:
        seen_files = set()
    tokens: list[str] = []
    for token in (part.strip() for part in value.split(",")):
        if not token:
            continue
        if token.startswith("@"):
            file_path = _resolve_hba_path(base_dir, token[1:])
            try:
                real_path = Path(await ctx.host.realpath(file_path))
            except OSError:
                tokens.append(token)
                continue
            marker = str(real_path)
            if marker in seen_files:
                continue
            seen_files.add(marker)
            try:
                text = await ctx.host.read_text(real_path)
                for raw_line in text.splitlines():
                    for child in _split_hba_line(raw_line):
                        tokens.extend(
                            await _expand_hba_list(ctx, child, real_path.parent, seen_files)
                        )
            except OSError:
                tokens.append(token)
            continue
        tokens.append(token)
    return tokens


def _value(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return row[key]
