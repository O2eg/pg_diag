# Publication Ownership

This instruction belongs to report item `users_roles.publication_ownership`. The item is backed by `roles.publication_ownership` (SQL query).

## What this item shows
- Logical replication publications in the connected database with the owner, whether the owner can log in or is a superuser, `all_tables`, the published operations, and `publish_via_partition_root` where the version supports it.
- `sampled_table_count` counts explicitly published tables from `pg_publication_rel`; `FOR ALL TABLES` publications show zero because their tables are implicit.

## What to watch
- `FOR ALL TABLES` publications, which also publish future tables and sensitive data that was never reviewed.
- Publications owned by login or application roles; the owner controls which tables leave the database.
- Publications that publish `DELETE` and `TRUNCATE` to subscribers that must keep history.

## Common fault causes
- Publications created by a migration account and never reassigned to the owner role.
- Broad publications created for an initial data copy and left in place.
- Ownership changed to a role without privileges on the published tables, which breaks row filters or column lists.

## Automatic evaluation
- This item is an inventory and assigns no risk to individual publications.
- The list covers 1,000 publications and 10,000 table memberships; coverage flags mark partial results and set the item severity to `unknown`.

## Related report items
- [users_roles.subscription_ownership](#item-users_roles.subscription_ownership) — Review the subscriptions that consume these publications.
- [replication.replication_slots](#item-replication.replication_slots) — Check the logical slots created for subscribers.
- [users_roles.object_ownership_by_role](#item-users_roles.object_ownership_by_role) — Confirm that publication owners also own the published tables.

## Checklist
- Restrict `FOR ALL TABLES` publications to cases where every table may leave the database.
- Assign publications to a dedicated replication owner role.
- Review published operations against subscriber expectations.
