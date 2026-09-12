# Extension Objects ACL Drift

This instruction belongs to report item `object_workload.extension_objects_acl_drift`.

This item lists a bounded sample of extension-owned objects whose current ACL differs from the privileges recorded when the extension script ran (`pg_init_privs`).

## What this item shows
- Extension name.
- Object kind, schema, object name, the current ACL (`acl_text`) and the recorded extension baseline (`initial_acl_text`; empty when the object started with the default ACL).
- `added_privileges` / `removed_privileges`: grantee=privilege pairs present only in the current ACL or only in the baseline.
- Candidate processing reserves independent quotas for 2,000 relations ordered by `relpages` and 1,000 functions ordered by observed calls. The relation branch therefore cannot displace every function candidate.

## What to watch
- Findings that conflict with the approved ownership, privilege, or application-role baseline.
- Broad or unexpected access paths that can be combined with inherited role membership.

## Common fault causes
- Legacy grants or ownership left by migrations, role changes, extension upgrades, or manual administration.
- Intentional exceptions that were not documented or revalidated.

## Automatic evaluation

- Severity is `unknown`: a difference from the recorded extension baseline is a change to confirm, not proven harm.
- Results are bounded to 1,000 objects and are not a complete extension-object inventory; verify upgrade behavior before changing extension-owned ACLs.
- `relation_candidates_truncated`, `function_candidates_truncated`, and `result_truncated` identify incomplete coverage. A `[coverage]` row remains visible even when truncation produces no ordinary finding.
- The baseline is `pg_init_privs` (privilege type `e`), which PostgreSQL fills while `CREATE EXTENSION` / `ALTER EXTENSION UPDATE` scripts run; grants made by the script itself (for example to `pg_read_all_stats`) are therefore part of the baseline, while a later manual `GRANT ... TO pg_monitor` or `REVOKE` on the same object is listed as drift. An ACL identical to the baseline is not listed, whatever roles it names.

## Related report items
- [cluster_inventory.extensions](#item-cluster_inventory.extensions) — Identify the owning extension and its availability.
- [cluster_inventory.installed_risky_extensions](#item-cluster_inventory.installed_risky_extensions) — Check whether the extension has elevated risk.
- [object_workload.object_acl_drift](#item-object_workload.object_acl_drift) — Compare extension ACLs with broader object ACL drift.

## Checklist
- Confirm the ACL is intentional and survives extension upgrades.
- Avoid editing extension object grants unless required.
- Re-test extension upgrade paths after grant changes.
