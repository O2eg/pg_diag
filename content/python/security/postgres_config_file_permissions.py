from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    paths: list[Path] = []
    for setting_name in ("config_file", "ident_file"):
        path = await _setting_path(ctx, setting_name)
        if path:
            paths.append(path)

    data_directory = await _setting_path(ctx, "data_directory")
    if data_directory:
        paths.append(data_directory / "postgresql.auto.conf")

    config_file = await _setting_path(ctx, "config_file")
    if config_file:
        confd = config_file.parent / "conf.d"
        try:
            paths.extend(sorted(confd.glob("*.conf")))
        except OSError:
            pass

    rows = []
    for path in _dedupe_paths(paths):
        rows.extend(
            _permission_findings(
                path,
                component="postgresql_config_file",
                expected_mode="0600 or 0640",
                disallowed_bits=0o037,
                missing_ok=True,
                risk_reason="PostgreSQL configuration file permissions are broader than expected",
            )
        )
    return _result(
        rows,
        ok_title="PostgreSQL configuration file permissions are restrictive",
        fail_title="PostgreSQL configuration file permissions are too broad",
        recommendation="Keep PostgreSQL configuration files at 0600 or 0640 and writable only by PostgreSQL administrators.",
        diagnostic_code="security_postgres_config_file_permissions",
    )
