from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    ssl_enabled = str(await _setting(ctx, "ssl") or "").lower() in {"on", "true", "1"}
    if not ssl_enabled:
        return _not_applicable_result(
            "PostgreSQL TLS is disabled, so no active server key file can be checked",
            "security_tls_key_not_applicable",
        )

    rows = []
    key_path = await _setting_path(ctx, "ssl_key_file")
    if key_path:
        rows.extend(await run_blocking(_tls_private_key_findings, key_path))
    for setting_name, component in (
        ("ssl_cert_file", "tls_certificate"),
        ("ssl_ca_file", "tls_ca_file"),
        ("ssl_crl_file", "tls_crl_file"),
    ):
        path = await _setting_path(ctx, setting_name)
        if not path:
            continue
        rows.extend(
            _permission_findings(
                path,
                component=component,
                expected_mode="not group/world writable",
                disallowed_bits=0o022,
                missing_ok=setting_name in {"ssl_ca_file", "ssl_crl_file"},
                risk_reason="PostgreSQL TLS support file is writable by group or other OS users",
            )
        )
    return _result(
        rows,
        ok_title="PostgreSQL TLS file permissions are restrictive",
        fail_title="PostgreSQL TLS file permissions are too broad",
        recommendation="Keep TLS private keys owner-only, or root-owned with group-read only, and prevent untrusted writes to support files.",
        diagnostic_code="security_tls_key_file_permissions",
    )
