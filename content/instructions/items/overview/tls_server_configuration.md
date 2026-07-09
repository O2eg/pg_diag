# TLS Server Configuration

This item reports TLS server settings that are disabled or weaker than the expected posture.

## What this item shows
- Whether server-side `ssl` is enabled.
- Minimum TLS protocol version.
- Missing certificate or private key settings when TLS is enabled.

## Checklist
- Enable TLS where clients connect over untrusted networks.
- Require TLSv1.2 or newer.
- Keep certificate and key files managed by the PostgreSQL OS account.
