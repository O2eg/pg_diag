# TLS Key File Permissions

This instruction belongs to report item `os.tls_key_file_permissions`.
It is backed by local Python source `security.tls_key_file_permissions`.

## What this item shows
- Active TLS key, certificate, CA, and CRL files when configured.
- File mode, owner, group, and risk reason.

## What to watch
- A private key readable by another account, writable certificate files, missing active key/certificate paths, or evidence the collector cannot stat.

## Automatic evaluation
- World access is `high`; unsupported group access and unavailable path evidence are `medium`. PostgreSQL's documented root-owned, group-read-only key pattern is accepted alongside owner-only access.
- When PostgreSQL TLS is disabled, the check is `skipped/unknown` as not applicable. It is not evidence that transport security is adequate.

## Common fault causes
- Key copied with a permissive mode, wrong service-account ownership, certificate automation changing permissions, or inaccessible container mounts.

## Related report items
- [overview.tls_server_configuration](#item-overview.tls_server_configuration) — Confirm that server TLS is enabled and configured.
- [cluster_inventory.pg_hba_tls_enforcement](#item-cluster_inventory.pg_hba_tls_enforcement) — Check whether HBA requires TLS.
- [overview.weak_tls_ciphers](#item-overview.weak_tls_ciphers) — Review the cipher policy using the key.

## Checklist
- Keep private keys owner-only readable, or use the documented root-owned group-read-only pattern when OS certificate management requires it.
- Ensure certificate support files are not group/world writable.
- Rotate exposed keys after permission exposure.
