# Multimedia Devices

This instruction belongs to report item `os.lshw_multimedia`. The item is backed by `os.lshw_multimedia` (local host script).

## What this item shows
- Multimedia/audio device inventory visible to lshw.
- Non-database peripheral context.

## What to watch
- Unexpected multimedia hardware on a database server.
- Virtual audio devices exposed by host image.

## Common fault causes
- Generic VM template.
- Desktop-class host image.
- Hypervisor defaults.

## Automatic evaluation
- No severity is assigned; multimedia devices are inventory-only evidence.
- Empty output is normal on server systems.

## Checklist
- Treat as inventory only.
- Remove or disable devices only if policy requires it.
- Ignore for PostgreSQL performance triage.
