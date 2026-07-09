from __future__ import annotations

from _pg_hba_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    try:
        hba_entries, hba_path = await _read_hba_from_context(ctx)
    except (FileNotFoundError, PermissionError) as exc:
        return _unavailable_result(str(exc), _unavailable_code(exc))
    rows = []
    for entry in hba_entries:
        row = _entry_row(entry)
        if row is None:
            continue
        auth_method = str(row["auth_method"]).lower()
        if auth_method not in INSECURE_AUTH_METHODS:
            continue
        row["risk_level"] = INSECURE_AUTH_METHODS[auth_method]
        row["risk_reason"] = _insecure_auth_reason(auth_method)
        rows.append(row)
    return _result(
        rows,
        hba_path,
        ok_title="No insecure pg_hba.conf authentication methods found",
        fail_title="Insecure pg_hba.conf authentication methods found",
        recommendation=(
            "Replace trust/password/ident/md5 with peer for local administration, "
            "scram-sha-256 for password authentication, or external/certificate authentication where required."
        ),
    )
