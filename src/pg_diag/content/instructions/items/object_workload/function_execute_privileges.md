# Function Execute Privileges

This instruction belongs to report item `object_workload.function_execute_privileges`.

This item reports PUBLIC or grantable `EXECUTE` privileges on user-defined functions.

## What this item shows
- Functions executable by `PUBLIC`.
- Grantable `EXECUTE` privileges held by non-owner roles.
- Higher risk when PUBLIC can execute a `SECURITY DEFINER` function.

## What to watch
- Findings that conflict with the approved ownership, privilege, or application-role baseline.
- Broad or unexpected access paths that can be combined with inherited role membership.

## Common fault causes
- Legacy grants or ownership left by migrations, role changes, extension upgrades, or manual administration.
- Intentional exceptions that were not documented or revalidated.

## Automatic evaluation

- `high`: PUBLIC can execute a `SECURITY DEFINER` function with no local `search_path`.
- `medium`: PUBLIC can execute a configured `SECURITY DEFINER` function, or a non-owner can re-grant EXECUTE.
- PUBLIC EXECUTE on an ordinary function is PostgreSQL's default and is shown as `ok`, not as a vulnerability.
- The item evaluates at most 1,000 functions prioritized by descending call count, expands at most 3,000 matching ACL rows, and displays at most 1,000 rows.
- Extension ownership is checked after the bounded function root is selected. If the root limit is reached, extension-owned roots removed later may have occupied places ahead of unchecked functions. `candidate_sample_truncated`, `acl_expansion_truncated`, and `result_truncated` identify root, ACL expansion, or output truncation; a `[coverage]` row prevents a false clean `empty`.

## Related report items
- [object_workload.security_definer_functions](#item-object_workload.security_definer_functions) — Identify privileged execution contexts.
- [object_workload.direct_user_grants](#item-object_workload.direct_user_grants) — Review direct function grants.
- [cluster_inventory.privilege_surface_by_role](#item-cluster_inventory.privilege_surface_by_role) — Place function access in the role's wider privilege surface.

## Checklist
- Revoke default PUBLIC function execution where it is not required.
- Keep `SECURITY DEFINER` functions callable only by explicit trusted roles.
- Review function grants after migrations and extension changes.
