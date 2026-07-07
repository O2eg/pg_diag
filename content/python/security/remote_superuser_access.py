from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result


HOST_TYPES = {"host", "hostssl", "hostnossl", "hostgssenc", "hostnogssenc"}
INCLUDE_DIRECTIVES = {"include", "include_if_exists", "include_dir"}


@dataclass(frozen=True)
class HbaEntry:
    file_path: str
    line_number: int
    raw_line: str
    fields: list[str]


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    hba_file = await ctx.conn.fetchval("select setting from pg_settings where name = 'hba_file'")
    superuser_rows = await ctx.conn.fetch(
        "select rolname from pg_roles where rolsuper order by rolname"
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

    superusers = {_value(row, "rolname") for row in superuser_rows}
    superusers.discard(None)
    superuser_roles = {name: {name} for name in superusers}
    for row in membership_rows:
        superuser = _value(row, "superuser")
        member_of = _value(row, "member_of")
        if superuser and member_of:
            superuser_roles.setdefault(superuser, {superuser}).add(member_of)

    if not hba_file:
        raise RuntimeError("PostgreSQL hba_file setting is empty or unavailable")

    hba_path = Path(str(hba_file))
    try:
        hba_entries = _read_hba_entries(hba_path)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"PostgreSQL reports hba_file as {hba_path}, but the file is not visible locally"
        ) from exc
    except PermissionError as exc:
        raise PermissionError(
            f"The collector cannot read PostgreSQL hba_file {hba_path}"
        ) from exc

    rows = []
    issues = []
    for entry in hba_entries:
        if not entry.fields or entry.fields[0] not in HOST_TYPES:
            continue
        row = _host_row(entry, superusers, superuser_roles)
        rows.append(row)
        if row["allows_superuser"]:
            issues.append(
                {
                    "severity": "high",
                    "title": "pg_hba.conf host rule allows remote superuser access",
                    "description": (
                        f"{row['file_path']}:{row['line_number']} allows "
                        f"{row['allowed_superusers']} through user field {row['user']!r}."
                    ),
                    "recommendation": (
                        "Remove superusers from host* rules, use local peer authentication for superusers, "
                        "and reload PostgreSQL configuration."
                    ),
                    "evidence": row,
                }
            )

    if issues:
        severity_level = "high"
        issue_block = {
            "summary": {
                "severity": "high",
                "status": "fail",
                "title": "Remote superuser access is allowed",
                "description": (
                    f"{len(issues)} pg_hba.conf host rule(s) allow network connections for PostgreSQL superusers."
                ),
                "recommendation": (
                    "Deny remote access for all superusers. Use non-superuser roles for remote administration "
                    "and SET ROLE or audited escalation where needed."
                ),
            },
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
                "message": f"Checked {len(rows)} host pg_hba.conf rule(s) from {hba_path}",
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


def _host_row(
    entry: HbaEntry,
    superusers: set[str],
    superuser_roles: dict[str, set[str]],
) -> dict[str, Any]:
    fields = entry.fields
    connection_type = fields[0]
    database = fields[1] if len(fields) > 1 else ""
    user = fields[2] if len(fields) > 2 else ""
    address = fields[3] if len(fields) > 3 else ""
    method = fields[4] if len(fields) > 4 else ""
    allowed = [] if method == "reject" else _allowed_superusers(user, Path(entry.file_path).parent, superusers, superuser_roles)
    return {
        "file_path": entry.file_path,
        "line_number": entry.line_number,
        "connection_type": connection_type,
        "database": database,
        "user": user,
        "address": address,
        "auth_method": method,
        "allows_superuser": bool(allowed),
        "allowed_superusers": ", ".join(allowed),
        "raw_line": entry.raw_line,
    }


def _allowed_superusers(
    user_field: str,
    base_dir: Path,
    superusers: set[str],
    superuser_roles: dict[str, set[str]],
) -> list[str]:
    tokens = _expand_hba_list(user_field, base_dir)
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


def _expand_hba_list(value: str, base_dir: Path, seen_files: set[Path] | None = None) -> list[str]:
    if seen_files is None:
        seen_files = set()
    tokens: list[str] = []
    for token in (part.strip() for part in value.split(",")):
        if not token:
            continue
        if token.startswith("@"):
            file_path = _resolve_hba_path(base_dir, token[1:])
            real_path = file_path.resolve()
            if real_path in seen_files:
                continue
            seen_files.add(real_path)
            try:
                for raw_line in real_path.read_text(encoding="utf-8").splitlines():
                    for child in _split_hba_line(raw_line):
                        tokens.extend(_expand_hba_list(child, real_path.parent, seen_files))
            except OSError:
                tokens.append(token)
            continue
        tokens.append(token)
    return tokens


def _resolve_hba_path(base_dir: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return base_dir / path


def _value(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return row[key]
