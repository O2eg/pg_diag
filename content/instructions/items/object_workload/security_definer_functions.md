# Security Definer Functions

This item lists user-defined `SECURITY DEFINER` functions that are not owned by extensions.

## What this item shows
- Function owner, language, signature, and function-local configuration.
- Whether the owner is a superuser.
- Whether the function sets a local `search_path`.

## Checklist
- Review each `SECURITY DEFINER` function for privilege escalation paths.
- Prefer a function-local safe `search_path`.
- Avoid superuser-owned `SECURITY DEFINER` functions unless strictly required.
