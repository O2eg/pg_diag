# Core Dump Policy

This item checks whether core dump policy can expose PostgreSQL memory.

## What this item shows
- `fs.suid_dumpable`.
- `kernel.core_pattern`.

## Checklist
- Disable unsafe core dumps for PostgreSQL.
- Route dumps to a protected collector if dumps are required.
- Treat dumps as sensitive because they may contain data and credentials.
