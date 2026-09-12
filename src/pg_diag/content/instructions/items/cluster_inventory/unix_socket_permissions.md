# Unix Socket Permissions

This instruction belongs to report item `cluster_inventory.unix_socket_permissions`.

This item reports PostgreSQL Unix socket permissions that allow access by other OS users.

## What this item shows
- Configured `unix_socket_permissions`.
- Existing socket file mode when the socket is visible locally.
- Risk level for world-accessible socket permissions.

## What to watch
- Findings whose severity or evidence differs from the approved cluster security baseline.
- Broad access, weak authentication, sensitive-file exposure, or missing controls that compound other findings.

## Common fault causes
- Package or cloud defaults, legacy compatibility, incomplete hardening, or undocumented operational exceptions.
- A change in one security layer without corresponding role, HBA, filesystem, or extension controls.

## Automatic evaluation

- `medium`: the socket is world-accessible and its directory lets any OS user replace it; `unknown`: the default 0777 mode inside a protected directory.
- This is not an authentication bypass: matching `local` pg_hba rules still decide database access.
- Abstract sockets cannot be checked with filesystem permissions and are skipped.
- `0777` is the PostgreSQL default and `local` pg_hba rules decide whether a connection attempt succeeds, so the default alone is `unknown` (review). The row is `medium` only when the socket directory itself is world-writable without the sticky bit, because any OS user could then replace the socket path.

## Related report items
- [cluster_inventory.pg_hba_generic_database_or_user](#item-cluster_inventory.pg_hba_generic_database_or_user) — Review local identity matching in HBA.
- [cluster_inventory.pg_hba_insecure_auth_methods](#item-cluster_inventory.pg_hba_insecure_auth_methods) — Check authentication methods for local connections.
- [cluster_inventory.pgdata_permissions](#item-cluster_inventory.pgdata_permissions) — Compare socket and data-directory protection.

## Checklist
- Use `0700` or `0770` for `unix_socket_permissions` unless all local OS users are trusted.
- Keep socket directories owned and writable only by trusted users.
- Review local `pg_hba.conf` rules together with socket permissions.
