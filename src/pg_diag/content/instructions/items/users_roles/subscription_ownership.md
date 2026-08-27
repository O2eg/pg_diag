# Subscription Ownership

This instruction belongs to report item `users_roles.subscription_ownership`. The item is backed by `roles.subscription_ownership` (trusted Python source).

## What this item shows
- Logical replication subscriptions in every database of the cluster with the owner, whether the owner can log in or is a superuser, `enabled`, the replication slot name, and the subscribed publications.
- `in_current_database` marks subscriptions that apply changes into the connected database.
- Only the publicly readable columns of `pg_subscription` are read; the connection string, which can contain a password, is never collected.
- On PostgreSQL 14 and older `pg_subscription` is readable only by superusers; without that access the item is reported as unsupported instead of failing the report.

## What to watch
- Subscriptions owned by non-superusers on PostgreSQL 16 and newer; the owner's privileges decide what the apply worker can write.
- Disabled subscriptions whose slot on the publisher keeps WAL retained.
- Subscriptions that no longer match any publication on the publisher.

## Common fault causes
- Subscriptions created during a migration and disabled instead of dropped.
- Subscription ownership transferred to a role without `INSERT`, `UPDATE`, or `DELETE` on the target tables.
- Superuser-owned subscriptions that bypass row-level security on the subscriber.

## Automatic evaluation
- This item is an inventory and assigns no risk to individual subscriptions.
- The list covers 1,000 subscriptions; `result_truncated` marks partial coverage and sets the item severity to `unknown`.

## Related report items
- [replication.subscription_workers](#item-replication.subscription_workers) — Check the apply and sync workers of each subscription.
- [users_roles.publication_ownership](#item-users_roles.publication_ownership) — Review the publications on the publisher side when both roles run on one cluster.
- [replication.replication_slots](#item-replication.replication_slots) — Correlate disabled subscriptions with retained slots on the publisher.

## Checklist
- Drop subscriptions that are disabled permanently and remove their publisher slots.
- Assign subscriptions to a dedicated replication owner role with the needed table privileges.
- Verify that the subscription owner is the intended role after upgrades to PostgreSQL 16 and newer.
