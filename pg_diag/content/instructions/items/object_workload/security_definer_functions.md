# Security Definer Functions

This instruction belongs to report item `object_workload.security_definer_functions`.

This item lists user-defined `SECURITY DEFINER` functions that are not owned by extensions.

## What this item shows
- Function owner, language, signature, and function-local configuration.
- Whether the owner is a superuser.
- Whether the function sets a local `search_path`.

## What to watch
- Findings that conflict with the approved ownership, privilege, or application-role baseline.
- Broad or unexpected access paths that can be combined with inherited role membership.

## Common fault causes
- Legacy grants or ownership left by migrations, role changes, extension upgrades, or manual administration.
- Intentional exceptions that were not documented or revalidated.

## Automatic evaluation

- `high`: a superuser-owned function has no function-local `search_path`.
- `medium`: either the owner is superuser or a local `search_path` is absent.
- A configured path is evidence, not proof that every entry is trusted; the function body still requires review.

## Related report items
- [object_workload.security_definer_owner_drift](#item-object_workload.security_definer_owner_drift) — Review owners of SECURITY DEFINER functions.
- [object_workload.function_execute_privileges](#item-object_workload.function_execute_privileges) — Check who can execute the functions.
- [object_workload.direct_user_grants](#item-object_workload.direct_user_grants) — Review direct grants to affected roles.

## Checklist
- Review each `SECURITY DEFINER` function for privilege escalation paths.
- Prefer a function-local safe `search_path`.
- Avoid superuser-owned `SECURITY DEFINER` functions unless strictly required.
