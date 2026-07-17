# Object ACL Drift

This instruction belongs to report item `object_workload.object_acl_drift`.

This item finds same-kind objects in one schema with inconsistent ACL signatures.

## What this item shows
- Schema and object kind.
- Number of distinct ACL signatures.
- Sample object names from the affected group.

## What to watch
- Findings that conflict with the approved ownership, privilege, or application-role baseline.
- Broad or unexpected access paths that can be combined with inherited role membership.

## Common fault causes
- Legacy grants or ownership left by migrations, role changes, extension upgrades, or manual administration.
- Intentional exceptions that were not documented or revalidated.

## Automatic evaluation

- Severity is `unknown`: unlike ACL signatures can be legitimate for different object purposes.
- The check identifies drift candidates but cannot infer the application privilege baseline.

## Related report items
- [object_workload.direct_user_grants](#item-object_workload.direct_user_grants) — Identify direct grants contributing to ACL drift.
- [object_workload.grant_option_holders](#item-object_workload.grant_option_holders) — Review principals able to propagate grants.
- [object_workload.unused_privileged_grants](#item-object_workload.unused_privileged_grants) — Check whether drifted grants appear unused.

## Checklist
- Compare grants for objects in the same application area.
- Reapply expected grants with migration tooling.
- Prefer default privileges for future objects.
