# Security Definer Owner Drift

This item lists `SECURITY DEFINER` functions owned by superusers or by a role that differs from the schema owner.

## What this item shows
- Function identity and owner.
- Schema owner.
- Whether the function owner is a superuser.

## Checklist
- Avoid superuser-owned `SECURITY DEFINER` functions unless strictly required.
- Use dedicated least-privilege owner roles.
- Verify `search_path` and function body before changing ownership.
