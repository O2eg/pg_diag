# Unused Privileged Grants

This instruction belongs to report item `object_workload.unused_privileged_grants`.

This item lists powerful table privileges on tables with no observed activity since statistics reset.

## What this item shows
- Table, grantee, privilege, and grant option flag.
- Read and write activity counters from `pg_stat_user_tables`.

## What to watch
- Findings that conflict with the approved ownership, privilege, or application-role baseline.
- Broad or unexpected access paths that can be combined with inherited role membership.

## Common fault causes
- Legacy grants or ownership left by migrations, role changes, extension upgrades, or manual administration.
- Intentional exceptions that were not documented or revalidated.

## Automatic evaluation

- Severity is `unknown`: zero cumulative table activity cannot prove that a privilege is unused.
- `stats_reset` defines the observation start, and standby, failover, seasonal, or maintenance paths may be absent.
- Results are bounded to 1000 grants.

## Related report items
- [object_workload.direct_user_grants](#item-object_workload.direct_user_grants) — Review whether the unused grant was assigned directly.
- [cluster_inventory.privilege_surface_by_role](#item-cluster_inventory.privilege_surface_by_role) — Check inherited and effective role privileges.
- [object_workload.grant_option_holders](#item-object_workload.grant_option_holders) — Identify principals that can re-grant access.

## Checklist
- Treat findings as revoke candidates, not proof of unused access.
- Check the reported `stats_reset` before acting.
- Revoke stale write privileges after application-owner confirmation.
