from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    ssl_enabled = str(await _setting(ctx, "ssl") or "").lower() in {"on", "true", "1"}
    if not ssl_enabled:
        return _result(
            [],
            ok_title="TLS is disabled; no PostgreSQL TLS key file is active",
            fail_title="PostgreSQL TLS key file permissions are too broad",
            recommendation="When TLS is enabled, keep private keys readable only by the PostgreSQL OS account.",
            diagnostic_code="security_tls_key_file_permissions",
        )

    rows = []
    key_path = await _setting_path(ctx, "ssl_key_file")
    if key_path:
        rows.extend(
            _permission_findings(
                key_path,
                component="tls_private_key",
                expected_mode="0600",
                disallowed_bits=0o077,
                missing_ok=False,
                permission_denied_is_finding=False,
                risk_reason="PostgreSQL TLS private key is readable or writable by other OS users",
            )
        )
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
                missing_ok=True,
                risk_reason="PostgreSQL TLS support file is writable by group or other OS users",
            )
        )
    return _result(
        rows,
        ok_title="PostgreSQL TLS file permissions are restrictive",
        fail_title="PostgreSQL TLS file permissions are too broad",
        recommendation="Keep TLS private keys at 0600 and ensure certificate support files are not writable by untrusted OS users.",
        diagnostic_code="security_tls_key_file_permissions",
    )
