from __future__ import annotations

from typing import Any

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result


RISK_RANK = {"ok": 0, "medium": 1, "high": 2}


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    try:
        records = await ctx.conn.fetch(
            """
            select
              usename as role_name,
              usesuper as is_superuser,
              usecreatedb as can_create_database,
              usesysid as role_oid,
              passwd as password_hash
            from pg_catalog.pg_shadow
            where passwd is not null
              and passwd <> ''
            order by usename asc
            """
        )
    except Exception as exc:
        reason = str(exc)
        return PythonSourceResult(
            collection_status="unsupported",
            reason=reason,
            result=table_result([]),
            severity_level="unknown",
            diagnostics=[
                {
                    "level": "warning",
                    "code": "security_role_password_hashes_unavailable",
                    "message": reason,
                }
            ],
        )

    rows = []
    for record in records:
        row = dict(record)
        password_hash = str(row.pop("password_hash") or "")
        classification = _classify_password_hash(password_hash)
        if classification is None:
            continue
        hash_type, risk_level, risk_reason = classification
        rows.append(
            {
                "role_name": row.get("role_name"),
                "is_superuser": row.get("is_superuser"),
                "can_create_database": row.get("can_create_database"),
                "role_oid": row.get("role_oid"),
                "hash_type": hash_type,
                "risk_level": risk_level,
                "risk_reason": risk_reason,
            }
        )

    severity_level = _max_risk(row.get("risk_level") for row in rows)
    if rows:
        issues = {
            "summary": {
                "severity": severity_level,
                "status": "fail",
                "title": "Weak or non-SCRAM role password hashes found",
                "description": f"{len(rows)} login role password hash(es) are weaker than SCRAM-SHA-256 or unknown.",
                "recommendation": "Reset affected role passwords after setting password_encryption to scram-sha-256.",
            },
            "items": [
                {
                    "severity": row["risk_level"],
                    "title": f"{row['role_name']}: {row['risk_reason']}",
                    "description": f"Role {row['role_name']} uses {row['hash_type']} password storage.",
                    "recommendation": "Reset this role password with SCRAM-SHA-256 enabled.",
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
                "title": "No weak role password hashes found",
                "description": "All visible role password hashes are SCRAM-SHA-256 or no hashes were visible.",
                "recommendation": "Keep password_encryption set to scram-sha-256 and rotate old MD5 hashes.",
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
                "code": "security_role_password_hashes",
                "message": f"Collected {len(rows)} weak or unknown role password hash finding(s)",
            }
        ],
    )


def _classify_password_hash(value: str) -> tuple[str, str, str] | None:
    text = str(value or "")
    if text.startswith("SCRAM-SHA-256$"):
        return None
    if text.startswith("md5"):
        return "md5", "high", "role password hash uses MD5"
    if text.startswith("SCRAM-"):
        return None
    return "unknown", "medium", "role password hash format is not SCRAM-SHA-256"


def _max_risk(levels: Any) -> str:
    best = "ok"
    for level in levels:
        normalized = str(level or "ok").lower()
        if RISK_RANK.get(normalized, -1) > RISK_RANK.get(best, -1):
            best = normalized
    return best
