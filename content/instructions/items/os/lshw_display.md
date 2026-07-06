# Graphics Adapters

This instruction belongs to report item `os.lshw_display`. The item is backed by `os.lshw_display` (local host script).

## What this item shows
- Display adapter inventory visible to lshw.
- Whether non-database GPU/display hardware is present.

## What to watch
- Unexpected GPU/display devices on a database server.
- Inventory collection errors.

## Common fault causes
- Generic server image with unused display devices.
- VM graphics adapter exposed by hypervisor.

## Checklist
- Treat this as inventory only.
- Confirm no GPU/display workload is colocated with PostgreSQL.
- Ignore normal virtual display adapters unless policy forbids them.
