# Security Definer Functions

This item lists user-defined `SECURITY DEFINER` functions that are not owned by extensions.

## What this item shows
- Function owner, language, signature, and function-local configuration.
- Whether the owner is a superuser.
- Whether the function sets a local `search_path`.

## Automatic evaluation
- `high`: a superuser-owned function has no function-local `search_path`.
- `medium`: either the owner is superuser or a local `search_path` is absent.
- A configured path is evidence, not proof that every entry is trusted; the function body still requires review.

## Checklist
- Review each `SECURITY DEFINER` function for privilege escalation paths.
- Prefer a function-local safe `search_path`.
- Avoid superuser-owned `SECURITY DEFINER` functions unless strictly required.
