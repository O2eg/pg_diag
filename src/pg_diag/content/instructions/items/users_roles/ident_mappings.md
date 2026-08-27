# pg_ident User Name Maps

This instruction belongs to report item `users_roles.ident_mappings`. The item is backed by `roles.ident_mappings` (trusted Python source).

## What this item shows
- User name maps from `pg_ident_file_mappings`, that is the maps PostgreSQL parsed from `pg_ident.conf`, with map name, operating-system or external user name, the PostgreSQL role, and the server-side parse `error`, ordered by `evaluation_order`.
- The view exists on PostgreSQL 15 and newer; `map_number` and `file_name` for `include` directives exist on PostgreSQL 16 and newer. Reading it needs superuser or an explicit `GRANT SELECT`; otherwise the item is reported as unsupported.

## What to watch
- Rows with an `error`: the map entry is ignored and the authentication rule that references it fails or falls through.
- Maps that let one external identity log in as a superuser or owner role.
- Regular-expression maps (`/...`) that match more identities than intended.

## Common fault causes
- Maps edited together with `pg_hba.conf` but never reloaded.
- Maps kept for operating-system users that no longer exist.
- Certificate common names or Kerberos principals renamed without updating the map.

## Automatic evaluation
- `high`: the server reports a parse error for the line.
- `ok`: all other mappings.
- The list covers 3,000 mappings; a `[coverage]` row marks partial coverage while listed findings keep their severity.

## Related report items
- [users_roles.hba_rules](#item-users_roles.hba_rules) — Find the authentication rules that reference each map.
- [users_roles.roles_inventory](#item-users_roles.roles_inventory) — Confirm that mapped roles exist and have the expected attributes.

## Checklist
- Fix lines with parse errors and reload PostgreSQL.
- Remove maps for identities that no longer exist.
- Keep regular-expression maps as narrow as possible.
