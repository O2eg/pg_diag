# Orphaned Object Owners

This item reports no-login roles that own user objects and need verification.

## What this item shows
- Owner role name.
- Whether the owner can login or is superuser.
- Number of user objects owned by the role.

## Automatic evaluation
- Severity is `unknown`: no-login ownership is normally desirable privilege separation and does not mean a role is orphaned.
- A finding becomes actionable only when the role is absent from the ownership baseline or operational process.

## Checklist
- Confirm that each no-login owner role is intentional and managed.
- Reassign objects owned by deprecated roles.
- Keep ownership roles separate from login roles where possible.
