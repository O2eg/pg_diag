# pg_hba Rules As Seen By The Server

This instruction belongs to report item `users_roles.hba_rules`. The item is backed by `roles.hba_rules` (trusted Python source).

## What this item shows
- Client authentication rules from `pg_hba_file_rules`, that is the rules PostgreSQL parsed from `pg_hba.conf`, in server evaluation order (`evaluation_order`); on PostgreSQL 16 and newer `rule_number` and `file_name` follow `include` directives, so a rule from an included file keeps its real priority even though its line number restarts.
- Connection type, databases, user names, address, netmask, authentication method, options, and the server-side parse `error` for invalid lines.
- Reading the view needs superuser or an explicit `GRANT SELECT ON pg_hba_file_rules`; otherwise the item is reported as unsupported and the host-based pg_hba items remain available.

## What to watch
- Rows with an `error`: the server ignores them, so the intended rule does not apply.
- `trust`, `password`, or `md5` methods, broad address ranges, and `all` databases or users.
- The order of rules: the first matching rule wins, so a broad rule evaluated before a strict one disables the strict one; use `evaluation_order`, not `line_number`, when included files are present.
- Rules for roles that no longer exist.

## Common fault causes
- Edits to `pg_hba.conf` with syntax errors that were never reloaded or checked.
- Rules appended at the end of the file after a catch-all rule.
- Included files or directories not present on the server.

## Automatic evaluation
- `high`: the server reports a parse error for the line.
- `ok`: all other rules; method and address risks are evaluated by the dedicated pg_hba items.
- The list covers 3,000 rules; `result_truncated` marks partial coverage.

## Related report items
- [cluster_inventory.pg_hba_insecure_auth_methods](#item-cluster_inventory.pg_hba_insecure_auth_methods) — Review insecure authentication methods from the file on the host.
- [cluster_inventory.pg_hba_broad_network_ranges](#item-cluster_inventory.pg_hba_broad_network_ranges) — Review broad address ranges.
- [cluster_inventory.remote_superuser_access](#item-cluster_inventory.remote_superuser_access) — Check network paths to superusers.
- [users_roles.ident_mappings](#item-users_roles.ident_mappings) — Review user name maps referenced by `map=` options.

## Checklist
- Fix lines with parse errors and reload PostgreSQL.
- Order rules from most specific to least specific.
- Remove rules for roles and networks that no longer exist.
