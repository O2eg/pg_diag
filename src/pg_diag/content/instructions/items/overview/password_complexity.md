# Password Complexity

This instruction belongs to report item `overview.password_complexity`. The item is backed by `security.password_complexity` (SQL query).

## What this item shows
- Whether `passwordcheck` or `credcheck` is preloaded.
- Whether related extensions are installed or available.
- Current `shared_preload_libraries` value for context.

## What to watch
- `medium` means neither exact module name is active in `shared_preload_libraries`.
- Installed/available extension fields are discovery hints; `passwordcheck` can be supplied as a preload library rather than a SQL extension.
- An empty result means one recognized hook is preloaded, not that its policy is strong or that all authentication paths use local passwords.

## Common fault causes
- Password policy is enforced by an external identity provider instead of PostgreSQL.
- A module was installed but not preloaded, or a required restart was not completed.
- A different custom password hook is used and is not recognized by this check.

## Applicability
- Do not treat this item as a failure when local PostgreSQL password creation is prohibited or controlled externally.
- The query recognizes only exact `passwordcheck` and `credcheck` preload entries.

## Automatic evaluation
- A missing recognized password hook is reported as `medium`; applicability must be evaluated against external identity controls.

## Related report items
- [cluster_inventory.role_password_hashes](#item-cluster_inventory.role_password_hashes) — Review the stored verifier population.
- [overview.password_encryption](#item-overview.password_encryption) — Check the hashing policy used for newly set passwords.

## Checklist
- Use `passwordcheck`, `credcheck`, or an equivalent password policy mechanism for local PostgreSQL passwords.
- Add the chosen module to `shared_preload_libraries` and restart PostgreSQL when required.
- Keep extension installation consistent across databases where password management occurs.
- Document an equivalent external control when this check is intentionally not applicable.
