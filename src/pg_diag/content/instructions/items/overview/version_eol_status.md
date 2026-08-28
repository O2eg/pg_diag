# Version End-Of-Life Status

This instruction belongs to report item `overview.version_eol_status`. The item is backed by `cluster.version_eol_status` (SQL query).

## What this item shows
- The running major version compared with the PostgreSQL community end-of-life schedule embedded in the report content.
- `days_to_eol` counts calendar days from the collection date to the published end-of-life date.
- An unknown major version (newer than the embedded schedule) reports `unknown` instead of guessing a date.

## What to watch
- A negative or small `days_to_eol`: the version stops receiving security and bug fixes.
- Minor version lag is not covered here; compare `server_version` with the latest minor release separately.

## Common fault causes
- Long-lived clusters installed once and never upgraded.
- Vendor images pinned to an old major version.

## Automatic evaluation
- `high` when the end-of-life date has passed, `medium` when it is less than a year away.
- `unknown` when the embedded schedule has no date for this major version; check postgresql.org/support/versioning.

## Related report items
- [overview.server_version](#item-overview.server_version) — Exact server version string and build details.

## Checklist
- Plan major upgrades at least a year before end of life.
- Keep minor versions current between major upgrades.
