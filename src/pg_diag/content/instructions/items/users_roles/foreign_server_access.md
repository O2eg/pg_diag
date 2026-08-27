# Foreign Data Access By Role

This instruction belongs to report item `users_roles.foreign_server_access`. The item is backed by `roles.foreign_server_access` (SQL query).

## What this item shows
- `USAGE` privileges on foreign data wrappers and foreign servers by grantee, including default ACLs.
- User mappings from `pg_user_mappings`: which role or `PUBLIC` is mapped to which server and the names of mapping options.
- Option values are never collected; `mapping_options_visible` shows whether the server exposed them to the collector role.

## What to watch
- `PUBLIC` mappings or `PUBLIC` `USAGE` on servers, which let every role reach the remote system with shared credentials.
- Mappings whose option names include `password`; the remote credential is stored in the catalog.
- Servers granted to application roles that should not access external systems.

## Common fault causes
- `postgres_fdw` or `dblink` set up for one integration and reused by other roles.
- Shared service credentials stored in a `PUBLIC` mapping.

## Automatic evaluation
- This item is an inventory and assigns no risk to individual entries.
- The list covers 200 wrappers, 1,000 servers, and 1,000 entries per pool; coverage flags mark partial results and add a `[coverage]` row.

## Related report items
- [cluster_inventory.extensions](#item-cluster_inventory.extensions) — Confirm which foreign data wrapper extensions are installed.
- [cluster_inventory.installed_risky_extensions](#item-cluster_inventory.installed_risky_extensions) — Review high-impact extensions such as file-based wrappers.

## Checklist
- Replace `PUBLIC` mappings with per-role mappings.
- Limit server `USAGE` to integration roles.
- Store remote credentials outside the catalog where the wrapper supports it.
