from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    port = str(await _setting(ctx, "port") or "5432")
    listen_addresses = str(await _setting(ctx, "listen_addresses") or "")
    if _listen_is_loopback_only(listen_addresses):
        return _result(
            [],
            ok_title="PostgreSQL listens on loopback only",
            fail_title="PostgreSQL network exposure is not covered by visible local firewall rules",
            recommendation="Keep PostgreSQL bound to trusted interfaces or restrict access with host firewall rules.",
            diagnostic_code="security_firewall_postgres_exposure",
        )

    firewall_text = "\n".join(
        output
        for output in (
            _run_command(("nft", "list", "ruleset")),
            _run_command(("iptables", "-S")),
            _run_command(("ufw", "status", "verbose")),
        )
        if output
    )
    rows = []
    if not firewall_text:
        rows.append(
            {
                "port": port,
                "listen_addresses": listen_addresses,
                "firewall_evidence": "",
                "risk_level": "medium",
                "risk_reason": "PostgreSQL listens beyond loopback and local firewall rules could not be inspected",
            }
        )
    elif _firewall_has_broad_accept(firewall_text, port):
        rows.append(
            {
                "port": port,
                "listen_addresses": listen_addresses,
                "firewall_evidence": _matching_firewall_lines(firewall_text, port),
                "risk_level": "high",
                "risk_reason": "Local firewall rules appear to allow broad access to the PostgreSQL port",
            }
        )
    elif port not in firewall_text:
        rows.append(
            {
                "port": port,
                "listen_addresses": listen_addresses,
                "firewall_evidence": "",
                "risk_level": "medium",
                "risk_reason": "PostgreSQL listens beyond loopback and no local firewall rule mentioning the port was visible",
            }
        )
    return _result(
        rows,
        ok_title="No broad local firewall exposure detected for PostgreSQL",
        fail_title="PostgreSQL firewall exposure findings found",
        recommendation="Restrict the PostgreSQL port to trusted source networks at the host firewall and network perimeter.",
        diagnostic_code="security_firewall_postgres_exposure",
    )
