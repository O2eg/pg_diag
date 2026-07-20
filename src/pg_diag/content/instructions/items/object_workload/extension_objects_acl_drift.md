# Extension Objects ACL Drift

This instruction belongs to report item `object_workload.extension_objects_acl_drift`.

This item lists extension-owned objects that have explicit ACL entries.

## What this item shows
- Extension name.
- Object kind, schema, object name, and ACL text.

## What to watch
- Findings that conflict with the approved ownership, privilege, or application-role baseline.
- Broad or unexpected access paths that can be combined with inherited role membership.

## Common fault causes
- Legacy grants or ownership left by migrations, role changes, extension upgrades, or manual administration.
- Intentional exceptions that were not documented or revalidated.

## Automatic evaluation

- Severity is `unknown`: an explicit ACL is not evidence of harmful drift without an extension baseline.
- Results are bounded to 1000 objects; verify upgrade behavior before changing extension-owned ACLs.

## Related report items
- [cluster_inventory.extensions](#item-cluster_inventory.extensions) — Identify the owning extension and its availability.
- [cluster_inventory.installed_risky_extensions](#item-cluster_inventory.installed_risky_extensions) — Check whether the extension has elevated risk.
- [object_workload.object_acl_drift](#item-object_workload.object_acl_drift) — Compare extension ACLs with broader object ACL drift.

## Checklist
- Confirm the ACL is intentional and survives extension upgrades.
- Avoid editing extension object grants unless required.
- Re-test extension upgrade paths after grant changes.
