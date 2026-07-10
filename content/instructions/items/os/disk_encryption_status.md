# Disk Encryption Evidence

This instruction belongs to `os.disk_encryption_status`, backed by local Python source `security.disk_encryption_status`.

## What this item shows
- PGDATA, log, tablespace, and inferred archive mount points.
- Filesystem type and backing source.
- Findings when encryption cannot be confirmed from encrypted filesystem type or `lsblk TYPE=crypt` ancestry.

## What to watch
- Sensitive paths on mounts with no locally confirmed encryption layer.

## Automatic evaluation
- Unconfirmed encryption is `medium`; it is not proof that storage is unencrypted.
- Generic `/dev/mapper/*` and `/dev/dm-*` names are not accepted as encryption evidence because ordinary LVM uses them too. Missing mount/lsblk evidence is `unsupported`; cloud or SAN encryption may be invisible locally.

## Common fault causes
- Plain LVM, cloud-provider encryption outside the guest, SAN encryption, container mount namespaces, or sensitive paths placed on an unexpected filesystem.

## Checklist
- Use volume or OS encryption where physical media exposure is in scope.
- Verify cloud volume encryption outside the database host.
- Treat this item as a heuristic and confirm storage policy manually.
