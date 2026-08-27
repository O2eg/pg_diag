# Role Password Validity

This instruction belongs to report item `users_roles.password_validity`. The item is backed by `roles.password_validity` (SQL query).

## What this item shows
- Login roles with `validity_state` (`no expiry`, `valid`, `expires within 30 days`, or `expired`), the `valid_until` timestamp, and `days_until_expiry`.
- The evaluation reads `pg_roles.rolvaliduntil` only; password hashes are not read and superuser privileges are not required.

## What to watch
- Expired roles that still exist: `VALID UNTIL` restricts only password authentication, so `peer`, `cert`, `trust`, or GSSAPI rules keep the role usable.
- Superusers and service accounts without any expiry when the security policy requires rotation.
- Roles expiring soon whose applications have no rotation procedure.

## Common fault causes
- Temporary accounts created with an expiry date and never removed after the project ended.
- Passwords rotated without updating `VALID UNTIL`.
- Rotation policies applied to human accounts but not to service accounts.

## Automatic evaluation
- `medium`: the password validity has expired while the role still exists and can log in.
- `unknown`: the password expires within 30 days, or a superuser login role has no expiry.
- `ok`: all other login roles.
- The list covers the first 5,000 login roles; `result_truncated` marks partial coverage.

## Related report items
- [cluster_inventory.role_password_hashes](#item-cluster_inventory.role_password_hashes) — Check password hash strength when superuser access is available.
- [overview.password_encryption](#item-overview.password_encryption) — Verify the server-side password encryption setting.
- [users_roles.hba_rules](#item-users_roles.hba_rules) — Identify non-password authentication rules that still admit expired roles.

## Checklist
- Drop or `NOLOGIN` expired roles that are no longer needed.
- Schedule rotation for roles expiring within 30 days.
- Decide explicitly whether service accounts and superusers need an expiry.
