# Disk Encryption Status

This item checks whether PostgreSQL-sensitive paths appear to be on encrypted storage.

## What this item shows
- PGDATA, log, tablespace, and inferred archive mount points.
- Filesystem type and backing source.
- Heuristic findings when encryption is not obvious from local mount data.

## Checklist
- Use volume or OS encryption where physical media exposure is in scope.
- Verify cloud volume encryption outside the database host.
- Treat this item as a heuristic and confirm storage policy manually.
