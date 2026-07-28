# Object ACL Drift

This instruction belongs to report item `object_workload.object_acl_drift`.

This item finds same-kind objects in one schema with inconsistent ACL signatures inside bounded object samples.

## What this item shows
- Schema and object kind.
- Sampled object count and sampled number of distinct ACL signatures.
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
- Stored relations are selected by descending `relpages`, named non-storage objects alphabetically, and functions by descending calls.
- ACL signatures are hashes of ACL entries normalized by grantor, grantee, privilege type, and grantability, so ACL array element order does not create false drift.
- ACL normalization is limited by a conservative 3,000-row expansion budget derived from ACL-array cardinality and the maximum privileges per object kind. Independent budgets reserve up to 1,500 expanded privilege rows for stored relations, 1,000 for named non-storage relations, and 500 for functions, so one branch cannot displace every candidate from another. `acl_expansion_truncated` identifies objects omitted to keep expansion bounded.
- At most 3,000 schema/kind drift groups are returned. `candidate_sample_truncated` identifies a reached relation or function root limit; because extension ownership is checked after root selection, extension-owned roots can consume part of a truncated sample. `result_truncated` identifies output truncation.
- A `[coverage]` row remains visible when truncation produces no drift group, so `empty` is clean only when all three coverage flags are false.

## Related report items
- [object_workload.direct_user_grants](#item-object_workload.direct_user_grants) — Identify direct grants contributing to ACL drift.
- [object_workload.grant_option_holders](#item-object_workload.grant_option_holders) — Review principals able to propagate grants.
- [object_workload.unused_privileged_grants](#item-object_workload.unused_privileged_grants) — Check whether drifted grants appear unused.

## Checklist
- Compare grants for objects in the same application area.
- Reapply expected grants with migration tooling.
- Prefer default privileges for future objects.
