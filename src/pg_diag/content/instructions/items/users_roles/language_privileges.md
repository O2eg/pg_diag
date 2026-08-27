# Procedural Language Privileges

This instruction belongs to report item `users_roles.language_privileges`. The item is backed by `roles.language_privileges` (SQL query).

## What this item shows
- `USAGE` privileges on procedural languages by grantee, with `is_trusted`, `is_grantable`, the grantor, and `acl_is_default`.
- Languages without an explicit ACL use the built-in default, which grants `USAGE` to `PUBLIC`.
- Owner entries are omitted.

## What to watch
- Untrusted languages such as `plpython3u` or `plperlu`; only superusers can create functions in them regardless of `USAGE`, but their presence is itself a finding.
- Trusted languages revoked from `PUBLIC` when application deployment relies on them.
- Grantable language privileges held by non-administrative roles.

## Common fault causes
- Languages installed for one extension and left available cluster-wide.
- `REVOKE USAGE ON LANGUAGE ... FROM PUBLIC` applied on one server but not on its replicas or clones.

## Automatic evaluation
- This item is an inventory and assigns no risk to individual privileges.
- The list covers 200 languages and 3,000 ACL entries; coverage flags mark partial results.

## Related report items
- [cluster_inventory.installed_risky_extensions](#item-cluster_inventory.installed_risky_extensions) — Review untrusted languages and high-impact extensions.
- [cluster_inventory.extensions](#item-cluster_inventory.extensions) — See which extensions installed the languages.

## Checklist
- Remove untrusted languages that no extension requires.
- Decide explicitly whether `PUBLIC` should keep `USAGE` on trusted languages.
