# PostgreSQL Full Version

This instruction belongs to report item `overview.server_version`. The item is backed by `cluster.server_version` (SQL query).

## What this item shows
- The exact PostgreSQL server version string reported by the connected server.
- The PostgreSQL major and minor version, package source, build platform, compiler, and architecture when present.
- A baseline for supportability, patch status, and upgrade verification.

## What to watch
- Server not on the latest minor release for its major version.
- Major version close to end of life or already unsupported.
- Package source or build string different from the expected vendor, distribution, or managed-service runtime.
- Version differs from the expected value after upgrade, failover, restore, or maintenance.

## Common fault causes
- Missed minor release updates, leaving bug fixes or security fixes unapplied.
- Standby, restored environment, image, or replica not upgraded with the primary.
- Package repository or managed-service track pinned to an older minor version.
- Clients connected to a different instance or binary than expected.

## Automatic evaluation
- This item is informational and does not assign severity from the version string.
- Determining latest minor release, vendor support, and end-of-life status requires a maintained external release/support dataset.

## Related report items
- [overview.pg_config](#item-overview.pg_config) — Compare the server build with the installed PostgreSQL toolchain.
- [overview.pg_controldata](#item-overview.pg_controldata) — Verify control-file compatibility and cluster identity.

## Checklist
- Check latest PostgreSQL minor releases at `https://www.postgresql.org/`
- Check support policy at `https://www.postgresql.org/support/versioning/`
- Review security guidance at `https://www.postgresql.org/support/security/`
- Review release notes at `https://www.postgresql.org/docs/release/`
- Confirm primaries, standbys, replicas, containers, and maintenance images all report the intended version after patching.
