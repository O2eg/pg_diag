# Security Definer Owner Drift

This instruction belongs to report item `object_workload.security_definer_owner_drift`.

This item lists a bounded risk-first sample of `SECURITY DEFINER` functions owned by superusers or by a role that differs from the schema owner.

## What this item shows
- Function identity and owner.
- Schema owner.
- Whether the function owner is a superuser.
- At most 1,000 candidates, with superuser-owned functions first and then descending observed calls.

## What to watch
- Findings that conflict with the approved ownership, privilege, or application-role baseline.
- Broad or unexpected access paths that can be combined with inherited role membership.

## Common fault causes
- Legacy grants or ownership left by migrations, role changes, extension upgrades, or manual administration.
- Intentional exceptions that were not documented or revalidated.

## Automatic evaluation

- `high` is appropriate only for superuser ownership; owner/schema mismatch is a review signal whose intent depends on the ownership model.
- Ownership is only one dimension: also inspect the local `search_path`, body, grants, and mutable dependencies.
- Empty output applies only to the bounded candidate set; functions beyond it were not evaluated.
- Extension ownership is checked after bounded risk-first selection. `candidate_sample_truncated = true` means the root limit was reached and functions excluded later may have occupied places ahead of unchecked functions; a `[coverage]` row prevents that partial sample from rendering as clean `empty`.

## Related report items
- [object_workload.security_definer_functions](#item-object_workload.security_definer_functions) — Review the affected privileged functions.
- [object_workload.superuser_owned_user_objects](#item-object_workload.superuser_owned_user_objects) — Find privileged ownership of other user objects.
- [cluster_inventory.privileged_roles](#item-cluster_inventory.privileged_roles) — Inspect elevated function owners.

## Checklist
- Avoid superuser-owned `SECURITY DEFINER` functions unless strictly required.
- Use dedicated least-privilege owner roles.
- Verify `search_path` and function body before changing ownership.
