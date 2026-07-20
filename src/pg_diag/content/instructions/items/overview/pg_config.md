# PostgreSQL pg_config

This instruction belongs to report item `overview.pg_config`. The item is backed by `cluster.pg_config` (Bash script).

## What this item shows
- The exact `pg_config` executable selected from the database host `PATH`.
- PostgreSQL installation directories for binaries, libraries, headers, extensions, documentation, and shared data.
- Build-time compiler, linker, configure, and feature options reported by that executable.
- The PostgreSQL version associated with the installed development files and client tools.

## What to watch
- `VERSION` differs from the connected PostgreSQL server major version.
- `BINDIR`, `PKGLIBDIR`, or `SHAREDIR` points to an unexpected PostgreSQL installation.
- Include and library paths mix files from different PostgreSQL major versions or package sources.
- `CONFIGURE`, compiler, or linker options differ between hosts expected to run identical PostgreSQL builds.

## Automatic evaluation
- This item is informational and does not assign severity automatically.
- A mismatch is not always a server fault because `pg_config` describes the binary found in `PATH`; a host can intentionally contain several PostgreSQL installations.

## Common fault causes
- An older PostgreSQL package appears earlier in `PATH`.
- Server, client, and development packages were installed from different repositories or versions.
- A source build and a distribution package coexist on the same host.
- Extension compilation uses headers or libraries from a different PostgreSQL installation.

## Related report items
- [overview.server_version](#item-overview.server_version) — Confirm that pg_config belongs to the running server major version.
- [cluster_inventory.extensions](#item-cluster_inventory.extensions) — Check extension availability for this PostgreSQL installation.

## Checklist
- Compare `VERSION` with PostgreSQL Full Version directly above this item.
- Verify `PG_CONFIG`, `BINDIR`, `PKGLIBDIR`, `INCLUDEDIR-SERVER`, and `SHAREDIR` against the intended installation.
- Use the displayed `PG_CONFIG` path explicitly when building extensions on hosts with multiple PostgreSQL versions.
- Compare build flags across primary and standby hosts when binary parity is required.
