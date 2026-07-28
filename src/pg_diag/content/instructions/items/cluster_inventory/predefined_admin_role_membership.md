# Predefined Admin Role Membership

This instruction belongs to report item `cluster_inventory.predefined_admin_role_membership`.

This item lists non-superuser, non-system roles that inherit powerful PostgreSQL predefined roles.

## What this item shows
- Membership in roles such as `pg_read_server_files`, `pg_write_server_files`, `pg_execute_server_program`, `pg_read_all_data`, `pg_write_all_data`, `pg_use_reserved_connections`, and `pg_signal_autovacuum_worker` when those roles exist in the server version.
- Whether the member role can log in.
- Direct or inherited grant depth.

## What to watch
- Findings whose severity or evidence differs from the approved cluster security baseline.
- Broad access, weak authentication, sensitive-file exposure, or missing controls that compound other findings.

## Common fault causes
- Package or cloud defaults, legacy compatibility, incomplete hardening, or undocumented operational exceptions.
- A change in one security layer without corresponding role, HBA, filesystem, or extension controls.

## Automatic evaluation

- `high`: inherited capabilities include server-program execution, server-file write, all-data write, or subscription creation.
- `medium`: read-all, backend signaling, checkpoint, maintenance, monitoring, or related administrative capabilities.
- Findings exclude superusers because their authority already subsumes these roles.
- Traversal starts from the predefined administrative roles instead of expanding the complete role graph.
- `membership_truncated = true` means traversal reached the 3,000-row safety cap; displayed memberships are partial and must not be treated as a complete inventory.
- When traversal is truncated, a synthetic `[coverage]` row remains visible even if every sampled membership was otherwise filtered out; therefore truncation cannot be rendered as a clean `empty` item.

## Related report items
- [cluster_inventory.privileged_roles](#item-cluster_inventory.privileged_roles) — Review all elevated roles.
- [cluster_inventory.privilege_surface_by_role](#item-cluster_inventory.privilege_surface_by_role) — Inspect effective privileges inherited by members.
- [object_workload.direct_user_grants](#item-object_workload.direct_user_grants) — Check additional direct object access.

## Checklist
- Review file-access and all-data roles as high-impact privileges.
- Remove inherited admin roles from application users.
- Prefer narrowly scoped operational roles and audited escalation.
