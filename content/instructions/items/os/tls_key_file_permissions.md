# TLS Key File Permissions

This item checks PostgreSQL TLS private key and support file permissions.

## What this item shows
- Active TLS key, certificate, CA, and CRL files when configured.
- File mode, owner, group, and risk reason.

## Checklist
- Keep private keys owner-only readable.
- Ensure certificate support files are not group/world writable.
- Rotate exposed keys after permission exposure.
