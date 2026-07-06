# OS Distribution

This instruction belongs to report item `os.os_release`. The item is backed by `os.os_release` (local host script).

## What this item shows
- Linux distribution name, version, ID, and codename from `/etc/os-release`
- Operating-system support context for PostgreSQL packages and tooling.

## What to watch
- Distribution version near EOL.
- Unexpected image, codename, or vendor for this database host.
- Different OS release between primary and standby hosts.

## Common fault causes
- Host rebuilt from a wrong base image.
- Repository migration incomplete.
- Managed image drift between nodes.

## Checklist
- Verify OS support lifecycle.
- Confirm PostgreSQL repository matches the OS release.
- Compare OS release across cluster nodes.
